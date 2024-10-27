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
from subprocess import Popen, PIPE
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
        
        # 상단 여백 추가
        layout.addSpacing(20)
        
        # 시간 추적 위젯을 왼쪽 아래에 배치하기 위한 컨테이너
        bottom_container = QWidget(self)
        bottom_layout = QHBoxLayout(bottom_container)
        
        # 홈 앱 트래킹 위젯의 크기 조정
        self.home_app_tracking = Home_app_tracking(self)
        self.home_app_tracking.setMaximumSize(450, 400)  # 가로 크기를 450으로, 세로를 400으로 증가
        
        # 왼쪽 정렬을 위한 레이아웃 조정
        bottom_layout.addWidget(self.home_app_tracking)
        bottom_layout.addStretch()  # 오른쪽 여백을 위한 stretch
        
        # Quit 버튼도 함께 배치
        button_container = QWidget()
        button_layout = QVBoxLayout(button_container)
        quit_button = QPushButton("Quit", self)
        quit_button.clicked.connect(QApplication.instance().quit)
        button_layout.addWidget(quit_button)
        button_layout.addStretch()
        
        # 전체 레이아웃에 추가
        layout.addStretch()  # 상단 여백을 위한 stretch
        layout.addWidget(bottom_container)
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
        layout.setContentsMargins(15, 15, 15, 15)  # 여백을 약간 증가
        
        self.usage_stats_label = QLabel("Home", self)
        self.usage_stats_label.setFont(QFont("Arial", 22, QFont.Bold))  # 폰트 크기 약간 증가
        layout.addWidget(self.usage_stats_label)
        
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
        self.usage_stats_layout.setSpacing(8)  # 간격 조정
        self.usage_stats_area.setWidget(self.usage_stats_widget)
        self.usage_stats_area.setWidgetResizable(True)
        
        layout.addWidget(self.usage_stats_area)
        self.setLayout(layout)

    def update_usage_stats(self):
        try:
            main_window = self.window()
            if not isinstance(main_window, TimeTracker):
                return

            # 기존 위젯들을 한 번에 제거
            for i in reversed(range(self.usage_stats_layout.count())): 
                self.usage_stats_layout.itemAt(i).widget().deleteLater()

            # Total 시간 계산 및 표시
            total_all_apps = sum(app_data['total_time'] for app_data in main_window.app_usage.values())
            hours, remainder = divmod(int(total_all_apps), 3600)
            minutes, seconds = divmod(remainder, 60)
            
            total_container = QWidget()
            total_layout = QHBoxLayout(total_container)
            
            total_label = QLabel("Total")
            total_label.setFont(QFont("Arial", 16, QFont.Bold))
            total_time_label = QLabel(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            total_time_label.setFont(QFont("Arial", 16, QFont.Bold))
            
            total_layout.addWidget(total_label)
            total_layout.addStretch()
            total_layout.addWidget(total_time_label)
            
            self.usage_stats_layout.addWidget(total_container)
            
            # 구분선 추가
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            self.usage_stats_layout.addWidget(line)

            # 기존의 앱별 통�� 표시 코드
            widgets_to_add = []
            for app_name, app_data in sorted(main_window.app_usage.items(), 
                                          key=lambda x: x[1]['total_time'], reverse=True):
                app_container = QWidget()
                app_container.setAttribute(Qt.WA_StyledBackground, True)  # 성능 최적화
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
                total_time_label.setFont(QFont("Arial", 14))
                
                header_layout.addWidget(app_name_label)
                header_layout.addStretch()
                header_layout.addWidget(total_time_label)
                
                app_layout.addWidget(header)
                
                # 탭/창 정보 추가
                if 'windows' in app_data:
                    for window_title, window_time in sorted(app_data['windows'].items(), 
                                                          key=lambda x: x[1], reverse=True):
                        w_hours, w_remainder = divmod(int(window_time), 3600)
                        w_minutes, w_seconds = divmod(w_remainder, 60)
                        
                        window_container = QWidget()
                        window_layout = QHBoxLayout(window_container)
                        window_layout.setContentsMargins(20, 0, 0, 0)  # 왼쪽 여백을 주어 계층 구조 표시
                        
                        window_name_label = QLabel(window_title)
                        window_name_label.setFont(QFont("Arial", 12))
                        window_time_label = QLabel(f"{w_hours:02d}:{w_minutes:02d}:{w_seconds:02d}")
                        window_time_label.setFont(QFont("Arial", 12))
                        
                        window_layout.addWidget(window_name_label)
                        window_layout.addStretch()
                        window_layout.addWidget(window_time_label)
                        
                        app_layout.addWidget(window_container)
                
                widgets_to_add.append(app_container)

            # 준비된 위젯들을 한 번에 추가
            for widget in widgets_to_add:
                self.usage_stats_layout.addWidget(widget)

            # 레이아웃 업데이트를 한 번만 수행
            self.usage_stats_layout.update()
            
        except Exception as e:
            print(f"Error in Home_app_tracking.update_usage_stats: {e}")

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
        
        # 필수 타이머만 유
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)

        self.app_update_timer = QTimer(self)
        self.app_update_timer.timeout.connect(self.update_app_list)
        self.app_update_timer.start(10000)

    def initUI(self):
        self.setWindowTitle('타임좌')
        self.setFixedSize(1024, 1024)  # 전체 크기를 1024x1024로 증가
        self.setWindowFlags(Qt.WindowStaysOnTopHint)

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
            
            if active_app:
                app_name = active_app['NSApplicationName']
                
                # 앱이 실행 중인 목록에 없으면 추가
                if app_name not in self.running_apps:
                    self.running_apps.add(app_name)
                
                # 앱 사 시간 데이 구조 초기화
                if app_name not in self.app_usage:
                    self.app_usage[app_name] = {
                        'total_time': 0,
                        'windows': {},
                        'last_window': None,
                        'last_update': current_time
                    }
                
                # 재 활성 창/탭 정보 가져오기
                current_window = self.get_active_window_title(app_name)
                
                # 창/탭 데이터 구조 초기화
                if current_window and current_window not in self.app_usage[app_name]['windows']:
                    self.app_usage[app_name]['windows'][current_window] = 0
                
                time_diff = current_time - self.app_usage[app_name]['last_update']
                
                # 앱 전체 시간 업데이트
                self.app_usage[app_name]['total_time'] += time_diff
                
                # 이전 창/탭의 시간 업데이트
                last_window = self.app_usage[app_name]['last_window']
                if last_window and last_window in self.app_usage[app_name]['windows']:
                    self.app_usage[app_name]['windows'][last_window] += time_diff
                
                # 현재 창/탭 정보 업데이트
                self.app_usage[app_name]['last_window'] = current_window
                self.app_usage[app_name]['last_update'] = current_time
                
                # UI 업데이트
                self.update_time_display()
                self.update_usage_stats()  # 여기서 home_app_tracking의 update_usage_stats가 호출됨
                
        except Exception as e:
            print(f"Error in update_time: {e}")

    def update_usage_stats(self):
        # TimeTracker에서는 home_app_tracking의 update_usage_stats를 직접 호
        if hasattr(self.home_widget, 'home_app_tracking'):
            self.home_widget.home_app_tracking.update_usage_stats()

    def get_active_window_title(self, app_name):
        try:
            if app_name == "Safari":
                script = '''
                    tell application "Safari"
                        set windowTitle to name of current tab of front window
                        return windowTitle
                    end tell
                '''
            elif app_name == "Obsidian":
                script = '''
                    tell application "System Events"
                        tell process "Obsidian"
                            set windowTitle to name of first window
                            return windowTitle
                        end tell
                    end tell
                '''
            elif app_name == "Cursor":
                script = '''
                    tell application "System Events"
                        tell process "Cursor"
                            set windowTitle to name of first window
                            if windowTitle contains " — " then
                                set AppleScript's text item delimiters to " — "
                                set fileName to first text item of windowTitle
                                return fileName
                            end if
                            return windowTitle
                        end tell
                    end tell
                '''
            elif app_name in ["Google Chrome", "Firefox"]:
                script = '''
                    tell application "%s"
                        get title of active tab of front window
                    end tell
                ''' % app_name
            else:
                script = '''
                    tell application "System Events"
                        tell process "%s"
                            set windowTitle to name of first window
                            return windowTitle
                        end tell
                    end tell
                ''' % app_name

            p = Popen(['osascript', '-e', script], stdout=PIPE, stderr=PIPE)
            out, err = p.communicate()
            
            if out:
                title = out.decode('utf-8').strip()
                return title if title else "Untitled"
            return "Untitled"

        except Exception as e:
            print(f"Error getting window title for {app_name}: {str(e)}")
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
        event.ignore()
        self.hide()

if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        
        tracker = TimeTracker()
        tracker.show()
        
        sys.exit(app.exec_())
    except Exception as e:
        print(f"Error occurred: {e}")
# 테스트 주석
# Updated version
