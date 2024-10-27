# 필요한 라이브러리 임포트
import sys
import time
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QFrame, QMenu, QAction, QPushButton, 
                            QScrollArea, QMainWindow)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont
from AppKit import NSWorkspace, NSApplicationActivationPolicyRegular
import Cocoa
import objc
from subprocess import Popen, PIPE
from Foundation import NSURL, NSString

class StatusBarController(Cocoa.NSObject):
    """
    맥OS의 상태바(메뉴바)를 제어하는 클래스
    시간 추적 정보를 상태바에 표시
    """
    def init(self):
        # 상태바 컨트롤러 초기화
        self = objc.super(StatusBarController, self).init()
        if self is None:
            return None
        self._setup_status_item()
        self._setup_custom_view()
        return self

    def _setup_status_item(self):
        # 상태바 아이템 설정
        self.statusItem = Cocoa.NSStatusBar.systemStatusBar().statusItemWithLength_(
            Cocoa.NSVariableStatusItemLength)
        self.statusItem.setHighlightMode_(True)

    def _setup_custom_view(self):
        # 상태바에 표시될 커스텀 뷰 설정
        self.custom_view = Cocoa.NSView.alloc().initWithFrame_(Cocoa.NSMakeRect(0, 0, 90, 22))
        
        # 시계 아이콘 설정
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
        
        # 시간 표시 레이블 설정
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
        # 상태바의 시간 표시를 업데이트
        self.time_label.setStringValue_(time_str)

    def draw_clock_icon(self):
        # 상태바에 표시될 시계 아이콘을 그리는 메서드
        width, height = 22, 22
        # 시계 외곽선 (검정)
        Cocoa.NSColor.blackColor().set()
        path = Cocoa.NSBezierPath.bezierPathWithOvalInRect_(Cocoa.NSMakeRect(1, 1, width-2, height-2))
        path.fill()
        # 시계 내부 (흰색)
        Cocoa.NSColor.whiteColor().set()
        path = Cocoa.NSBezierPath.bezierPathWithOvalInRect_(Cocoa.NSMakeRect(2, 2, width-4, height-4))
        path.fill()
        # 시계 바늘 (검정)
        Cocoa.NSColor.blackColor().set()
        path = Cocoa.NSBezierPath.bezierPath()
        path.moveToPoint_(Cocoa.NSMakePoint(width/2, height/2))
        path.lineToPoint_(Cocoa.NSMakePoint(width/2, height/2+7))  # 분침
        path.moveToPoint_(Cocoa.NSMakePoint(width/2, height/2))
        path.lineToPoint_(Cocoa.NSMakePoint(width/2+5, height/2))  # 시침
        path.setLineWidth_(2)
        path.stroke()

    def iconClicked_(self, sender):
        # 아이콘 클릭 시 메뉴 표시
        self.statusItem.popUpStatusItemMenu_(self.menu)

    def setMenu_(self, menu):
        # 상태바 메뉴 설정
        self.menu = menu

class HomeWidget(QWidget):
    """
    메인 창의 홈 화면을 구성하는 위젯
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)  # 전체 여백 설정
        
        # 홈 앱 트래킹 위젯 추가
        self.home_app_tracking = Home_app_tracking(self)
        
        # Quit 버튼 컨테이너 설정
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 10, 0, 0)  # 상단 여백만 추가
        
        # Quit 버튼 설정
        quit_button = QPushButton("Quit", self)
        quit_button.clicked.connect(QApplication.instance().quit)
        quit_button.setFixedWidth(100)  # 버튼 너비 고정
        
        # 버튼을 오른쪽에 배치
        button_layout.addStretch()
        button_layout.addWidget(quit_button)
        
        # 전체 레이아웃에 위젯들 추가
        layout.addWidget(self.home_app_tracking, 1)
        layout.addWidget(button_container)
        
        self.setLayout(layout)
        
        # 1초마다 시간 업데이트하는 타이머 설정
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)

    def update_time(self):
        if isinstance(self.parent(), TimeTracker):
            self.parent().update_time()

class Home_app_tracking(QWidget):
    """
    앱 사용 시간을 추적하고 표시하는 위젯
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Total 시간 표시 위젯 설정
        self.total_container = QWidget()
        total_layout = QHBoxLayout(self.total_container)
        
        self.total_label = QLabel("Total")
        self.total_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.total_time_label = QLabel("00:00:00")
        self.total_time_label.setFont(QFont("Arial", 16, QFont.Bold))
        
        total_layout.addWidget(self.total_label)
        total_layout.addStretch()
        total_layout.addWidget(self.total_time_label)
        
        # 구분선 설정
        self.separator_line = QFrame()
        self.separator_line.setFrameShape(QFrame.HLine)
        self.separator_line.setFrameShadow(QFrame.Sunken)
        
        # 레이아웃에 위젯 추가
        layout.addWidget(self.total_container)
        layout.addWidget(self.separator_line)
        
        # 앱별 사용 시간 표시를 위한 스크롤 영역 설정
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
        
        # 위젯 캐시 및 업데이트 타이머 설정
        self._widgets_cache = {}  # 앱별 위젯을 캐시하여 재사용
        self._layout_update_timer = QTimer()  # 레이아웃 업데이트를 위한 타이머
        self._layout_update_timer.setSingleShot(True)
        self._layout_update_timer.timeout.connect(self._update_layout)
        self._pending_updates = set()  # 업데이트가 필요한 앱 목록

    def _update_total_widget(self, total_all_apps):
        # 전체 사용 시간을 시:분:초 형식으로 변환하여 표시
        hours, remainder = divmod(int(total_all_apps), 3600)
        minutes, seconds = divmod(remainder, 60)
        self.total_time_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    def update_usage_stats(self):
        try:
            # 메인 윈도우 참조 가져오기
            main_window = self.window()
            if not isinstance(main_window, TimeTracker):
                return

            # 업데이트가 필요한 앱 목록 수집 (사용 시간이 0보다 큰 앱들)
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
            # 메인 윈도우 참조 가져오기
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
                        # 기존 위젯이 있으면 업데이트, 없으면 새로 생성
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

            # 더 이상 사용하지 않는 위젯 정리
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
        # TimeTracker 인스턴스인 경우에만 시간 업데이트 수행
        if isinstance(self.parent(), TimeTracker):
            self.parent().update_time()

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
        
        # 캐시 확인
        if app_name in self._window_title_cache:
            cached_time, cached_title = self._window_title_cache[app_name]
            if current_time - cached_time < self._cache_timeout:
                return cached_title

        try:
            script = f'''
                tell application "System Events"
                    tell process "{app_name}"
                        try
                            set frontWindow to first window whose focused is true
                            return name of frontWindow
                        on error
                            try
                                return name of front window
                            on error
                                return "Untitled"
                            end try
                        end try
                    end tell
                end tell
            '''
            
            # 타임아웃을 더 짧게 설정
            p = Popen(['osascript', '-e', script], stdout=PIPE, stderr=PIPE)
            out, err = p.communicate(timeout=1.0)  # 타임아웃을 1초로 감소
            
            if out:
                title = out.decode('utf-8').strip()
                self._window_title_cache[app_name] = (current_time, title)
                return title if title else "Untitled"
                
            return "Untitled"
        except Exception as e:
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
        print(f"Error occurred: {e}")

