import sys
import time
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QFrame, QMenu, QAction, QPushButton, 
                            QScrollArea, QMainWindow, QTreeWidget, QTreeWidgetItem, QHeaderView)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont
from AppKit import NSWorkspace, NSApplicationActivationPolicyRegular  # 다시 추가
import Cocoa
import objc
from subprocess import Popen, PIPE, TimeoutExpired
import os

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
        button_layout = QHBoxLayout(button_container)  # QVBoxLayout에서 QHBoxLayout으 변경
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
        self.timer.start(3000)  # 3초로 변경
    def update_time(self):
        if isinstance(self.parent(), TimeTracker):
            self.parent().update_time()
class Home_app_tracking(QWidget): # Total 안쪽 영역
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # 시작 시간 및 업데이트 관련 변수 초기화
        self.start_time = time.time()
        self._last_update = time.time()
        self._update_interval = 3.0
        self._pending_updates = set()
        
        # 폰트 설정
        self.app_font = QFont("Arial", 14)
        self.window_font = QFont("Arial", 12)
        
        # 캐시 및 상태 변수 초기화
        self._widgets_cache = {}
        self._is_active = True
        self.MAX_ITEMS = 100
        
        # Total 시간
        self.total_container = QWidget()
        total_layout = QHBoxLayout(self.total_container)
        
        self.total_label = QLabel("Total")
        self.total_label.setFont(QFont("Arial", 20, QFont.Bold))
        self.total_time_label = QLabel("00:00:00")
        self.total_time_label.setFont(QFont("Arial", 20, QFont.Bold))
        
        total_layout.addWidget(self.total_label)
        total_layout.addStretch()
        total_layout.addWidget(self.total_time_label)
        
        # 트리 위젯 설정
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderHidden(False)
        self.tree_widget.setColumnCount(2)
        self.tree_widget.setHeaderLabels(["Name", "Time"])
        
        # 헤더 설정
        header = self.tree_widget.header()
        header.setSectionsMovable(True)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        
        # Name 열의 너비를 화면의 절반으로 설정 (약 512px)
        self.tree_widget.setColumnWidth(0, 512)  # 1024의 절반
        self.tree_widget.setColumnWidth(1, 200)  # Time 열은 적당한 크기로
        
        # 헤더와 아이템 폰트 크기 설정
        header_font = QFont("Arial", 17, QFont.Bold)  # 20 -> 17
        item_font = QFont("Arial", 15)  # 18 -> 15
        
        # 헤더 폰트 적용
        self.tree_widget.headerItem().setFont(0, header_font)
        self.tree_widget.headerItem().setFont(1, header_font)
        
        # 트리 위젯 스타일 설정
        self.tree_widget.setStyleSheet("""
            QTreeWidget {
                background-color: #1E1E1E;
                color: white;
                border: none;
                font-size: 15px;  /* 18 -> 15 */
            }
            QTreeWidget::item {
                padding: 8px;  /* 10 -> 8 */
                border-bottom: 1px solid #3C3C3C;
                height: 35px;  /* 40 -> 35 */
            }
            QTreeWidget::item:selected {
                background-color: #404040;
            }
            QHeaderView::section {
                background-color: #2C2C2C;
                color: white;
                padding: 10px;  /* 12 -> 10 */
                border: 1px solid #3C3C3C;
                font-size: 17px;  /* 20 -> 17 */
            }
            QHeaderView::section:hover {
                background-color: #404040;
            }
        """)
        
        # 레이아웃에 위젯 추가
        layout.addWidget(self.total_container)
        layout.addWidget(self.tree_widget)
        
        # 타이머 설정
        self.total_timer = QTimer(self)
        self.total_timer.timeout.connect(self.update_total_time)
        self.total_timer.start(1000)
        
        # 레이아웃 업데이트 타이
        self._layout_update_timer = QTimer(self)
        self._layout_update_timer.timeout.connect(self._update_layout)
        self._layout_update_timer.setSingleShot(True)
        
        # 캐시 초기화
        self._widgets_cache = {}
        self._is_active = True
        self.MAX_ITEMS = 100
        
        # 창 활성화 상태 추적
        self._is_active = True
        
    def showEvent(self, event):
        self._is_active = True
        super().showEvent(event)
        
    def hideEvent(self, event):
        self._is_active = False
        super().hideEvent(event)

    def update_usage_stats(self):
        if not self._is_active:
            return
            
        current_time = time.time()
        if current_time - self._last_update < self._update_interval:
            return

        try:
            main_window = self.window()
            if not isinstance(main_window, TimeTracker):
                return

            # 상위/하위 아이템 폰트 설정
            parent_font = QFont("Arial", 17)
            child_font = QFont("Arial", 16)
            
            for app_name, app_data in main_window.app_usage.items():
                if app_data['total_time'] > 0:
                    # 최상위 아이템 생성 또는 가져오기
                    app_item = self._get_or_create_item(app_name)
                    app_item.setFont(0, parent_font)
                    app_item.setFont(1, parent_font)
                    
                    # 앱의 총 시간 계산 및 설정
                    total_time = sum(app_data['windows'].values())
                    hours = int(total_time // 3600)
                    minutes = int((total_time % 3600) // 60)
                    seconds = int(total_time % 60)
                    time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    app_item.setText(1, time_str)  # 앱 총 시간 설정
                    
                    # 하위 윈도우 아이템 처리
                    for window_name, window_time in app_data['windows'].items():
                        window_item = self._get_or_create_window_item(app_item, window_name)
                        window_item.setFont(0, child_font)
                        window_item.setFont(1, child_font)
                        
                        # 윈도우 시간 포맷팅 및 설정
                        w_hours = int(window_time // 3600)
                        w_minutes = int((window_time % 3600) // 60)
                        w_seconds = int(window_time % 60)
                        w_time_str = f"{w_hours:02d}:{w_minutes:02d}:{w_seconds:02d}"
                        window_item.setText(1, w_time_str)

            self._last_update = current_time

        except Exception as e:
            print(f"Error in update_usage_stats: {e}")

    def _update_layout(self):
        if not self._is_active:
            return

        try:
            main_window = self.window()
            if not isinstance(main_window, TimeTracker):
                return

            self.tree_widget.setUpdatesEnabled(False)

            # 가장 많이 사용된 앱 순으로 정렬
            sorted_apps = sorted(
                ((name, data) for name, data in main_window.app_usage.items() 
                 if data['total_time'] > 0),
                key=lambda x: x[1]['total_time'],
                reverse=True
            )[:self.MAX_ITEMS]

            # 현재 표시된 항목 추적
            current_items = set()

            for app_name, app_data in sorted_apps:
                current_items.add(app_name)
                
                # 기존 아템 재사용 또는 새로 생성
                app_item = self._widgets_cache.get(app_name)
                if not app_item:
                    app_item = QTreeWidgetItem()
                    self.tree_widget.addTopLevelItem(app_item)
                    self._widgets_cache[app_name] = app_item

                # 앱 정보 업데이트
                app_item.setText(0, app_name)
                
                # 앱의 총 시간 계산 (모든 윈도우/탭 시간의 합)
                total_time = sum(app_data['windows'].values())
                hours, remainder = divmod(int(total_time), 3600)
                minutes, seconds = divmod(remainder, 60)
                app_item.setText(1, f"{hours:02d}:{minutes:02d}:{seconds:02d}")

                # 앱 아이템 폰트 설정
                app_item.setFont(0, self.app_font)
                app_item.setFont(1, self.app_font)
                
                # 윈도우 항목 제한 및 재사용
                if 'windows' in app_data:
                    window_items = sorted(
                        app_data['windows'].items(),
                        key=lambda x: x[1],
                        reverse=True
                    )[:10]  # 최대 10개의 윈도우만 표시

                    while app_item.childCount() > len(window_items):
                        app_item.removeChild(app_item.child(app_item.childCount() - 1))

                    for i, (window_title, window_time) in enumerate(window_items):
                        if window_time > 0:
                            if i < app_item.childCount():
                                window_item = app_item.child(i)
                            else:
                                window_item = QTreeWidgetItem(app_item)

                            window_item.setText(0, window_title)
                            w_hours, w_remainder = divmod(int(window_time), 3600)
                            w_minutes, w_seconds = divmod(w_remainder, 60)
                            window_item.setText(1, f"{w_hours:02d}:{w_minutes:02d}:{w_seconds:02d}")

                            # 창 아이템 폰트 설정
                            window_item.setFont(0, self.window_font)
                            window_item.setFont(1, self.window_font)

            # 사용하지 않는 항목 제거
            for app_name in list(self._widgets_cache.keys()):
                if app_name not in current_items:
                    item = self._widgets_cache.pop(app_name)
                    index = self.tree_widget.indexOfTopLevelItem(item)
                    if index >= 0:
                        self.tree_widget.takeTopLevelItem(index)

            self.tree_widget.setUpdatesEnabled(True)

        except Exception as e:
            print(f"Error in _update_layout: {e}")
            self.tree_widget.setUpdatesEnabled(True)

    def update_total_time(self):
        # 프로그램 실행 시간 계산
        elapsed_time = time.time() - self.start_time
        hours, remainder = divmod(int(elapsed_time), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        # Total 시간 업데이트
        self.total_time_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    def _get_or_create_item(self, app_name):
        # 기존 아이템 찾기
        for i in range(self.tree_widget.topLevelItemCount()):
            item = self.tree_widget.topLevelItem(i)
            if item.text(0) == app_name:
                return item
        
        # 새 아이템 생성
        item = QTreeWidgetItem([app_name])
        self.tree_widget.addTopLevelItem(item)
        
        # 폰트 설정
        item_font = QFont("Arial", 15)  # 18 -> 15
        item.setFont(0, item_font)
        item.setFont(1, item_font)
        
        return item

    def _get_or_create_window_item(self, parent_item, window_name):
        # 기존 하위 아이템 찾기
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.text(0) == window_name:
                return child
        
        # 새 하위 아이템 생성
        child = QTreeWidgetItem([window_name])
        parent_item.addChild(child)
        
        # 폰트 설정
        item_font = QFont("Arial", 15)  # 18 -> 15
        child.setFont(0, item_font)
        child.setFont(1, item_font)
        
        return child

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
        
        self.running_apps = set()
        self.app_usage = {}
        self.current_app = None
        self.last_update_time = time.time()
        
        self.status_bar_controller = StatusBarController.alloc().init()
        self.create_status_bar_menu()
        
        self.home_widget = HomeWidget(self)
        self.time_track_widget = TimeTrackWidget()
        
        self.initUI()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)
        
        self.app_update_timer = QTimer(self)
        self.app_update_timer.timeout.connect(self.update_app_list)
        self.app_update_timer.start(10000)
        
        self._window_title_cache = {}
        self._pending_updates = False
        self._is_shutting_down = False
        
        # 스타일시트 설정 유지
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
        
        self.start_time = time.time()
    
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
        try:
            current_time = time.time()
            active_app = NSWorkspace.sharedWorkspace().activeApplication()
            
            if not active_app:
                return
                
            app_name = active_app['NSApplicationName']
            active_pid = active_app['NSApplicationProcessIdentifier']
            active_bundle_id = active_app['NSApplicationBundleIdentifier']
            
            # 현재 창이 맥 타임좌인 경우 추가
            if self.isActiveWindow():
                app_name = "맥 타임좌"
                active_pid = os.getpid()  # 현재 프로세스 ID
                active_bundle_id = "com.mactimeja.app"  # 임의의 번들 ID
                current_window = "Home"  # 홈 창 이름
            else:
                # 기존 창/탭 정보 가져오기
                current_window = self.get_active_window_title(app_name)
            
            # Loading 상태면 시간 기록하지 않음
            if current_window == "Loading...":
                if app_name in self.app_usage:
                    self.app_usage[app_name]['last_update'] = current_time
                return
            
            # 새로운 앱이거나 처음 실행된 경우
            if app_name not in self.app_usage:
                self.app_usage[app_name] = {
                    'total_time': 0,
                    'windows': {},
                    'last_window': None,
                    'last_update': current_time,
                    'is_active': True,
                    'pid': active_pid,
                    'bundle_id': active_bundle_id
                }
            
            app_data = self.app_usage[app_name]
            
            # 시간 차이 계산 및 기록
            time_diff = current_time - app_data['last_update']
            if time_diff > 0 and time_diff <= 3.5:  # 타머 간격(3초)보다 약간 더 큰 값으로 제한
                # 탭 시간 업데이트
                if current_window not in app_data['windows']:
                    app_data['windows'][current_window] = 0
                app_data['windows'][current_window] += time_diff
                
                # 앱 전체 시간은 탭 시간들의 합으로 계산
                app_data['total_time'] = sum(app_data['windows'].values())
                
                app_data['last_window'] = current_window
            
            app_data['last_update'] = current_time
            
            # UI 업데이트
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
            if time_diff <= 3.5:  # 여기도 제한 추가
                app_data['windows'][current_window] += time_diff
            app_data['last_window'] = current_window
    def get_active_window_title(self, app_name):
        current_time = time.time()
        
        try:
            active_app = NSWorkspace.sharedWorkspace().activeApplication()
            if not active_app:
                return "Loading..."
            
            active_pid = active_app['NSApplicationProcessIdentifier']
            active_bundle_id = active_app['NSApplicationBundleIdentifier']
            
            if app_name in self.app_usage:
                app_data = self.app_usage[app_name]
                if 'bundle_id' not in app_data:
                    app_data['bundle_id'] = active_bundle_id
                elif app_data['bundle_id'] != active_bundle_id:
                    return "Loading..."
            
            script = f'''
                tell application "System Events"
                    set pidStr to "{active_pid}"
                    set pidNum to (pidStr as number)
                    set targetProcess to first process whose unix id is pidNum
                    try
                        set windowList to windows of targetProcess
                        repeat with windowItem in windowList
                            if value of attribute "AXMain" of windowItem is true then
                                return name of windowItem
                            end if
                        end repeat
                    end try
                end tell
            '''
            
            p = Popen(['osascript', '-e', script], stdout=PIPE, stderr=PIPE)
            try:
                out, err = p.communicate(timeout=0.3)
                
                if p.returncode == 0 and out:
                    title = out.decode('utf-8').strip()
                    if title:
                        self._window_title_cache[app_name] = {
                            'time': current_time,
                            'title': title,
                            'pid': active_pid,
                            'bundle_id': active_bundle_id
                        }
                        return title
            
                return "Loading..."
            
            except TimeoutExpired:
                p.kill()
                return "Loading..."
            
        except Exception as e:
            print(f"Error getting window title: {e}")
            return "Loading..."

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
        
        # 1. 모든 타이머 정지
        self.timer.stop()
        self.app_update_timer.stop()
        
        # 2. 메모리에 있는 데이터 정리
        self._window_title_cache.clear()  # 창 제목 캐시 정리
        self.app_usage.clear()           # 앱 사용 데이터 정리
        
        # 3. UI 요소 숨기기
        self.hide()
        self.time_track_widget.hide()
        
        # 4. 비동기 정리 작업
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












