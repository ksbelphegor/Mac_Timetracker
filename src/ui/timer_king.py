import sys
import time
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QPushButton, QLabel, QSystemTrayIcon, QMenu, QAction)
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
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import threading

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
        
        # 데이터 매니저 초기화
        self.data_manager = DataManager.get_instance()
        
        # 캐시 및 상태 관리
        self._window_title_cache = {}
        self._app_list_cache = set()
        self._last_app_update = 0
        self._last_window_check = 0
        self._window_check_interval = 0.5  # 윈도우 체크 간격 (초)
        self._app_cache_lifetime = 5.0  # 앱 캐시 수명 (초)
        
        # 메모리 캐시
        self._memory_cache = {
            'active_app': None,
            'window_title': None,
            'last_update': 0,
            'last_ui_update': 0
        }
        
        # Timer 데이터 초기화
        self.timer_data = self.data_manager.load_timer_data()
        
        # 앱 사용 통계 관련 초기화
        self.last_update_time = time.time()
        self.current_date = datetime.datetime.now().date().strftime('%Y-%m-%d')
        
        # 저장된 데이터 불러오기
        self.app_usage = self.data_manager.load_app_usage()
        if 'dates' not in self.app_usage:
            self.app_usage['dates'] = {}
        
        # 현재 날짜의 데이터가 없으면 초기화
        if self.current_date not in self.app_usage['dates']:
            self.app_usage['dates'][self.current_date] = {}
        
        # StatusBarController 초기화
        self.status_bar_controller = StatusBarController.alloc().init()
        self.create_status_bar_menu()
        
        # 위젯 초기화
        self.home_widget = HomeWidget(self)
        self.time_track_widget = TimerWidget()
        
        # Timer 위젯 설정
        self.time_track_widget.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.time_track_widget.reset_button.clicked.connect(self.reset_timer)
        self.time_track_widget.app_combo.currentTextChanged.connect(self.on_app_selected)
        
        # 앱 리스트 초기화
        self.running_apps = set()
        self.update_app_list()
        
        self.initUI()
        
        # 타이머 설정
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)  # 1초마다 업데이트
        
        self.app_update_timer = QTimer(self)
        self.app_update_timer.timeout.connect(self.update_app_list)
        self.app_update_timer.start(5000)  # 5초마다 업데이트
        
        # UI 업데이트 최적화를 위한 변수
        self._last_ui_update = 0
        self._ui_update_interval = 0.5  # UI 업데이트 간격 (초)
        
        # 파일 저장 최적화를 위한 변수
        self._last_save = 0
        self._save_interval = 60  # 저장 간격 (초)
        self._data_changed = False
        
        self.start_time = time.time()

    def initUI(self):
        self.setWindowTitle('타임')
        self.setFixedSize(1024, 1024)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.addWidget(self.home_widget)

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
            if not self.timer_data['app_name']:
                return
                
            current_time = time.time()
            
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
                    self.time_track_widget.time_frame.setStyleSheet("""
                        QFrame {
                            background-color: #FFCCCC;
                            border-radius: 4px;
                            padding: 5px;
                        }
                    """)
                self._pending_save = True
            
            # 시간 계산
            if self.timer_data['is_active']:
                elapsed = current_time - self.timer_data['start_time']
                current_total = self.timer_data['total_time'] + elapsed
            else:
                current_total = self.timer_data['total_time']
            
            # UI 업데이트 (1초에 한 번)
            if current_time - self._memory_cache['last_ui_update'] >= 1.0:
                hours = int(current_total // 3600)
                minutes = int((current_total % 3600) // 60)
                seconds = int(current_total % 60)
                time_text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                
                self.status_bar_controller.update_time_display(time_text)
                if hasattr(self, 'time_track_widget'):
                    self.time_track_widget.update_time_display(time_text)
                
                self._memory_cache['last_ui_update'] = current_time
            
            # 데이터 저장 (30초마다)
            if self._pending_save and current_time - getattr(self, '_last_save_time', 0) >= 30.0:
                self.data_manager.save_timer_data(self.timer_data)
                self._last_save_time = current_time
                self._pending_save = False
                
        except Exception as e:
            print(f"Error in update_time: {e}")

    def get_active_window_title(self):
        current_time = time.time()
        
        try:
            # 캐시된 윈도우 타이틀이 유효한 경우 사용
            if (current_time - self._memory_cache['last_update'] < self._window_check_interval and
                self._memory_cache['window_title'] is not None):
                return self._memory_cache['window_title']
            
            # Home 화면과 Timer 창 확인
            if self.isActiveWindow():
                self._update_window_cache("Home", current_time)
                return "Home"
            elif hasattr(self, 'time_track_widget') and self.time_track_widget.isActiveWindow():
                self._update_window_cache("Timer", current_time)
                return "Timer"
            
            active_app = NSWorkspace.sharedWorkspace().activeApplication()
            if not active_app:
                self._update_window_cache("Unknown", current_time)
                return "Unknown"
            
            app_name = active_app.get('NSApplicationName', '')
            active_pid = active_app.get('NSApplicationProcessIdentifier', 0)
            
            # 우리 앱인 경우
            if active_pid == self.our_pid:
                window_title = "Home" if self.isActiveWindow() else "Timer"
                self._update_window_cache(window_title, current_time)
                return window_title
            
            # 캐시된 타이틀 확인
            cache_key = f"{app_name}_{active_pid}"
            if (cache_key in self._window_title_cache and 
                current_time - self._window_title_cache[cache_key]['time'] < 5.0):
                window_title = self._window_title_cache[cache_key]['title']
                self._update_window_cache(window_title, current_time)
                return window_title
            
            # AppleScript는 마지막 수단으로만 사용
            window_title = app_name
            self._window_title_cache[cache_key] = {
                'time': current_time,
                'title': window_title
            }
            self._update_window_cache(window_title, current_time)
            return window_title
            
        except Exception as e:
            print(f"Error getting window title: {e}")
            return "Unknown"

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
        QApplication.instance().quit()

    def show_timer(self):
        """Timer 창을 표시합니다."""
        # 창이 이미 표시되어 있다면 활성화만 합니다
        if self.time_track_widget.isVisible():
            self.time_track_widget.raise_()
            self.time_track_widget.activateWindow()
            return
        
        # 앱 리스트가 오래되었으면 업데이트
        current_time = time.time()
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
            'is_active': False
        }
        # 화면 업데이트
        self.update_time_display()

    def update_usage_stats(self):
        """앱 사용 통계를 업데이트합니다."""
        try:
            current_time = time.time()
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
                    'is_active': False
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
                window_title = self.get_active_window_title()
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
            import traceback
            print(traceback.format_exc())

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
            window_time = time.time() - self.timer_data.get('start_time', 0) if self.timer_data['is_active'] else 0
            self.time_track_widget.update_time_display(time_text, self.format_time(window_time), self.timer_data['app_name'])

    def update_app_list(self):
        current_time = time.time()
        
        # 캐시가 유효한 경우 캐시된 앱 리스트 사용
        if (current_time - self._last_app_update < self._app_cache_lifetime and 
            self._app_list_cache):
            self.running_apps = self._app_list_cache
        else:
            # 캐시가 만료되었거나 비어있는 경우 앱 리스트 업데이트
            self.running_apps = set()
            for app in NSWorkspace.sharedWorkspace().runningApplications():
                if app.activationPolicy() == NSApplicationActivationPolicyRegular:
                    app_name = app.localizedName()
                    if app_name:
                        self.running_apps.add(app_name)
            
            # 캐시 업데이트
            self._app_list_cache = self.running_apps.copy()
            self._last_app_update = current_time
        
        # Timer 창의 콤보박스 업데이트 (재귀 호출 방지)
        if hasattr(self, 'time_track_widget'):
            current_app = self.timer_data.get('app_name')  # timer_data에서 현재 앱 이름을 가져옴
            self.time_track_widget.app_combo.blockSignals(True)  # 시그널 일시 차단
            self.time_track_widget.update_app_list(self.running_apps, current_app)
            self.time_track_widget.app_combo.blockSignals(False)  # 시그널 복원

    def select_app(self, app_name):
        """앱을 선택하고 시간 트래킹을 시작합니다."""
        # Timer 데이터 초기화
        self.timer_data = {
            'app_name': app_name,
            'start_time': None,
            'total_time': 0,
            'is_active': False
        }
        
        # 현재 앱이 활성화되어 있는지 확인
        active_app = NSWorkspace.sharedWorkspace().activeApplication()
        is_target_app_active = active_app and active_app['NSApplicationName'] == app_name
        
        # UI 업데이트
        if is_target_app_active:
            self.timer_data['start_time'] = time.time()
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
                DataManager.force_save_all()
                event.accept()
        except Exception as e:
            print(f"Error in closeEvent: {e}")
            event.accept()