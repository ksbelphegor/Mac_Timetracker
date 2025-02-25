from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QMenu
from src.core.status_bar import StatusBarController
import objc
from AppKit import NSWorkspace, NSMenu, NSMenuItem, NSStatusBar
import logging
import os
import re

class UIController:
    """UI 관련 로직을 처리하는 클래스"""
    
    def __init__(self, main_window, home_widget, time_track_widget, timer_manager, app_tracker):
        """UIController 초기화"""
        self.main_window = main_window
        self.home_widget = home_widget
        self.time_track_widget = time_track_widget
        self.timer_manager = timer_manager
        self.app_tracker = app_tracker
        
        # StatusBarController 초기화
        self.status_bar_controller = StatusBarController.alloc().init()
        self.create_status_bar_menu()
        
        # 타이머 설정 (UI 업데이트용)
        self.timer = QTimer(main_window)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)  # 1초로 설정
        
        # 앱 업데이트 타이머
        self.app_update_timer = QTimer(main_window)
        self.app_update_timer.timeout.connect(self.update_app_list)
        self.app_update_timer.start(10000)  # 10초 유지
        
        # 자동 저장 타이머
        self.autosave_timer = QTimer(main_window)
        self.autosave_timer.timeout.connect(self.autosave_data)
        self.autosave_timer.start(30000)  # 30초마다 저장
        
        # UI 업데이트 최적화를 위한 변수
        self._last_ui_update = 0
        self._ui_update_interval = 0.5  # 0.5초 유지
        
        # 이벤트 연결
        self.connect_events()
    
    def connect_events(self):
        """이벤트 핸들러를 연결합니다."""
        # Timer 위젯 이벤트 연결
        self.time_track_widget.reset_button.clicked.connect(self.reset_timer)
        self.time_track_widget.app_combo.currentTextChanged.connect(self.on_app_selected)
    
    def create_status_bar_menu(self):
        """상태바 메뉴를 생성합니다."""
        # 상태바 메뉴 생성
        menu = NSMenu.alloc().init()
        
        # 홈 메뉴 항목
        home_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "홈", objc.selector(self.show_home_window_, signature=b'v@:'), "")
        menu.addItem_(home_item)
        
        # 타이머 메뉴 항목
        timer_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "타이머", objc.selector(self.show_timer_window_, signature=b'v@:'), "")
        menu.addItem_(timer_item)
        
        # 구분선
        menu.addItem_(NSMenuItem.separatorItem())
        
        # 종료 메뉴 항목
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "종료", objc.selector(self.quit_app_, signature=b'v@:'), "q")
        menu.addItem_(quit_item)
        
        # 메뉴 설정
        self.status_bar_controller.setMenu_(menu)
    
    def show_home_window_(self, sender):
        """홈 창을 표시합니다."""
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()
    
    def show_timer_window_(self, sender):
        """타이머 창을 표시합니다."""
        self.time_track_widget.show()
        self.time_track_widget.raise_()
        self.time_track_widget.activateWindow()
    
    def quit_app_(self, sender):
        """앱을 종료합니다."""
        # 앱 종료 전 모든 데이터 저장
        self.save_all_data()
        QApplication.quit()
    
    def save_all_data(self):
        """모든 데이터를 저장합니다."""
        # 앱 트래커의 사용 통계 업데이트
        self.app_tracker.update_usage_stats(self.timer_manager.timer_data)
        
        # 데이터 저장
        self.app_tracker.save_app_usage()
        self.timer_manager.save_timer_data()
    
    def update_time(self):
        """시간 표시를 업데이트합니다."""
        try:
            # 선택된 앱이 없으면 업데이트 안 함
            if not self.timer_manager.timer_data.get('app_name'):
                return
            
            # 현재 실행 중인 앱 확인
            app = NSWorkspace.sharedWorkspace().activeApplication()
            if not app:
                return
                
            app_name = app['NSApplicationName']
            is_selected_app_active = (app_name == self.timer_manager.timer_data['app_name'])
            
            # 타이머 상태 업데이트
            _, state_changed = self.timer_manager.update_timer_status(is_selected_app_active)
            
            # 상태가 변경된 경우 UI 스타일 업데이트
            if state_changed:
                if is_selected_app_active:
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
            
            # 시간 텍스트 가져오기
            time_text = self.timer_manager.get_formatted_time()
            
            # UI 업데이트
            self.status_bar_controller.update_time_display(time_text)
            self.time_track_widget.update_time_display(time_text)
            
            # 필요시 배치 업데이트 처리
            if self.timer_manager.should_process_updates():
                self.timer_manager._process_pending_updates()
                
        except Exception as e:
            print(f"시간 업데이트 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
    
    def update_app_list(self):
        """실행 중인 앱 목록을 업데이트합니다."""
        # 앱 트래커를 통해 앱 목록 업데이트
        running_apps = self.app_tracker.update_app_list()
        
        # Timer 창의 콤보박스 업데이트
        current_app = self.timer_manager.timer_data.get('app_name')
        self.time_track_widget.app_combo.blockSignals(True)
        self.time_track_widget.update_app_list(running_apps, current_app)
        self.time_track_widget.app_combo.blockSignals(False)
    
    def autosave_data(self):
        """데이터를 자동으로 저장합니다."""
        # 타이머 데이터 저장
        self.timer_manager.save_timer_data()
        
        # 앱 사용 통계 업데이트 및 저장
        self.app_tracker.update_usage_stats(self.timer_manager.timer_data)
        self.app_tracker.save_app_usage()
    
    def reset_timer(self):
        """타이머를 초기화합니다."""
        self.timer_manager.reset_timer()
        self.time_track_widget.update_time_display("00:00:00")
    
    def on_app_selected(self, app_name):
        """앱 선택 이벤트 처리"""
        if not app_name:
            return
            
        # 현재 실행 중인 앱인지 확인
        active_app = NSWorkspace.sharedWorkspace().activeApplication()
        is_target_app_active = active_app and active_app['NSApplicationName'] == app_name
        
        # 타이머 매니저에 앱 선택 알림
        self.timer_manager.select_app(app_name, is_target_app_active)
        
        # UI 업데이트
        self.time_track_widget.update_time_display("00:00:00")
        
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
    
    def cleanup(self):
        """리소스를 정리합니다."""
        # 타이머 중지
        if hasattr(self, 'timer'):
            self.timer.stop()
        if hasattr(self, 'app_update_timer'):
            self.app_update_timer.stop()
        if hasattr(self, 'autosave_timer'):
            self.autosave_timer.stop()
        
        # 상태바 컨트롤러 정리
        if hasattr(self, 'status_bar_controller') and self.status_bar_controller:
            # 상태바 아이템 제거
            try:
                NSStatusBar.systemStatusBar().removeStatusItem_(self.status_bar_controller.statusItem)
            except Exception as e:
                print(f"상태바 제거 중 오류 발생: {e}")
    
    def update_status_bar(self):
        """상태 표시줄을 업데이트합니다."""
        if self.status_bar:
            self.status_bar.update_display()
    
    def set_data_retention_period(self, days):
        """데이터 보관 기간을 설정합니다."""
        from src.core.config import DATA_RETENTION_DAYS
        
        # config.py 파일 경로
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'core', 'config.py')
        
        try:
            # config.py 파일 읽기
            with open(config_path, 'r') as f:
                config_content = f.read()
            
            # DATA_RETENTION_DAYS 값 업데이트
            updated_content = re.sub(
                r'DATA_RETENTION_DAYS\s*=\s*\d+',
                f'DATA_RETENTION_DAYS = {days}',
                config_content
            )
            
            # 파일 쓰기
            with open(config_path, 'w') as f:
                f.write(updated_content)
            
            # 앱 추적 위젯에서 오래된 데이터 정리
            if hasattr(self, 'app_tracking_widget') and self.app_tracking_widget:
                self.app_tracking_widget.cleanup_old_data(days)
                
            return True
        except Exception as e:
            logging.error(f"데이터 보관 기간 설정 중 오류 발생: {e}")
            return False 