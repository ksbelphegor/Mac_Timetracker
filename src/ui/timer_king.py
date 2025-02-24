import time as time_module
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QPushButton, QLabel, QSystemTrayIcon, QMenu, QAction,
                            QApplication)
from PyQt5.QtCore import Qt, QTimer, QSettings
from PyQt5.QtGui import QIcon, QFont
import os
import json

from core.config import *
from core.data_manager import DataManager
from core.status_bar import StatusBarController
from ui.widgets.home_widget import HomeWidget
from ui.widgets.timer_widget import TimerWidget
from AppKit import NSWorkspace, NSApplicationActivationPolicyRegular
import datetime
import shutil
import objc
from subprocess import Popen, PIPE, TimeoutExpired
import Cocoa
from concurrent.futures import ThreadPoolExecutor
from functools import partial

class TimerKing(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_QuitOnClose, False)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        
        # 현재 프로세스 ID 저장
        self.our_pid = os.getpid()
        self.our_bundle_id = BUNDLE_ID
        self.our_app_name = APP_NAME
        
        # 초기화 플래그
        self._is_shutting_down = False
        self._pending_updates = False
        self._initialization_complete = False
        
        # 데이터 매니저 초기화
        self.data_manager = DataManager.get_instance()
        
        # 기본 데이터 초기화
        self.current_date = datetime.datetime.now().date().strftime('%Y-%m-%d')
        self.app_usage = {'dates': {self.current_date: {}}}
        self.timer_data = {
            'app_name': None,
            'start_time': None,
            'total_time': 0,
            'is_active': False,
            'windows': {},
            'current_window': None,
            'last_update': time_module.time()
        }
        
        # 캐시 및 상태 관리
        self._window_title_cache = {}
        self._app_list_cache = set()
        self._last_app_update = 0
        self._last_window_check = 0
        self._window_check_interval = 1.0  # 0.5초에서 1초로 증가
        self._app_cache_lifetime = 10.0  # 5초에서 10초로 증가
        
        # 메모리 캐시 최적화
        self._memory_cache = {
            'active_app': None,
            'window_title': None,
            'last_update': 0,
            'last_ui_update': 0,
            'last_save': 0,
            'pending_updates': set(),
            'cache_hits': 0,
            'cache_misses': 0
        }
        
        # 성능 최적화를 위한 설정
        self._batch_size = 20  # 10에서 20으로 증가
        self._min_update_interval = 0.2  # 0.1초에서 0.2초로 증가
        self._last_batch_process = 0
        self._cache_cleanup_counter = 0  # 캐시 정리를 위한 카운터
        
        # UI 초기화
        self.initUI()
        
        # 비동기 초기화 시작
        self._start_async_initialization()
        
    def _start_async_initialization(self):
        """비동기적으로 앱 초기화를 수행합니다."""
        self.async_timer = QTimer(self)
        self.async_timer.timeout.connect(self._async_init_step)
        self.async_timer.start(500)  # 500ms로 증가
        self._init_step = 0
        
    def _async_init_step(self):
        """초기화 단계를 순차적으로 실행합니다."""
        if self._init_step == 0:
            # 기본 타이머 데이터 로드
            self.timer_data = self.data_manager.load_timer_data()
            self._init_step += 1
            
        elif self._init_step == 1:
            # 최근 사용 데이터만 로드
            recent_usage = self.data_manager.load_recent_app_usage()
            if recent_usage:
                self.app_usage.update(recent_usage)
            self._init_step += 1
            
        elif self._init_step == 2:
            # 앱 리스트 초기 업데이트
            self.update_app_list()
            self._init_step += 1
            
        elif self._init_step == 3:
            # 나머지 데이터 백그라운드 로드 시작
            self._load_remaining_data_async()
            self._init_step += 1
            self._initialization_complete = True
            self.async_timer.stop()
            
    def _load_remaining_data_async(self):
        """나머지 앱 사용 데이터를 백그라운드에서 로드합니다."""
        def load_data():
            full_usage = self.data_manager.load_app_usage()
            return full_usage
            
        self.thread_pool = ThreadPoolExecutor(max_workers=1)
        future = self.thread_pool.submit(load_data)
        future.add_done_callback(self._on_data_loaded)
        
    def _on_data_loaded(self, future):
        """백그라운드 데이터 로딩이 완료되면 호출됩니다."""
        try:
            full_usage = future.result()
            if full_usage:
                self.app_usage.update(full_usage)
        except Exception as e:
            print(f"데이터 로딩 중 오류 발생: {e}")

    def initUI(self):
        """UI 컴포넌트를 초기화합니다."""
        self.setWindowTitle('타임 트래커')
        self.setFixedSize(1024, 1024)
        
        # StatusBarController 초기화
        self.status_bar_controller = StatusBarController.alloc().init()
        self.create_status_bar_menu()
        
        # 기본 위젯 초기화
        self.home_widget = HomeWidget(self)
        self.time_track_widget = TimerWidget()
        
        # 중앙 위젯 설정
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.addWidget(self.home_widget)
        
        # Timer 위젯 설정
        self.time_track_widget.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.time_track_widget.reset_button.clicked.connect(self.reset_timer)
        self.time_track_widget.app_combo.currentTextChanged.connect(self.on_app_selected)
        
        # 앱 리스트 초기화
        self.running_apps = set()
        
        # 타이머 설정
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)  # 1초로 설정
        
        # 앱 업데이트 타이머
        self.app_update_timer = QTimer(self)
        self.app_update_timer.timeout.connect(self.update_app_list)
        self.app_update_timer.start(10000)  # 10초 유지
        
        # 자동 저장 타이머 추가
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self.autosave_data)
        self.autosave_timer.start(30000)  # 30초마다 저장
        
        # UI 업데이트 최적화를 위한 변수
        self._last_ui_update = 0
        self._ui_update_interval = 0.5  # 0.5초 유지
        
        # 파일 저장 최적화를 위한 변수
        self._last_save = 0
        self._save_interval = 120  # 120초 유지
        self._data_changed = False
        
        self.start_time = time_module.time()
        
        # 스타일시트 설정
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1E1E1E;
            }
            QWidget {
                background-color: #1E1E1E;
                color: #FFFFFF;
            }
            QPushButton {
                background-color: #2C2C2C;
                border: none;
                padding: 8px 15px;
                border-radius: 5px;
                color: #FFFFFF;
            }
            QPushButton:hover {
                background-color: #404040;
            }
            QPushButton:pressed {
                background-color: #505050;
            }
        """)

    def update_time(self):
        try:
            if not self.timer_data.get('app_name'):
                return
                
            current_time = time_module.time()
            
            # 메모리 캐시에서 앱 정보 가져오기
            if current_time - self._memory_cache['last_update'] < self._window_check_interval:
                app_name = self._memory_cache['active_app']
                is_selected_app_active = (app_name == self.timer_data['app_name'])
            else:
                app = NSWorkspace.sharedWorkspace().activeApplication()
                if not app:
                    return
                app_name = app['NSApplicationName']
                is_selected_app_active = (app_name == self.timer_data['app_name'])
                self._memory_cache.update({
                    'active_app': app_name,
                    'last_update': current_time
                })
            
            # 상태가 변경된 경우에만 업데이트
            if is_selected_app_active != self.timer_data['is_active']:
                if is_selected_app_active:
                    if not self.timer_data['is_active']:
                        self.timer_data['start_time'] = current_time
                        self.timer_data['is_active'] = True
                        self.timer_data['last_update'] = current_time
                    self.time_track_widget.time_frame.setStyleSheet("""
                        QFrame {
                            background-color: #CCE5FF;
                            border-radius: 4px;
                            padding: 5px;
                        }
                    """)
                else:
                    if self.timer_data['is_active']:
                        elapsed = current_time - self.timer_data['start_time']
                        self.timer_data['total_time'] += elapsed
                        self.timer_data['is_active'] = False
                        self.timer_data['last_update'] = current_time
                    self.time_track_widget.time_frame.setStyleSheet("""
                        QFrame {
                            background-color: #FFCCCC;
                            border-radius: 4px;
                            padding: 5px;
                        }
                    """)
                self._memory_cache['pending_updates'].add('timer_data')
            
            # 시간 계산 및 UI 업데이트 최적화
            if current_time - self._memory_cache['last_ui_update'] >= self._min_update_interval:
                if self.timer_data['is_active']:
                    elapsed = current_time - self.timer_data['start_time']
                    current_total = self.timer_data['total_time'] + elapsed
                else:
                    current_total = self.timer_data['total_time']
                
                hours = int(current_total // 3600)
                minutes = int((current_total % 3600) // 60)
                seconds = int(current_total % 60)
                time_text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                
                self.status_bar_controller.update_time_display(time_text)
                if hasattr(self, 'time_track_widget'):
                    self.time_track_widget.update_time_display(time_text)
                
                self._memory_cache['last_ui_update'] = current_time
            
            # 배치 처리로 데이터 저장 최적화
            if (len(self._memory_cache['pending_updates']) >= self._batch_size or 
                (self._memory_cache['pending_updates'] and 
                 current_time - self._last_batch_process >= 30.0)):
                self._process_pending_updates()
                
        except Exception as e:
            print(f"Error in update_time: {e}")
            import traceback
            traceback.print_exc()

    def _process_pending_updates(self):
        """배치로 대기 중인 업데이트를 처리합니다."""
        try:
            current_time = time_module.time()
            if 'timer_data' in self._memory_cache['pending_updates']:
                self.data_manager.save_timer_data(self.timer_data)
            self._memory_cache['pending_updates'].clear()
            self._last_batch_process = current_time
        except Exception as e:
            print(f"Error in _process_pending_updates: {e}")

    def get_active_window_title(self):
        """현재 활성 창의 제목을 가져옵니다."""
        try:
            # Home 화면과 Timer 창 확인
            if self.isActiveWindow():
                return "Home", "Home"
            elif hasattr(self, 'time_track_widget') and self.time_track_widget.isActiveWindow():
                return "Timer", "Timer"
            
            workspace = NSWorkspace.sharedWorkspace()
            active_app = workspace.activeApplication()
            if not active_app:
                return None, None
            
            app_name = active_app['NSApplicationName']
            
            # 우리 앱인 경우
            if active_app['NSApplicationProcessIdentifier'] == self.our_pid:
                window_title = "Home" if self.isActiveWindow() else "Timer"
                return app_name, window_title
            
            # 시스템 앱은 제외
            skip_apps = {'Finder', 'SystemUIServer', 'loginwindow', 'Dock', 'Control Center', 'Notification Center'}
            if app_name in skip_apps:
                return app_name, app_name
            
            # 캐시 확인
            cache_key = f"{app_name}_{active_app['NSApplicationProcessIdentifier']}"
            current_time = time_module.time()
            
            if (cache_key in self._window_title_cache and 
                current_time - self._window_title_cache[cache_key]['time'] < 10.0):  # 5초에서 10초로 증가
                self._memory_cache['cache_hits'] += 1
                return app_name, self._window_title_cache[cache_key]['title']
            
            self._memory_cache['cache_misses'] += 1
            
            # 캐시 업데이트
            window_title = app_name
            self._window_title_cache[cache_key] = {
                'title': window_title,
                'time': current_time
            }
            
            # 주기적으로 캐시 정리 (100회마다)
            self._cache_cleanup_counter += 1
            if self._cache_cleanup_counter >= 100:
                self._cleanup_cache()
                self._cache_cleanup_counter = 0
            
            return app_name, window_title
            
        except Exception as e:
            print(f"활성 창 정보 가져오기 실패: {e}")
            return None, None

    def _cleanup_cache(self):
        """오래된 캐시 항목을 정리합니다."""
        current_time = time_module.time()
        # 30초 이상 된 캐시 항목 제거
        self._window_title_cache = {
            k: v for k, v in self._window_title_cache.items()
            if current_time - v['time'] < 30.0
        }

    def _update_window_cache(self, title, time):
        """윈도우 타이틀 메모리 캐시를 업데이트합니다."""
        self._memory_cache.update({
            'window_title': title,
            'last_update': time
        })

    def create_status_bar_menu(self):
        """상태바 메뉴를 생성합니다."""
        menu = Cocoa.NSMenu.alloc().init()
        
        # Home 메뉴 아이템
        home_item = Cocoa.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Home", "showHome:", "")
        home_item.setTarget_(self)
        menu.addItem_(home_item)
        
        # Timer 메뉴 아이템
        timer_item = Cocoa.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Timer", "showTimer:", "")
        timer_item.setTarget_(self)
        menu.addItem_(timer_item)
        
        # 구분선
        menu.addItem_(Cocoa.NSMenuItem.separatorItem())
        
        # 종료 메뉴 아이템
        quit_item = Cocoa.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit", "quitApp:", "")
        quit_item.setTarget_(self)
        menu.addItem_(quit_item)
        
        # 메뉴 설정
        self.status_bar_controller.setMenu_(menu)

    @objc.python_method
    def showHome_(self, sender):
        self.show()

    @objc.python_method
    def showTimer_(self, sender):
        self.show_timer()

    @objc.python_method
    def quitApp_(self, sender):
        """앱을 종료합니다."""
        try:
            print("앱 종료 중... 데이터 저장")
            
            # 현재 실행 중인 앱의 시간 업데이트
            self.update_usage_stats()
            
            # 데이터 저장 전 현재 상태 출력
            current_date = datetime.datetime.now().date().strftime('%Y-%m-%d')
            print(f"저장할 데이터 확인 - 날짜: {current_date}")
            if hasattr(self, 'app_usage') and 'dates' in self.app_usage and current_date in self.app_usage['dates']:
                for app_name, data in self.app_usage['dates'][current_date].items():
                    total_time = data.get('total_time', 0)
                    print(f"- {app_name}: {self.format_time(total_time)}")
            
            # 모든 데이터 강제 저장
            DataManager.force_save_all()
            
            # 저장 확인 및 대기
            max_retries = 5
            retry_count = 0
            while retry_count < max_retries:
                if os.path.exists(APP_USAGE_FILE):
                    file_size = os.path.getsize(APP_USAGE_FILE)
                    print(f"데이터 파일 저장됨: {APP_USAGE_FILE}")
                    print(f"파일 크기: {file_size} bytes")
                    if file_size > 0:
                        print("데이터 저장 완료")
                        break
                print("데이터 저장 대기 중...")
                time_module.sleep(0.1)  # 100ms 대기
                retry_count += 1
            
            # 타이머 중지
            if hasattr(self, 'timer'):
                self.timer.stop()
            if hasattr(self, 'app_update_timer'):
                self.app_update_timer.stop()
            if hasattr(self, 'autosave_timer'):
                self.autosave_timer.stop()
            
        except Exception as e:
            print(f"앱 종료 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 앱 종료
            app = QApplication.instance()
            if app:
                app.quit()

    def show_timer(self):
        """Timer 창을 표시합니다."""
        # 창이 이미 표시되어 있다면 활성화만 합니다
        if self.time_track_widget.isVisible():
            self.time_track_widget.raise_()
            self.time_track_widget.activateWindow()
            return
        
        # 앱 리스트가 오래되었으면 업데이트
        current_time = time_module.time()
        if current_time - self._last_app_update >= self._app_cache_lifetime:
            self.update_app_list()
            
        # 현재 선택된 앱 정보 업데이트
        current_app = self.timer_data.get('app_name')  # timer_data에서 현재 앱 이름을 가져옴
        self.time_track_widget.update_app_list(self.running_apps, current_app)
        
        # 창 표시
        self.time_track_widget.show()
        self.time_track_widget.raise_()
        self.time_track_widget.activateWindow()

    def on_app_selected(self, app_name):
        if app_name and app_name != "Select App...":
            self.select_app(app_name)

    def reset_timer(self):
        # Timer 데이터 초기화
        self.timer_data = {
            'app_name': None,
            'start_time': None,
            'total_time': 0,
            'is_active': False,
            'windows': {},
            'current_window': None,
            'last_update': time_module.time()
        }
        # 화면 업데이트
        self.update_time_display()

    def update_usage_stats(self):
        """현재 실행 중인 앱의 시간을 업데이트합니다."""
        try:
            if not self.timer_data.get('is_active', False) or not self.timer_data.get('app_name'):
                return
                
            current_time = time_module.time()
            current_date = datetime.datetime.now().date().strftime('%Y-%m-%d')
            
            # 날짜가 변경되었는지 확인
            if current_date != self.current_date:
                print(f"날짜가 변경됨: {self.current_date} -> {current_date}")
                
                # 새로운 날짜의 데이터 초기화
                if current_date not in self.app_usage['dates']:
                    self.app_usage['dates'][current_date] = {}
                print(f"새로운 날짜({current_date})의 데이터 공간 생성됨")
                
                # 현재 날짜 업데이트
                self.current_date = current_date
                
                # 타이머 초기화
                self.timer_data = {
                    'app_name': None,
                    'start_time': None,
                    'total_time': 0,
                    'is_active': False,
                    'windows': {},
                    'current_window': None,
                    'last_update': time_module.time()
                }
            
            # 현재 활성화된 앱의 시간 업데이트
            if self.timer_data['is_active'] and self.timer_data['app_name']:
                app_name = self.timer_data['app_name']
                
                # 현재 날짜의 앱 데이터 초기화
                if app_name not in self.app_usage['dates'][current_date]:
                    self.app_usage['dates'][current_date][app_name] = {
                        'total_time': 0,
                        'windows': {},
                        'is_active': True,
                        'last_update': current_time
                    }
                
                elapsed = current_time - self.timer_data.get('start_time', current_time)
                self.app_usage['dates'][current_date][app_name]['total_time'] = (
                    self.app_usage['dates'][current_date][app_name].get('total_time', 0) + elapsed
                )
                self.app_usage['dates'][current_date][app_name]['last_update'] = current_time
                
                # 현재 창 시간 업데이트
                window_title = self.get_active_window_title()[1]
                if window_title:
                    if window_title not in self.app_usage['dates'][current_date][app_name]['windows']:
                        self.app_usage['dates'][current_date][app_name]['windows'][window_title] = 0
                    self.app_usage['dates'][current_date][app_name]['windows'][window_title] += elapsed
            
            # 데이터 저장
            self.data_manager.save_app_usage(self.app_usage)
            
            # Home 위젯 업데이트
            if hasattr(self, 'home_widget') and hasattr(self.home_widget, 'home_app_tracking'):
                self.home_widget.home_app_tracking.update_usage_stats()
            
        except Exception as e:
            print(f"통계 업데이트 중 오류 발생: {e}")
            traceback.print_exc()

    def save_app_usage(self):
        """앱 사용 통계를 저장합니다."""
        self.data_manager.save_app_usage(self.app_usage)

    def format_time(self, seconds):
        """Convert seconds into a formatted time string (HH:MM:SS)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def update_time_display(self):
        """상태바의 시간 표시를 업데이트합니다."""
        if not self.timer_data['app_name']:
            return
        
        current_total = self.timer_data['total_time']
        time_text = self.format_time(current_total)
        self.status_bar_controller.update_time_display(time_text)
        
        # Timer 위젯이 있으면 업데이트
        if hasattr(self, 'time_track_widget'):
            # 현재 창 시간과 전체 시간을 함께 전달
            window_time = time_module.time() - self.timer_data.get('start_time', 0) if self.timer_data['is_active'] else 0
            self.time_track_widget.update_time_display(time_text, self.format_time(window_time), self.timer_data['app_name'])

    def update_app_list(self):
        """실행 중인 앱 목록을 업데이트합니다."""
        current_time = time_module.time()
        
        # 캐시가 유효한 경우 캐시된 앱 리스트 사용
        if (current_time - self._last_app_update < self._app_cache_lifetime and 
            self._app_list_cache):
            return
        
        # 앱 리스트 업데이트
        new_apps = set()
        for app in NSWorkspace.sharedWorkspace().runningApplications():
            if app.activationPolicy() == NSApplicationActivationPolicyRegular:
                app_name = app.localizedName()
                if app_name:
                    new_apps.add(app_name)
        
        # 변경사항이 있을 때만 업데이트
        if new_apps != self._app_list_cache:
            self.running_apps = new_apps
            self._app_list_cache = new_apps.copy()
            self._last_app_update = current_time
            
            # Timer 창의 콤보박스 업데이트
            if hasattr(self, 'time_track_widget'):
                current_app = self.timer_data.get('app_name')
                self.time_track_widget.app_combo.blockSignals(True)
                self.time_track_widget.update_app_list(self.running_apps, current_app)
                self.time_track_widget.app_combo.blockSignals(False)

    def select_app(self, app_name):
        """앱을 선택하고 시간 트래킹을 시작합니다."""
        # Timer 데이터 초기화
        self.timer_data = {
            'app_name': app_name,
            'start_time': None,
            'total_time': 0,
            'is_active': False,
            'windows': {},
            'current_window': None,
            'last_update': time_module.time()
        }
        
        # 현재 앱이 활성화되어 있는지 확인
        active_app = NSWorkspace.sharedWorkspace().activeApplication()
        is_target_app_active = active_app and active_app['NSApplicationName'] == app_name
        
        # UI 업데이트
        if is_target_app_active:
            self.timer_data['start_time'] = time_module.time()
            self.timer_data['is_active'] = True
            self.time_track_widget.time_frame.setStyleSheet("""
                QFrame {
                    background-color: #CCE5FF;
                    border-radius: 4px;
                    padding: 5px;
                }
            """)
        else:
            self.time_track_widget.time_frame.setStyleSheet("""
                QFrame {
                    background-color: #FFCCCC;
                    border-radius: 4px;
                    padding: 5px;
                }
            """)
        
        # 데이터 저장
        self.data_manager.save_timer_data(self.timer_data)

    def start_tracking(self):
        # 이 메서드는 더 이상 update_time_display를 호출하지 않음
        if self.current_app:
            active_app = NSWorkspace.sharedWorkspace().activeApplication()
            is_target_app_active = active_app and active_app['NSApplicationName'] == self.current_app
            
            # 배경색만 업데이트
            if is_target_app_active:
                self.time_track_widget.time_frame.setStyleSheet("""
                    QFrame {
                        background-color: #CCE5FF;
                        border-radius: 4px;
                        padding: 5px;
                    }
                """)
            else:
                self.time_track_widget.time_frame.setStyleSheet("""
                    QFrame {
                        background-color: #FFCCCC;
                        border-radius: 4px;
                        padding: 5px;
                    }
                """)

    def closeEvent(self, event):
        """앱이 종료될 때 데이터를 저장합니다."""
        try:
            if not self._is_shutting_down:
                self._is_shutting_down = True
                print("앱 종료 중... 데이터 저장")
                
                # 현재 실행 중인 앱의 시간 업데이트
                self.update_usage_stats()
                
                # 데이터 저장 전 현재 상태 출력
                current_date = datetime.datetime.now().date().strftime('%Y-%m-%d')
                print(f"저장할 데이터 확인 - 날짜: {current_date}")
                if hasattr(self, 'app_usage') and 'dates' in self.app_usage and current_date in self.app_usage['dates']:
                    for app_name, data in self.app_usage['dates'][current_date].items():
                        total_time = data.get('total_time', 0)
                        print(f"- {app_name}: {self.format_time(total_time)}")
                
                # 모든 데이터 강제 저장
                DataManager.force_save_all()
                
                # 저장 확인
                if os.path.exists(APP_USAGE_FILE):
                    print(f"데이터 파일 저장됨: {APP_USAGE_FILE}")
                    print(f"파일 크기: {os.path.getsize(APP_USAGE_FILE)} bytes")
                
                print("데이터 저장 완료")
                
                # 타이머 중지
                if hasattr(self, 'timer'):
                    self.timer.stop()
                if hasattr(self, 'app_update_timer'):
                    self.app_update_timer.stop()
                if hasattr(self, 'autosave_timer'):
                    self.autosave_timer.stop()
                
                event.accept()
        except Exception as e:
            print(f"앱 종료 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            event.accept()

    def autosave_data(self):
        """30초마다 데이터를 자동 저장합니다."""
        try:
            # 현재 실행 중인 앱의 시간 업데이트
            self.update_usage_stats()
            
            # 데이터 저장
            if hasattr(self, 'app_usage') and hasattr(self, 'timer_data'):
                self.data_manager.save_app_usage(self.app_usage)
                self.data_manager.save_timer_data(self.timer_data)
                
        except Exception as e:
            print(f"자동 저장 중 오류 발생: {e}")
            traceback.print_exc()