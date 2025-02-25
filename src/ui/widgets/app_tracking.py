from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, 
                            QTreeWidgetItem, QTreeWidgetItemIterator, QHeaderView, QSizePolicy, QToolTip,
                            QListWidget, QTableWidget, QTableWidgetItem, QListWidgetItem)
from PyQt5.QtCore import QTimer, Qt, QRect, QPoint
from PyQt5.QtGui import QFont, QPainter, QColor, QPen
import time
import traceback
from datetime import datetime, timedelta
from core.data_manager import DataManager
import subprocess
from Foundation import NSWorkspace
import os
from core.config import APP_NAME, DATA_RETENTION_DAYS
import json
import logging
from ui.widgets.time_graph_widget import TimeGraphWidget

class AppTrackingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # 초기화
        self.active_app = None
        self.active_window = None
        self.active_start_time = None
        self._is_active = True
        self.current_date = datetime.now().date()
        self.selected_date = self.current_date.strftime('%Y-%m-%d')
        
        # 데이터 매니저 초기화
        self.data_manager = DataManager.get_instance()
        
        # 앱 사용 데이터 로드
        self.app_usage = self.data_manager.load_app_usage()
        if not self.app_usage:
            self.app_usage = {'dates': {}}
        if 'dates' not in self.app_usage:
            self.app_usage['dates'] = {}
        if self.selected_date not in self.app_usage['dates']:
            self.app_usage['dates'][self.selected_date] = {}
        
        # 타이머 설정 (0.5초마다 업데이트)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_usage_stats)
        self.timer.start(500)  # 0.5초마다

        # 트리 업데이트 최적화를 위한 변수
        self._last_tree_update = 0
        self._tree_update_interval = 2.0  # 트리 업데이트 간격을 2초로 설정
        self._pending_tree_update = False  # 트리 업데이트 대기 상태 초기화
        self._expanded_items = {}  # 확장된 아이템 상태를 저장할 딕셔너리

    def update_usage_stats(self):
        """현재 활성화된 앱의 사용 통계를 업데이트합니다."""
        try:
            workspace = NSWorkspace.sharedWorkspace()
            active_app = workspace.activeApplication()
            
            if active_app:
                app_name = active_app['NSApplicationName']
                current_time = time.time()
                current_date = datetime.now().date().strftime('%Y-%m-%d')
                
                # 날짜 데이터가 없으면 초기화
                if current_date not in self.app_usage['dates']:
                    self.app_usage['dates'][current_date] = {}
                
                # 창 제목 가져오기
                window_info = self.get_active_window_title()
                window_title = window_info[1] if isinstance(window_info, tuple) else window_info
                
                # 앱이 변경되었을 때
                if app_name != self.active_app:
                    # 이전 앱의 사용 시간 업데이트
                    if self.active_app and self.active_start_time:
                        elapsed = current_time - self.active_start_time
                        if elapsed > 0 and self.active_app in self.app_usage['dates'][current_date]:
                            self.app_usage['dates'][current_date][self.active_app]['total_time'] += elapsed
                            
                            # 이전 창의 현재 세션 업데이트
                            if self.active_window and 'sessions' in self.app_usage['dates'][current_date][self.active_app]:
                                sessions = self.app_usage['dates'][current_date][self.active_app]['sessions']
                                if sessions and sessions[0]['window'] == self.active_window:
                                    sessions[0]['duration'] += elapsed
                                    sessions[0]['end_time'] = datetime.now().strftime('%H:%M:%S')
                
                    # 앱 데이터 초기화 또는 업데이트
                    if app_name not in self.app_usage['dates'][current_date]:
                        self.app_usage['dates'][current_date][app_name] = {
                            'total_time': 0,
                            'windows': {},
                            'start_times': [],
                            'sessions': []  # 세션 목록 추가
                        }
                    else:
                        # 기존 앱 데이터에 필요한 키가 없으면 추가
                        if 'sessions' not in self.app_usage['dates'][current_date][app_name]:
                            self.app_usage['dates'][current_date][app_name]['sessions'] = []
                        if 'start_times' not in self.app_usage['dates'][current_date][app_name]:
                            self.app_usage['dates'][current_date][app_name]['start_times'] = []
                    
                    # windows 딕셔너리에 창 제목 추가
                    if window_title:
                        # 창 제목이 앱 이름과 같은지 확인
                        if window_title == app_name:
                            # 앱 전환 후 약간의 지연을 추가하여 더 정확한 창 제목을 가져올 수 있도록 함
                            time.sleep(0.2)
                            # 더 정확한 창 제목 가져오기 시도
                            better_title = self.get_app_window_title(app_name)
                            if better_title and better_title != app_name:
                                window_title = better_title
                        
                        if window_title not in self.app_usage['dates'][current_date][app_name]['windows']:
                            self.app_usage['dates'][current_date][app_name]['windows'][window_title] = 0
                        
                        # 새 세션 추가
                        current_time_str = datetime.now().strftime('%H:%M:%S')
                        new_session = {
                            'window': window_title,
                            'start_time': current_time_str,
                            'end_time': current_time_str,  # 초기값은 시작 시간과 동일
                            'duration': 0  # 초기 지속 시간은 0
                        }
                        self.app_usage['dates'][current_date][app_name]['sessions'].insert(0, new_session)
                    
                    # 현재 시간을 시작 시간 목록의 맨 앞에 추가 (기존 호환성 유지)
                    current_time_str = datetime.now().strftime('%H:%M:%S')
                    self.app_usage['dates'][current_date][app_name]['start_times'].insert(0, current_time_str)
                    
                    self.active_app = app_name
                    self.active_window = window_title
                    self.active_start_time = current_time
                else:
                    # 같은 앱을 계속 사용 중인 경우에도 시간 업데이트
                    if self.active_app and self.active_start_time:
                        elapsed = current_time - self.active_start_time
                        if elapsed > 0 and self.active_app in self.app_usage['dates'][current_date]:
                            # 필요한 키가 없으면 추가
                            if 'start_times' not in self.app_usage['dates'][current_date][self.active_app]:
                                self.app_usage['dates'][current_date][self.active_app]['start_times'] = []
                            if 'sessions' not in self.app_usage['dates'][current_date][self.active_app]:
                                self.app_usage['dates'][current_date][self.active_app]['sessions'] = []
                            
                            # 현재 시간까지의 사용 시간을 업데이트
                            self.app_usage['dates'][current_date][self.active_app]['total_time'] += elapsed
                            
                            # 창이 변경되었는지 확인
                            if window_title != self.active_window:
                                # 이전 창의 시간 업데이트
                                if self.active_window in self.app_usage['dates'][current_date][self.active_app]['windows']:
                                    self.app_usage['dates'][current_date][self.active_app]['windows'][self.active_window] += elapsed
                                
                                # 이전 세션 업데이트
                                if 'sessions' in self.app_usage['dates'][current_date][self.active_app]:
                                    sessions = self.app_usage['dates'][current_date][self.active_app]['sessions']
                                    if sessions and sessions[0]['window'] == self.active_window:
                                        sessions[0]['duration'] += elapsed
                                        sessions[0]['end_time'] = datetime.now().strftime('%H:%M:%S')
                                
                                # 새 창 추가
                                if window_title not in self.app_usage['dates'][current_date][self.active_app]['windows']:
                                    self.app_usage['dates'][current_date][self.active_app]['windows'][window_title] = 0
                                
                                # 새 세션 추가
                                current_time_str = datetime.now().strftime('%H:%M:%S')
                                new_session = {
                                    'window': window_title,
                                    'start_time': current_time_str,
                                    'end_time': current_time_str,
                                    'duration': 0
                                }
                                self.app_usage['dates'][current_date][self.active_app]['sessions'].insert(0, new_session)
                                
                                # 시작 시간 추가 (기존 호환성 유지)
                                self.app_usage['dates'][current_date][self.active_app]['start_times'].insert(0, current_time_str)
                                
                                self.active_window = window_title
                            else:
                                # 같은 창이면 해당 창의 시간만 업데이트
                                if self.active_window in self.app_usage['dates'][current_date][self.active_app]['windows']:
                                    self.app_usage['dates'][current_date][self.active_app]['windows'][self.active_window] += elapsed
                                
                                # 현재 세션 업데이트
                                if 'sessions' in self.app_usage['dates'][current_date][self.active_app]:
                                    sessions = self.app_usage['dates'][current_date][self.active_app]['sessions']
                                    if sessions and sessions[0]['window'] == self.active_window:
                                        sessions[0]['duration'] += elapsed
                                        sessions[0]['end_time'] = datetime.now().strftime('%H:%M:%S')
                            
                            # 시작 시간 재설정
                            self.active_start_time = current_time
            
        except Exception as e:
            logging.error(f"앱 사용 통계 업데이트 중 오류 발생: {e}")
            traceback.print_exc()

    def save_expanded_state(self):
        """더 이상 tree widget을 사용하지 않으므로 빈 메서드로 유지"""
        pass

    def restore_expanded_state(self):
        """더 이상 tree widget을 사용하지 않으므로 빈 메서드로 유지"""
        pass

    def update_app_time(self, app_name=None, window_title=None, elapsed_time=None):
        """앱 사용 시간을 업데이트합니다."""
        try:
            if not all([app_name, elapsed_time]) or app_name == APP_NAME:
                return
                
            current_date = datetime.now().date().strftime('%Y-%m-%d')
            
            # 날짜 데이터가 없으면 초기화
            if current_date not in self.app_usage['dates']:
                self.app_usage['dates'][current_date] = {}
            
            # 앱 데이터가 없으면 초기화
            if app_name not in self.app_usage['dates'][current_date]:
                self.app_usage['dates'][current_date][app_name] = {
                    'total_time': 0,
                    'windows': {},
                    'start_times': []
                }
            elif 'start_times' not in self.app_usage['dates'][current_date][app_name]:
                # 기존 앱 데이터에 start_times 필드가 없으면 추가
                self.app_usage['dates'][current_date][app_name]['start_times'] = []
            
            # 앱의 총 사용 시간 업데이트
            self.app_usage['dates'][current_date][app_name]['total_time'] += elapsed_time
            
            # 창별 사용 시간 업데이트
            if window_title:
                # window_title이 튜플인 경우 첫 번째 요소만 사용
                if isinstance(window_title, tuple):
                    window_title = window_title[1] if len(window_title) > 1 else window_title[0]
                    
                if window_title not in self.app_usage['dates'][current_date][app_name]['windows']:
                    self.app_usage['dates'][current_date][app_name]['windows'][window_title] = 0
                self.app_usage['dates'][current_date][app_name]['windows'][window_title] += elapsed_time
            
        except Exception as e:
            logging.error(f"앱 시간 업데이트 중 오류 발생: {e}")
            traceback.print_exc()

    def get_app_window_title(self, app_name):
        """각 앱의 현재 창/탭 제목을 가져옵니다."""
        try:
            # 특정 앱에 대한 특별 처리
            if app_name in ["Safari", "Chrome", "Firefox", "Arc", "Brave Browser"]:
                # 브라우저용 특별 스크립트
                script = f'''
                    tell application "{app_name}"
                        try
                            set windowTitle to name of front window
                            return windowTitle
                        on error
                            return "{app_name}"
                        end try
                    end tell
                '''
            elif app_name in ["Cursor", "Visual Studio Code", "Code", "Sublime Text"]:
                # 코드 에디터용 특별 스크립트
                script = f'''
                    tell application "System Events"
                        tell process "{app_name}"
                            try
                                set windowTitle to name of front window
                                if windowTitle contains "{app_name}" then
                                    set windowTitle to windowTitle
                                end if
                                return windowTitle
                            on error
                                return "{app_name}"
                            end try
                        end tell
                    end tell
                '''
            else:
                # 일반적인 앱용 스크립트 (더 강력한 버전)
                script = f'''
                    tell application "System Events"
                        tell process "{app_name}"
                            try
                                set windowList to every window
                                set frontWindow to item 1 of windowList
                                set windowTitle to name of frontWindow
                                return windowTitle
                            on error
                                try
                                    set windowTitle to name of front window
                                    return windowTitle
                                on error
                                    return "{app_name}"
                                end try
                            end try
                        end tell
                    end tell
                '''
            
            # 스크립트 실행
            result = subprocess.run(['osascript', '-e', script], 
                                  capture_output=True, 
                                  text=True,
                                  timeout=1.5)
            
            window_title = result.stdout.strip()
            
            # 결과가 비어있거나 앱 이름과 같으면 다른 방법 시도
            if not window_title or window_title == app_name:
                # 대체 스크립트 시도
                alt_script = f'''
                    tell application "System Events"
                        tell application process "{app_name}"
                            try
                                set frontWindow to first window
                                set windowTitle to title of frontWindow
                                return windowTitle
                            on error
                                try
                                    set windowTitle to name of front window
                                    return windowTitle
                                on error
                                    return "{app_name}"
                                end try
                            end try
                        end tell
                    end tell
                '''
                
                alt_result = subprocess.run(['osascript', '-e', alt_script], 
                                          capture_output=True, 
                                          text=True,
                                          timeout=1.5)
                
                alt_window_title = alt_result.stdout.strip()
                
                if alt_window_title and alt_window_title != app_name:
                    return alt_window_title
            
            if window_title and window_title != app_name:
                return window_title
            
            # 특정 앱에 대한 하드코딩된 접근 방식
            if app_name == "Cursor":
                return "Cursor Editor"
            elif app_name == "Arc":
                return "Arc Browser"
            
            return app_name
            
        except subprocess.TimeoutExpired:
            return app_name
        except Exception:
            return app_name

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
            app_pid = active_app['NSApplicationProcessIdentifier']
            
            # 캐시 확인 (캐시 시간을 5초로 조정)
            cache_key = f"{app_name}_{app_pid}"
            current_time = time.time()
            
            if (hasattr(self, '_window_title_cache') and 
                cache_key in self._window_title_cache and 
                current_time - self._window_title_cache[cache_key]['time'] < 5.0):
                cached_title = self._window_title_cache[cache_key]['title']
                return app_name, cached_title
            
            # our_pid 속성이 없는 경우 처리
            our_pid = getattr(self, 'our_pid', None)
            if our_pid is None:
                our_pid = os.getpid()
            
            # 우리 앱인 경우
            if active_app['NSApplicationProcessIdentifier'] == our_pid:
                window_title = "Home" if self.isActiveWindow() else "Timer"
                return app_name, window_title
            
            # 시스템 앱은 제외
            skip_apps = {'Finder', 'SystemUIServer', 'loginwindow', 'Dock', 'Control Center', 'Notification Center'}
            if app_name in skip_apps:
                return app_name, app_name
            
            # 앱별 특수 처리
            if app_name in ["Safari", "Chrome", "Firefox", "Arc", "Brave Browser"]:
                window_title = self.get_browser_window_title(app_name)
                if window_title and window_title != app_name:
                    # 캐시 업데이트
                    if not hasattr(self, '_window_title_cache'):
                        self._window_title_cache = {}
                    self._window_title_cache[cache_key] = {
                        'title': window_title,
                        'time': current_time
                    }
                    return app_name, window_title
            
            # 일반적인 방법으로 창 제목 가져오기
            try:
                # 약간의 지연을 추가하여 앱이 완전히 활성화되도록 함
                time.sleep(0.1)
                
                script = f'''
                    tell application "System Events"
                        tell process "{app_name}"
                            try
                                set frontWindow to first window whose focused is true
                                set windowTitle to name of frontWindow
                                return windowTitle
                            on error
                                try
                                    set windowTitle to name of front window
                                    return windowTitle
                                on error
                                    return "{app_name}"
                                end try
                            end try
                        end tell
                    end tell
                '''
                
                result = subprocess.run(['osascript', '-e', script], 
                                      capture_output=True, 
                                      text=True,
                                      timeout=1.0)
                
                window_title = result.stdout.strip()
                if result.returncode == 0 and window_title and window_title != app_name:
                    # 캐시 업데이트
                    if not hasattr(self, '_window_title_cache'):
                        self._window_title_cache = {}
                    self._window_title_cache[cache_key] = {
                        'title': window_title,
                        'time': current_time
                    }
                    
                    return app_name, window_title
            except:
                pass
            
            # 대체 방법 시도
            try:
                alt_script = f'''
                    tell application "System Events"
                        tell application process "{app_name}"
                            try
                                set windowTitle to name of front window
                                return windowTitle
                            on error
                                return "{app_name}"
                            end try
                        end tell
                    end tell
                '''
                
                alt_result = subprocess.run(['osascript', '-e', alt_script], 
                                          capture_output=True, 
                                          text=True,
                                          timeout=1.0)
                
                alt_window_title = alt_result.stdout.strip()
                if alt_result.returncode == 0 and alt_window_title and alt_window_title != app_name:
                    # 캐시 업데이트
                    if not hasattr(self, '_window_title_cache'):
                        self._window_title_cache = {}
                    self._window_title_cache[cache_key] = {
                        'title': alt_window_title,
                        'time': current_time
                    }
                    
                    return app_name, alt_window_title
            except:
                pass
            
            # 특정 앱에 대한 하드코딩된 처리
            if app_name == "Cursor":
                return app_name, "Cursor Editor"
            elif app_name == "Visual Studio Code":
                return app_name, "VS Code Editor"
            elif app_name == "Arc":
                return app_name, "Arc Browser"
            
            return app_name, app_name
            
        except Exception as e:
            logging.error(f"활성 창 정보 가져오기 실패: {e}")
            return None, None

    def get_browser_window_title(self, browser_name):
        """브라우저의 창 제목을 가져옵니다."""
        try:
            script = f'''
                tell application "{browser_name}"
                    try
                        set windowTitle to name of front window
                        return windowTitle
                    on error
                        return "{browser_name}"
                    end try
                end tell
            '''
            
            result = subprocess.run(['osascript', '-e', script], 
                                  capture_output=True, 
                                  text=True,
                                  timeout=1.0)
            
            window_title = result.stdout.strip()
            if result.returncode == 0 and window_title and window_title != browser_name:
                return window_title
            
            return browser_name
        except:
            return browser_name

    def update_tree_widget(self):
        """트리 위젯의 내용을 업데이트합니다."""
        try:
            current_date = datetime.now().date().strftime('%Y-%m-%d')
            if current_date not in self.app_usage['dates']:
                return

            # 현재 선택된 정렬 열과 정렬 순서 저장
            header = self.tree_widget.header()
            sort_column = header.sortIndicatorSection()
            sort_order = header.sortIndicatorOrder()

            # 트리가 비어있을 때만 새로 생성
            if self.tree_widget.topLevelItemCount() == 0:
                self.create_tree_items()
            else:
                self.update_tree_items()

            # 이전 정렬 상태 복원
            self.tree_widget.sortItems(sort_column, sort_order)
            
            # 총 사용 시간 업데이트
            self.update_total_time()
            
            # 데이터 저장
            self.data_manager.save_app_usage(self.app_usage)
            
            # 확장 상태 복원
            self.restore_expanded_state()
            
        except Exception as e:
            logging.error(f"트리 위젯 업데이트 중 오류 발생: {e}")
            traceback.print_exc()

    def create_tree_items(self):
        """트리 아이템을 처음 생성합니다."""
        current_date = datetime.now().date().strftime('%Y-%m-%d')
        
        for app_name, app_data in self.app_usage['dates'][current_date].items():
            if app_name == APP_NAME:  # 자기 자신은 표시하지 않음
                continue
                
            # 부모 아이템 생성
            app_item = QTreeWidgetItem(self.tree_widget)
            app_item.setText(0, app_name)  # 앱 이름
            app_item.setText(1, '')  # 시작 시간은 비워둠
            app_item.setText(2, '')  # 종료 시간은 비워둠
            app_item.setData(0, Qt.UserRole, app_name)  # 앱 이름을 데이터로 저장
            
            # 총 사용 시간 계산 및 설정
            total_time = self.calculate_total_time(app_data)
            app_item.setText(3, self.format_time(total_time))
            
            # 창/탭별 세부 정보
            start_times = app_data.get('start_times', [])
            windows = app_data.get('windows', {})
            
            # 각 창에 대해 자식 아이템 생성
            for window_title, window_time in windows.items():
                if window_title:  # 창 제목이 있는 경우만
                    # window_title이 튜플인 경우 첫 번째 요소만 사용
                    if isinstance(window_title, tuple):
                        window_title = window_title[1] if len(window_title) > 1 else window_title[0]
                    
                    # 시작 시간을 역순으로 정렬 (최신 시간이 먼저 오도록)
                    sorted_times = sorted(start_times, reverse=True)
                    
                    # 각 시작 시간에 대해 별도의 항목 생성
                    for start_time in sorted_times:
                        window_item = QTreeWidgetItem(app_item)
                        window_item.setText(0, window_title)
                        window_item.setData(0, Qt.UserRole, window_title)
                        window_item.setText(1, start_time)
                        window_item.setText(2, '')
                        window_item.setText(3, '')
                        # 맨 앞에 삽입
                        app_item.insertChild(0, window_item)
        
        # 확장 상태 복원
        # self.restore_expanded_state()

    def update_tree_items(self):
        """기존 트리 아이템의 시간 정보만 업데이트합니다."""
        current_date = datetime.now().date().strftime('%Y-%m-%d')
        
        # 모든 최상위 아이템(앱)을 순회
        for i in range(self.tree_widget.topLevelItemCount()):
            app_item = self.tree_widget.topLevelItem(i)
            app_name = app_item.data(0, Qt.UserRole)
            
            if app_name in self.app_usage['dates'][current_date]:
                app_data = self.app_usage['dates'][current_date][app_name]
                
                # 총 사용 시간 업데이트
                total_time = self.calculate_total_time(app_data)
                app_item.setText(3, self.format_time(total_time))

    def calculate_total_time(self, app_data):
        """앱의 총 사용 시간을 계산합니다."""
        total_time = 0
        windows = app_data.get('windows', {})
        for window_time in windows.values():
            if isinstance(window_time, (int, float)):
                total_time += window_time
        return total_time

    def update_total_time(self):
        """총 사용 시간을 업데이트합니다."""
        try:
            current_date = datetime.now().date().strftime('%Y-%m-%d')
            if 'dates' not in self.app_usage or current_date not in self.app_usage['dates']:
                self.total_time_label.setText("00:00:00")
                return
            
            date_data = self.app_usage['dates'][current_date]
            total_time = sum(app_data.get('total_time', 0) 
                           for app_data in date_data.values() 
                           if isinstance(app_data, dict))
            
            self.total_time_label.setText(self.format_time(total_time))
            
        except Exception as e:
            logging.error(f"총 시간 업데이트 중 오류 발생: {e}")
            traceback.print_exc()

    def format_time(self, seconds):
        """초를 시:분:초 형식으로 변환합니다."""
        try:
            if isinstance(seconds, dict):
                seconds = seconds.get('total_time', 0)
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            seconds = int(seconds % 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        except Exception as e:
            logging.error(f"시간 포맷팅 중 오류 발생: {e}")
            return "00:00:00"

    def _update_app_list(self):
        """앱 목록을 업데이트합니다."""
        try:
            current_date = datetime.now().date().strftime('%Y-%m-%d')
            if current_date not in self.app_usage['dates']:
                return
            
            # 현재 선택된 앱 저장
            current_app = self.app_list.currentItem()
            current_app_name = current_app.data(Qt.UserRole) if current_app else None
            
            # 목록 업데이트 시작
            self.app_list.blockSignals(True)
            self.app_list.clear()
            
            # 앱 데이터 정렬 (사용 시간 기준)
            app_data = []
            for app_name, data in self.app_usage['dates'][current_date].items():
                if app_name == APP_NAME:
                    continue
                total_time = data.get('total_time', 0)
                app_data.append((app_name, total_time))
            
            app_data.sort(key=lambda x: x[1], reverse=True)
            
            # 앱 목록 추가
            selected_item = None
            for app_name, total_time in app_data:
                item = QListWidgetItem()
                item.setText(f"{app_name} ({self.format_time(total_time)})")
                item.setData(Qt.UserRole, app_name)
                self.app_list.addItem(item)
                
                # 이전에 선택된 앱과 같은 앱이면 저장
                if app_name == current_app_name:
                    selected_item = item
            
            # 이전 선택 복원
            if selected_item:
                self.app_list.setCurrentItem(selected_item)
            
            self.app_list.blockSignals(False)
            
        except Exception as e:
            logging.error(f"앱 목록 업데이트 중 오류 발생: {e}")

    def _on_app_selected(self, current, previous):
        """앱이 선택되었을 때 호출됩니다."""
        if current:
            app_name = current.data(Qt.UserRole)
            self._update_detail_view(app_name)

    def setup_style(self):
        # 다크 테마 스타일
        dark_style = """
            QWidget {
                background-color: #1E1E1E;
                color: white;
            }
            QListWidget {
                background-color: #2C2C2C;
                border: none;
                padding: 5px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #3C3C3C;
            }
            QListWidget::item:selected {
                background-color: #404040;
            }
            QTableWidget {
                background-color: #2C2C2C;
                border: none;
                gridline-color: #3C3C3C;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QHeaderView::section {
                background-color: #2C2C2C;
                color: white;
                padding: 8px;
                border: 1px solid #3C3C3C;
            }
            QLabel {
                color: white;
            }
        """
        self.setStyleSheet(dark_style)

    def cleanup_old_data(self, days_to_keep=None):
        """오래된 데이터를 정리합니다."""
        try:
            # 설정된 보관 기간 사용 (기본값: config에서 정의한 값)
            if days_to_keep is None:
                days_to_keep = DATA_RETENTION_DAYS
                
            today = datetime.now().date()
            dates_to_remove = []
            
            for date_str in self.app_usage['dates']:
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    days_old = (today - date_obj).days
                    
                    if days_old > days_to_keep:
                        dates_to_remove.append(date_str)
                except ValueError:
                    # 잘못된 날짜 형식은 무시
                    continue
            
            # 오래된 데이터 삭제
            for date_str in dates_to_remove:
                del self.app_usage['dates'][date_str]
            
            return len(dates_to_remove)
        except Exception as e:
            logging.error(f"오래된 데이터 정리 중 오류 발생: {e}")
            return 0

class Home_app_tracking(AppTrackingWidget):
    def __init__(self, parent=None, our_pid=None):
        super().__init__(parent)
        
        # our_pid 설정
        self.our_pid = our_pid or os.getpid()
        
        # 초기화 변수 설정
        self._last_time_update = time.time()
        self._update_interval = 1.0
        self.tree_widget = None  # tree_widget 사용하지 않음
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # UI 초기화
        self._init_ui(layout)
        
        # 타이머 설정
        self.timer.setInterval(1000)
        
        # 그래프 업데이트 타이머
        self.graph_timer = QTimer(self)
        self.graph_timer.timeout.connect(self._update_graph)
        self.graph_timer.start(1000)
        
        # 초기 데이터 업데이트
        self._update_graph()

    def _init_ui(self, layout):
        # Total 시간과 그래프를 포함하는 컨테이너
        total_graph_container = QWidget()
        total_graph_layout = QVBoxLayout(total_graph_container)
        total_graph_layout.setContentsMargins(0, 0, 0, 0)
        
        # Total 시간
        total_container = QWidget()
        total_layout = QHBoxLayout(total_container)
        total_layout.setContentsMargins(0, 0, 0, 0)
        
        self.total_label = QLabel("Total")
        self.total_label.setFont(QFont("Arial", 20, QFont.Bold))
        self.total_time_label = QLabel("00:00:00")
        self.total_time_label.setFont(QFont("Arial", 20, QFont.Bold))
        
        total_layout.addWidget(self.total_label)
        total_layout.addStretch()
        total_layout.addWidget(self.total_time_label)
        
        # 시간 그래프
        self.time_graph = TimeGraphWidget()
        
        # 컨테이너에 위젯 추가
        total_graph_layout.addWidget(total_container)
        total_graph_layout.addWidget(self.time_graph)
        
        # 앱 목록과 상세 정보를 포함할 컨테이너
        content_container = QWidget()
        content_layout = QHBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        # 앱 목록 (왼쪽)
        app_list_container = QWidget()
        app_list_layout = QVBoxLayout(app_list_container)
        app_list_layout.setContentsMargins(0, 0, 0, 0)
        
        # 앱 목록 레이블
        app_list_label = QLabel("Applications")
        app_list_label.setFont(QFont("Arial", 16, QFont.Bold))
        app_list_layout.addWidget(app_list_label)
        
        # 앱 목록 위젯
        self.app_list = QListWidget()
        self.app_list.setFont(QFont("Arial", 14))
        self.app_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.app_list.setHorizontalScrollMode(QListWidget.ScrollPerPixel)
        self.app_list.setUniformItemSizes(True)
        self.app_list.currentItemChanged.connect(self._on_app_selected)
        app_list_layout.addWidget(self.app_list)
        
        # 상세 정보 패널 (오른쪽)
        detail_container = QWidget()
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        
        # 상세 정보 레이블
        detail_label = QLabel("Details")
        detail_label.setFont(QFont("Arial", 16, QFont.Bold))
        detail_layout.addWidget(detail_label)
        
        # 상세 정보 테이블
        self.detail_table = QTableWidget()
        self.detail_table.setColumnCount(3)
        self.detail_table.setHorizontalHeaderLabels(["Window", "Start Time", "Duration"])
        self.detail_table.setFont(QFont("Arial", 14))
        self.detail_table.verticalHeader().setVisible(False)
        self.detail_table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.detail_table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        
        # 테이블 헤더 설정
        header = self.detail_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.detail_table.setColumnWidth(1, 100)
        self.detail_table.setColumnWidth(2, 100)
        
        detail_layout.addWidget(self.detail_table)
        
        # 컨테이너에 위젯 추가
        content_layout.addWidget(app_list_container, 1)
        content_layout.addWidget(detail_container, 2)
        
        # 메인 레이아웃에 위젯 추가
        layout.addWidget(total_graph_container)
        layout.addWidget(content_container)
        
        # 스타일 설정
        self.setup_style()

    def _update_graph(self):
        """그래프와 UI를 업데이트합니다."""
        try:
            if not hasattr(self, 'time_graph') or not hasattr(self, 'app_usage'):
                return
            
            update_start = time.time()
            
            # 그래프 데이터 업데이트
            self.time_graph.update_data(self.app_usage)
            
            # 앱 목록과 상세 정보 업데이트
            if update_start - self._last_time_update >= self._update_interval:
                # 현재 선택된 앱 저장
                current_app = self.app_list.currentItem()
                current_app_name = current_app.data(Qt.UserRole) if current_app else None
                
                # 앱 목록 업데이트
                self._update_app_list()
                
                # 선택된 앱이 있었다면 다시 선택
                if current_app_name:
                    for i in range(self.app_list.count()):
                        item = self.app_list.item(i)
                        if item.data(Qt.UserRole) == current_app_name:
                            self.app_list.setCurrentItem(item)
                            # 상세 정보 업데이트
                            self._update_detail_view(current_app_name)
                
                self._last_time_update = update_start
            else:
                # 업데이트 간격이 아니더라도 선택된 앱의 상세 정보는 업데이트
                current_app = self.app_list.currentItem()
                if current_app:
                    app_name = current_app.data(Qt.UserRole)
                    self._update_detail_view(app_name)
            
            # 총 시간 업데이트
            self.update_total_time()
            
        except Exception as e:
            logging.error(f"그래프 업데이트 중 오류 발생: {e}")
            traceback.print_exc()

    def _update_app_list(self):
        """앱 목록을 업데이트합니다."""
        try:
            current_date = datetime.now().date().strftime('%Y-%m-%d')
            if current_date not in self.app_usage['dates']:
                return
            
            # 현재 선택된 앱 저장
            current_app = self.app_list.currentItem()
            current_app_name = current_app.data(Qt.UserRole) if current_app else None
            
            # 목록 업데이트 시작
            self.app_list.blockSignals(True)
            self.app_list.clear()
            
            # 앱 데이터 정렬 (사용 시간 기준)
            app_data = []
            for app_name, data in self.app_usage['dates'][current_date].items():
                if app_name == APP_NAME:
                    continue
                total_time = data.get('total_time', 0)
                app_data.append((app_name, total_time))
            
            app_data.sort(key=lambda x: x[1], reverse=True)
            
            # 앱 목록 추가
            selected_item = None
            for app_name, total_time in app_data:
                item = QListWidgetItem()
                item.setText(f"{app_name} ({self.format_time(total_time)})")
                item.setData(Qt.UserRole, app_name)
                self.app_list.addItem(item)
                
                # 이전에 선택된 앱과 같은 앱이면 저장
                if app_name == current_app_name:
                    selected_item = item
            
            # 이전 선택 복원
            if selected_item:
                self.app_list.setCurrentItem(selected_item)
            
            self.app_list.blockSignals(False)
            
        except Exception as e:
            logging.error(f"앱 목록 업데이트 중 오류 발생: {e}")

    def _on_app_selected(self, current, previous):
        """앱이 선택되었을 때 호출됩니다."""
        if current:
            app_name = current.data(Qt.UserRole)
            self._update_detail_view(app_name)

    def _update_detail_view(self, app_name):
        """선택된 앱의 상세 정보를 업데이트합니다."""
        try:
            current_date = datetime.now().date().strftime('%Y-%m-%d')
            if current_date not in self.app_usage['dates'] or app_name not in self.app_usage['dates'][current_date]:
                return
            
            app_data = self.app_usage['dates'][current_date][app_name]
            
            # 세션 데이터 가져오기
            sessions = app_data.get('sessions', [])
            
            # 테이블 업데이트 시작
            self.detail_table.setRowCount(0)
            
            # 세션이 없는 경우 기존 방식으로 처리 (이전 버전과의 호환성)
            if not sessions:
                windows = app_data.get('windows', {})
                start_times = app_data.get('start_times', [])
                
                # 창별 사용 시간 표시
                window_items = []
                for window_title, window_time in windows.items():
                    # 창 제목 처리
                    display_title = self._get_window_display_title(window_title)
                    window_items.append((display_title, window_time, ""))
                
                # 사용 시간 기준으로 정렬 (많이 사용한 창 먼저)
                window_items.sort(key=lambda x: x[1], reverse=True)
                
                # 시작 시간과 창 정보 표시
                for i, (window_title, window_time, _) in enumerate(window_items):
                    row = self.detail_table.rowCount()
                    self.detail_table.insertRow(row)
                    
                    # 창 제목
                    title_item = QTableWidgetItem(str(window_title))
                    self.detail_table.setItem(row, 0, title_item)
                    
                    # 시작 시간 (있는 경우)
                    start_time = start_times[i] if i < len(start_times) else ""
                    time_item = QTableWidgetItem(start_time)
                    self.detail_table.setItem(row, 1, time_item)
                    
                    # 사용 시간
                    duration_item = QTableWidgetItem(self.format_time(window_time))
                    self.detail_table.setItem(row, 2, duration_item)
            else:
                # 현재 활성화된 창 가져오기
                active_window = None
                if app_name == self.active_app:
                    active_window = self._get_window_display_title(self.active_window)
                
                # 세션을 시작 시간 기준으로 정렬 (최신 세션이 먼저 표시)
                # sessions는 이미 최신 순으로 정렬되어 있으므로 그대로 사용
                
                # 각 세션을 개별적으로 표시
                for session in sessions:
                    window_title = session['window']
                    start_time = session['start_time']
                    duration = session['duration']
                    
                    # 현재 활성 세션인 경우 실시간 시간 계산
                    if app_name == self.active_app and self._get_window_display_title(window_title) == active_window and session == sessions[0]:
                        current_time = time.time()
                        elapsed = current_time - self.active_start_time
                        duration += elapsed
                    
                    # 창 제목 처리
                    display_title = self._get_window_display_title(window_title)
                    
                    row = self.detail_table.rowCount()
                    self.detail_table.insertRow(row)
                    
                    # 창 제목
                    title_item = QTableWidgetItem(str(display_title))
                    self.detail_table.setItem(row, 0, title_item)
                    
                    # 시작 시간
                    time_item = QTableWidgetItem(start_time)
                    self.detail_table.setItem(row, 1, time_item)
                    
                    # 사용 시간
                    duration_item = QTableWidgetItem(self.format_time(duration))
                    self.detail_table.setItem(row, 2, duration_item)
        
        except Exception as e:
            logging.error(f"상세 정보 업데이트 중 오류 발생: {e}")

    def setup_style(self):
        # 다크 테마 스타일
        dark_style = """
            QWidget {
                background-color: #1E1E1E;
                color: white;
            }
            QListWidget {
                background-color: #2C2C2C;
                border: none;
                padding: 5px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #3C3C3C;
            }
            QListWidget::item:selected {
                background-color: #404040;
            }
            QTableWidget {
                background-color: #2C2C2C;
                border: none;
                gridline-color: #3C3C3C;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QHeaderView::section {
                background-color: #2C2C2C;
                color: white;
                padding: 8px;
                border: 1px solid #3C3C3C;
            }
            QLabel {
                color: white;
            }
        """
        self.setStyleSheet(dark_style)

    def _get_window_display_title(self, window_title):
        """창 제목을 표시용으로 변환합니다."""
        if isinstance(window_title, tuple):
            return window_title[1] if len(window_title) > 1 else window_title[0]
        return window_title