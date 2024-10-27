import sys
import time
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QFrame, QMenu, QAction, QPushButton, 
                            QScrollArea, QMainWindow)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont
from AppKit import NSWorkspace, NSApplicationActivationPolicyRegular  # 이 부분 추가
import Cocoa
import objc
from subprocess import Popen, PIPE, TimeoutExpired  # TimeoutExpired 추가
from Foundation import NSURL, NSString
class StatusBarController(Cocoa.NSObject):
    def init(self):
        self = objc.super(StatusBarController, self).init()
        if self is None:
            return None
        self._setup_status_item()
        self._setup_custom_view()
        return self
    def _setup_status_item(self):
        self.statusItem = Cocoa.NSStatusBar.systemStatusBar().statusItemWithLength_(
            Cocoa.NSVariableStatusItemLength)
        self.statusItem.setHighlightMode_(True)
    def _setup_custom_view(self):
        self.custom_view = Cocoa.NSView.alloc().initWithFrame_(Cocoa.NSMakeRect(0, 0, 90, 22))
        
        self.icon_view = Cocoa.NSButton.alloc().initWithFrame_(Cocoa.NSMakeRect(0, 0, 22, 22))
        self.icon_view.setButtonType_(Cocoa.NSButtonTypeMomentaryLight)
        self.icon_view.setBordered_(False)
        icon_image = Cocoa.NSImage.alloc().initWithSize_(Cocoa.NSMakeSize(22, 22))
        icon_image.lockFocus()
        self.draw_clock_icon()
        icon_image.unlockFocus()
        self.icon_view.setImage_(icon_image)
        self.icon_view.setTarget_(self)
        self.icon_view.setAction_(objc.selector(self.iconClicked_, signature=b'v@:'))
        self.custom_view.addSubview_(self.icon_view)
        
        self.time_label = Cocoa.NSTextField.alloc().initWithFrame_(Cocoa.NSMakeRect(24, 2, 66, 20))
        self.time_label.setBezeled_(False)
        self.time_label.setDrawsBackground_(False)
        self.time_label.setEditable_(False)
        self.time_label.setSelectable_(False)
        self.time_label.setAlignment_(Cocoa.NSTextAlignmentCenter)
        self.time_label.setStringValue_("00:00:00")
        self.custom_view.addSubview_(self.time_label)
        
        self.statusItem.setView_(self.custom_view)
    def updateTime_(self, time_str):
        self.time_label.setStringValue_(time_str)
    def draw_clock_icon(self):
        width, height = 22, 22
        Cocoa.NSColor.blackColor().set()
        path = Cocoa.NSBezierPath.bezierPathWithOvalInRect_(Cocoa.NSMakeRect(1, 1, width-2, height-2))
        path.fill()
        Cocoa.NSColor.whiteColor().set()
        path = Cocoa.NSBezierPath.bezierPathWithOvalInRect_(Cocoa.NSMakeRect(2, 2, width-4, height-4))
        path.fill()
        Cocoa.NSColor.blackColor().set()
        path = Cocoa.NSBezierPath.bezierPath()
        path.moveToPoint_(Cocoa.NSMakePoint(width/2, height/2))
        path.lineToPoint_(Cocoa.NSMakePoint(width/2, height/2+7))
        path.moveToPoint_(Cocoa.NSMakePoint(width/2, height/2))
        path.lineToPoint_(Cocoa.NSMakePoint(width/2+5, height/2))
        path.setLineWidth_(2)
        path.stroke()
    def iconClicked_(self, sender):
        self.statusItem.popUpStatusItemMenu_(self.menu)
    def setMenu_(self, menu):
        self.menu = menu
class HomeWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)  # 전체 여백 조정
        
        # 홈 앱 트래킹 위젯을 전체 공간에 배치
        self.home_app_tracking = Home_app_tracking(self)
        # 최대 크기 제한 제거
        # self.home_app_tracking.setMaximumSize(450, 400)  
        
        # Quit 버튼 컨테이너
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)  # QVBoxLayout에서 QHBoxLayout으로 변경
        button_layout.setContentsMargins(0, 10, 0, 0)  # 상단 여백만 추가
        
        quit_button = QPushButton("Quit", self)
        quit_button.clicked.connect(QApplication.instance().quit)
        quit_button.setFixedWidth(100)  # 버튼 너비 고정
        
        button_layout.addStretch()  # 왼쪽 여백
        button_layout.addWidget(quit_button)  # 버튼을 오른쪽에 배치
        
        # 전체 레이아웃에 추가
        layout.addWidget(self.home_app_tracking, 1)  # stretch factor 1 추가
        layout.addWidget(button_container)
        
        self.setLayout(layout)
        
        # 타이머 설정
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)
    def update_time(self):
        if isinstance(self.parent(), TimeTracker):
            self.parent().update_time()
class Home_app_tracking(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Total 위젯을 멤버 변수로 저장
        self.total_container = QWidget()
        total_layout = QHBoxLayout(self.total_container)
        
        self.total_label = QLabel("Total")
        self.total_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.total_time_label = QLabel("00:00:00")
        self.total_time_label.setFont(QFont("Arial", 16, QFont.Bold))
        
        total_layout.addWidget(self.total_label)
        total_layout.addStretch()
        total_layout.addWidget(self.total_time_label)
        
        # 구분선도 미리 생성
        self.separator_line = QFrame()
        self.separator_line.setFrameShape(QFrame.HLine)
        self.separator_line.setFrameShadow(QFrame.Sunken)
        
        # 레이아웃에 추가
        layout.addWidget(self.total_container)
        layout.addWidget(self.separator_line)
        
        # 나머지 위젯들을 위한 레이아웃
        self.usage_stats_area = QScrollArea()
        self.usage_stats_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #ccc;
                border-radius: 8px;
                background-color: white;
            }
        """)
        self.usage_stats_widget = QWidget()
        self.usage_stats_layout = QVBoxLayout(self.usage_stats_widget)
        self.usage_stats_layout.setSpacing(8)
        self.usage_stats_area.setWidget(self.usage_stats_widget)
        self.usage_stats_area.setWidgetResizable(True)
        
        layout.addWidget(self.usage_stats_area)
        self._widgets_cache = {}
        self._layout_update_timer = QTimer()
        self._layout_update_timer.setSingleShot(True)
        self._layout_update_timer.timeout.connect(self._update_layout)
        self._pending_updates = set()

    def _update_total_widget(self, total_all_apps):
        # 기존 Total 라벨만 업데이트
        hours, remainder = divmod(int(total_all_apps), 3600)
        minutes, seconds = divmod(remainder, 60)
        self.total_time_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
    def update_usage_stats(self):
        try:
            main_window = self.window()
            if not isinstance(main_window, TimeTracker):
                return

            # 업데이트가 필요한 앱 목록 수집
            self._pending_updates = {
                app_name for app_name, app_data in main_window.app_usage.items()
                if app_data['total_time'] > 0
            }

            # 레이아웃 업데이트를 지연시켜 한 번에 처리
            if not self._layout_update_timer.isActive():
                self._layout_update_timer.start(100)

        except Exception as e:
            print(f"Error in update_usage_stats: {e}")

    def _update_layout(self):
        try:
            main_window = self.window()
            if not isinstance(main_window, TimeTracker):
                return

            # Total 시간 업데이트
            total_all_apps = sum(
                app_data['total_time'] 
                for app_data in main_window.app_usage.values()
            )
            self._update_total_widget(total_all_apps)

            # 앱별 위젯 업데이트
            current_apps = set()
            for app_name in self._pending_updates:
                if app_name in main_window.app_usage:
                    app_data = main_window.app_usage[app_name]
                    if app_data['total_time'] > 0:
                        current_apps.add(app_name)
                        if app_name in self._widgets_cache:
                            self._update_app_widget(
                                self._widgets_cache[app_name], 
                                app_name, 
                                app_data
                            )
                        else:
                            widget = self._create_app_widget(app_name, app_data)
                            self._widgets_cache[app_name] = widget
                            self.usage_stats_layout.addWidget(widget)

            # 사용하지 않는 위젯 정리
            for app_name in list(self._widgets_cache.keys()):
                if app_name not in current_apps:
                    widget = self._widgets_cache.pop(app_name)
                    self.usage_stats_layout.removeWidget(widget)
                    widget.deleteLater()

            self._pending_updates.clear()

        except Exception as e:
            print(f"Error in _update_layout: {e}")
    def _update_app_widget(self, widget, app_name, app_data):
        # 앱 전체 시간 업데이트
        total_time = app_data['total_time']
        hours, remainder = divmod(int(total_time), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        time_label = widget.findChild(QLabel, f"{app_name}_time")
        if time_label:
            time_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        
        # 기존 창/탭 위젯 제거
        windows_container = widget.findChild(QWidget, f"{app_name}_windows")
        if windows_container:
            layout = windows_container.layout()
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        
        # 새로운 창/탭 정보 추가
        if 'windows' in app_data:
            for window_title, window_time in sorted(app_data['windows'].items(), 
                                                  key=lambda x: x[1], reverse=True):
                if window_time > 0:  # 시간이 0보다 큰 경우만 표시
                    w_hours, w_remainder = divmod(int(window_time), 3600)
                    w_minutes, w_seconds = divmod(w_remainder, 60)
                    
                    window_container = QWidget()
                    window_layout = QHBoxLayout(window_container)
                    window_layout.setContentsMargins(20, 0, 0, 0)
                    
                    window_name_label = QLabel(window_title)
                    window_name_label.setFont(QFont("Arial", 12))
                    window_time_label = QLabel(f"{w_hours:02d}:{w_minutes:02d}:{w_seconds:02d}")
                    window_time_label.setFont(QFont("Arial", 12))
                    
                    window_layout.addWidget(window_name_label)
                    window_layout.addStretch()
                    window_layout.addWidget(window_time_label)
                    
                    layout.addWidget(window_container)
    def _create_app_widget(self, app_name, app_data):
        app_container = QWidget()
        app_container.setAttribute(Qt.WA_StyledBackground, True)
        app_layout = QVBoxLayout(app_container)
        app_layout.setContentsMargins(5, 5, 5, 5)
        app_layout.setSpacing(2)
        
        # 앱 헤더 (이름 + 총 시간)
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        app_name_label = QLabel(app_name)
        app_name_label.setFont(QFont("Arial", 14, QFont.Bold))
        
        total_time = app_data['total_time']
        hours, remainder = divmod(int(total_time), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        total_time_label = QLabel(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        total_time_label.setObjectName(f"{app_name}_time")  # 객체 이름 설정
        total_time_label.setFont(QFont("Arial", 14))
        
        header_layout.addWidget(app_name_label)
        header_layout.addStretch()
        header_layout.addWidget(total_time_label)
        
        app_layout.addWidget(header)
        
        # 탭/창 정보를 담을 컨테이너
        windows_container = QWidget()
        windows_container.setObjectName(f"{app_name}_windows")
        windows_layout = QVBoxLayout(windows_container)
        windows_layout.setContentsMargins(20, 0, 0, 0)
        
        # 탭/창 정보 추가
        if 'windows' in app_data:
            for window_title, window_time in sorted(app_data['windows'].items(), 
                                                  key=lambda x: x[1], reverse=True):
                if window_time > 0:  # 시간이 0보다 큰 경우만 표시
                    w_hours, w_remainder = divmod(int(window_time), 3600)
                    w_minutes, w_seconds = divmod(w_remainder, 60)
                    
                    window_container = QWidget()
                    window_layout = QHBoxLayout(window_container)
                    window_layout.setContentsMargins(20, 0, 0, 0)
                    
                    window_name_label = QLabel(window_title)
                    window_name_label.setFont(QFont("Arial", 12))
                    window_time_label = QLabel(f"{w_hours:02d}:{w_minutes:02d}:{w_seconds:02d}")
                    window_time_label.setFont(QFont("Arial", 12))
                    
                    window_layout.addWidget(window_name_label)
                    window_layout.addStretch()
                    window_layout.addWidget(window_time_label)
                    
                    windows_layout.addWidget(window_container)
        
        app_layout.addWidget(windows_container)
        return app_container
class TimeTrackWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        layout.setSpacing(5)
        layout.setContentsMargins(10, 10, 10, 10)
        self.time_frame = QFrame()
        self.time_frame.setFrameShape(QFrame.StyledPanel)
        self.time_frame.setStyleSheet("""
            QFrame {
                background-color: #FFCCCC;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        time_layout = QVBoxLayout(self.time_frame)
        self.time_label = QLabel('00:00:00')
        self.time_label.setStyleSheet("color: #000000; font-size: 18px; font-weight: bold;")
        self.time_label.setAlignment(Qt.AlignCenter)
        time_layout.addWidget(self.time_label)
        layout.addWidget(self.time_frame)
        self.setLayout(layout)
class TimeTracker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_QuitOnClose, False)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        
        self.running_apps = set()  # 리스트 대신 set 사용
        self.app_usage = {}
        self.current_app = None
        self.last_update_time = time.time()
        
        self.status_bar_controller = StatusBarController.alloc().init()
        self.create_status_bar_menu()
        
        self.home_widget = HomeWidget(self)
        self.time_track_widget = TimeTrackWidget()
        
        self.initUI()
        
        # 필수 타만 유
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)  # 1초마다 업데이트
        
        self.app_update_timer = QTimer(self)
        self.app_update_timer.timeout.connect(self.update_app_list)
        self.app_update_timer.start(10000)  # 10초마다 업데이트
        
        self._window_title_cache = {}
        self._cache_timeout = 1.0
        self._last_stats_update = 0
        self._stats_update_interval = 5  # 5초마다 통계 업데이트
        self._pending_updates = False  # UI 업데이트 최적화를 위한 플래그
        
        # 앱 종료 시 정리를 위한 변수
        self._is_shutting_down = False
        
        # 전체 앱에 다크 모드 스타일 적용
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
            QMenuBar {
                background-color: #2C2C2C;
                color: #FFFFFF;
            }
            QMenuBar::item:selected {
                background-color: #404040;
            }
            QMenu {
                background-color: #2C2C2C;
                color: #FFFFFF;
                border: 1px solid #404040;
            }
            QMenu::item:selected {
                background-color: #404040;
            }
        """)
        
        # 성능 최적화를 위한 변수 추가
        self._last_window_check = 0
        self._window_check_interval = 0.5  # 0.5초 간격으로 제한
    def initUI(self):
        self.setWindowTitle('타임좌')
        self.setFixedSize(1024, 1024)
        # WindowStaysOnTopHint 플래그 제거
        # self.setWindowFlags(Qt.WindowStaysOnTopHint)  
        
        menubar = self.menuBar()
        timer_menu = menubar.addMenu('Menu')
        
        show_timer_action = QAction('Timer', self)
        show_home_action = QAction('Home', self)
        self.work1_menu = QMenu('Work1', self)
        
        show_timer_action.triggered.connect(self.show_timer)
        show_home_action.triggered.connect(self.show)
        
        timer_menu.addAction(show_timer_action)
        timer_menu.addAction(show_home_action)
        
        timer_menu.addMenu(self.work1_menu)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.addWidget(self.home_widget)
    def create_status_bar_menu(self):
        menu = Cocoa.NSMenu.alloc().init()
        
        home_item = Cocoa.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Home", "showHome:", "")
        home_item.setTarget_(self)
        menu.addItem_(home_item)
        
        timer_item = Cocoa.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Timer", "showTimer:", "")
        timer_item.setTarget_(self)
        menu.addItem_(timer_item)
        
        work1_submenu = Cocoa.NSMenu.alloc().initWithTitle_("Work1")
        work1_item = Cocoa.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Work1", "", "")
        work1_item.setSubmenu_(work1_submenu)
        menu.addItem_(work1_item)
        
        quit_item = Cocoa.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit", "quitApp:", "")
        quit_item.setTarget_(self)
        menu.addItem_(quit_item)
        
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
        self.time_track_widget.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.time_track_widget.show()
    def update_app_list(self):
        self.running_apps = set()
        for app in NSWorkspace.sharedWorkspace().runningApplications():
            if app.activationPolicy() == NSApplicationActivationPolicyRegular:
                app_name = app.localizedName()
                if app_name and app_name not in self.running_apps:
                    self.running_apps.add(app_name)
        
        self.work1_menu.clear()
        work1_submenu = self.status_bar_controller.menu.itemWithTitle_("Work1").submenu()
        work1_submenu.removeAllItems()
        
        for app in sorted(self.running_apps):
            action = QAction(app, self)
            action.triggered.connect(lambda checked, a=app: self.select_app(a))
            action.setCheckable(True)
            action.setChecked(app == self.current_app)
            self.work1_menu.addAction(action)
            
            item = Cocoa.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(app, "selectApp:", "")
            item.setTarget_(self)
            item.setRepresentedObject_(app)
            work1_submenu.addItem_(item)
    @objc.python_method
    def selectApp_(self, sender):
        app_name = sender.representedObject()
        self.select_app(app_name)
    def select_app(self, app_name):
        self.current_app = app_name
        self.start_tracking()
        self.update_app_list()
    def start_tracking(self):
        if self.current_app:
            self.update_time_display()
            self.time_track_widget.time_frame.setStyleSheet("""
                QFrame {
                    background-color: #CCE5FF;
                    border-radius: 4px;
                    padding: 5px;
                }
            """)
    def update_time(self):
        if self._is_shutting_down:
            return
            
        try:
            current_time = time.time()
            
            # 활성 앱 정보 가져오기를 최적화
            active_app = NSWorkspace.sharedWorkspace().activeApplication()
            if not active_app:
                return
                
            app_name = active_app['NSApplicationName']
            
            # 불필요한 window title 검사 최소화
            if self.current_app != app_name or \
               current_time - self._last_window_check >= self._window_check_interval:
                current_window = self.get_active_window_title(app_name)
            else:
                current_window = self.app_usage.get(app_name, {}).get('last_window', "Untitled")
            
            # 새로운 앱이거나 처음 실행된 경우
            if app_name not in self.app_usage:
                self.app_usage[app_name] = {
                    'total_time': 0,
                    'windows': {},
                    'last_window': current_window,
                    'last_update': current_time,
                    'is_active': True
                }
            
            app_data = self.app_usage[app_name]
            
            # 앱이 활성 상태일 때만 시간 누적
            if app_data.get('is_active', True):
                time_diff = current_time - app_data['last_update']
                
                # 전체 앱 시간 업데이트
                app_data['total_time'] += time_diff
                
                # 현재 창/탭 시간 업데이트
                if current_window:
                    if current_window not in app_data['windows']:
                        app_data['windows'][current_window] = 0
                    app_data['windows'][current_window] += time_diff
            
            # 다른 앱들은 비활성 상태로 표시
            for other_app in self.app_usage:
                if other_app != app_name:
                    self.app_usage[other_app]['is_active'] = False
            
            # 현재 앱을 활성 상태로 표시
            app_data['is_active'] = True
            app_data['last_window'] = current_window
            app_data['last_update'] = current_time
            
            # UI 업데이트 최적화
            if not self._pending_updates:
                self._pending_updates = True
                QTimer.singleShot(1000, self._delayed_ui_update)
                
        except Exception as e:
            print(f"Error in update_time: {e}")

    def _delayed_ui_update(self):
        if not self._is_shutting_down:
            self.update_time_display()
            self.update_usage_stats()
            self._pending_updates = False

    def update_usage_stats(self):
        # TimeTracker에서는 home_app_tracking의 update_usage_stats를 직접 호
        if hasattr(self.home_widget, 'home_app_tracking'):
            self.home_widget.home_app_tracking.update_usage_stats()
    def _update_window_title(self, app_name, time_diff):
        if self._is_shutting_down:
            return
        
        current_window = self.get_active_window_title(app_name)
        if current_window and app_name in self.app_usage:
            app_data = self.app_usage[app_name]
            if current_window not in app_data['windows']:
                app_data['windows'][current_window] = 0
            app_data['windows'][current_window] += time_diff
            app_data['last_window'] = current_window
    def get_active_window_title(self, app_name):
        current_time = time.time()
        
        # 캐시 확인 및 요청 빈도 제한
        if app_name in self._window_title_cache:
            cached_time, cached_title = self._window_title_cache[app_name]
            if current_time - cached_time < self._cache_timeout:
                return cached_title
            
            # 너무 빈번한 요청 방지
            if current_time - self._last_window_check < self._window_check_interval:
                return cached_title

        self._last_window_check = current_time

        try:
            # AppleScript 실행을 최적화된 버전으로 변경
            script = f'''
                tell application "System Events"
                    set frontApp to first application process whose frontmost is true
                    if name of frontApp is "{app_name}" then
                        try
                            return name of window 1 of process "{app_name}"
                        end try
                    end if
                end tell
            '''
            
            p = Popen(['osascript', '-e', script], stdout=PIPE, stderr=PIPE)
            try:
                out, err = p.communicate(timeout=0.5)  # 타임아웃 시간 더 단축
                
                if p.returncode == 0 and out:
                    title = out.decode('utf-8').strip()
                    if title:
                        self._window_title_cache[app_name] = (current_time, title)
                        return title
                
            except TimeoutExpired:
                p.kill()
                if app_name in self._window_title_cache:
                    return self._window_title_cache[app_name][1]
                
            except Exception as e:
                print(f"Error in AppleScript execution: {e}")
            
            # 캐시된 값이 있으면 반환
            if app_name in self._window_title_cache:
                return self._window_title_cache[app_name][1]
            
            return "Untitled"
                
        except Exception as e:
            print(f"Error getting window title for {app_name}: {e}")
            if app_name in self._window_title_cache:
                return self._window_title_cache[app_name][1]
            return "Untitled"

    def update_time_display(self):
        if self.current_app in self.app_usage:
            total_time = self.app_usage[self.current_app]['total_time']
            hours = int(total_time // 3600)
            minutes = int((total_time % 3600) // 60)
            seconds = int(total_time % 60)
            
            # 현재 활성 창/탭 정보 표시
            current_window = self.get_active_window_title(self.current_app)
            window_time = self.app_usage[self.current_app]['windows'].get(current_window, 0)
            window_hours = int(window_time // 3600)
            window_minutes = int((window_time % 3600) // 60)
            window_seconds = int(window_time % 60)
            
            # 시간 표시 업데이
            time_text = f"Total: {hours:02d}:{minutes:02d}:{seconds:02d}\n"
            time_text += f"Current: {window_hours:02d}:{window_minutes:02d}:{window_seconds:02d}\n"
            time_text += f"Window: {current_window}"
            
            self.time_track_widget.time_label.setText(time_text)
            self.status_bar_controller.updateTime_(time_text)
    def closeEvent(self, event):
        if self._is_shutting_down:
            event.ignore()
            return
        
        # 즉시 UI 관련 작업 처리
        self.hide()
        self.time_track_widget.hide()
        
        # 타이머 정지
        self.timer.stop()
        self.app_update_timer.stop()
        
        # 비동기 정리 작업 예약
        QTimer.singleShot(0, self._cleanup_resources)
        QTimer.singleShot(100, self._set_shutdown_flag)
        
        event.ignore()

    def _cleanup_resources(self):
        # 캐시 정리를 비동기로 처리
        self._window_title_cache.clear()
        
        if hasattr(self.home_widget, 'home_app_tracking'):
            home_tracking = self.home_widget.home_app_tracking
            if hasattr(home_tracking, '_widgets_cache'):
                home_tracking._widgets_cache.clear()

    def _set_shutdown_flag(self):
        self._is_shutting_down = True
if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        
        tracker = TimeTracker()
        tracker.show()
        
        sys.exit(app.exec_())
    except Exception as e:
        print(f"Error occurred: {e}") #커밋용 헤헷
