import time as time_module
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QPushButton, QLabel, QApplication)
from PyQt5.QtCore import Qt, QTimer, QSettings
from PyQt5.QtGui import QFont
import os
import json

from core.config import *
from core.data_manager import DataManager
from core.app_tracker import AppTracker
from core.timer_manager import TimerManager
from ui.ui_controller import UIController

from ui.widgets.home_widget import HomeWidget
from ui.widgets.timer_widget import TimerWidget
from AppKit import NSWorkspace, NSApplicationActivationPolicyRegular
import datetime
import objc
import Cocoa
from concurrent.futures import ThreadPoolExecutor
from functools import partial

class TimerKing(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_QuitOnClose, False)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        
        # 초기화 플래그
        self._is_shutting_down = False
        self._initialization_complete = False
        
        # 데이터 매니저 초기화
        self.data_manager = DataManager.get_instance()
        
        # UI 초기화
        self.initUI()
        
        # 앱 트래커 초기화 (앱 추적 로직 담당)
        self.app_tracker = AppTracker(self.data_manager)
        
        # 타이머 매니저 초기화 (타이머 로직 담당)
        self.timer_manager = TimerManager(self.data_manager)
        
        # UI 컨트롤러 초기화 (UI 관련 로직 담당)
        self.ui_controller = UIController(
            self, 
            self.home_widget, 
            self.time_track_widget,
            self.timer_manager, 
            self.app_tracker
        )
        
        # 비동기 초기화 시작
        self._start_async_initialization()
        
    def closeEvent(self, event):
        """앱이 종료될 때 호출됩니다."""
        if not self._is_shutting_down:
            self._is_shutting_down = True
            self._save_all_data()
            self.ui_controller.cleanup()
        event.accept()
    
    def _save_all_data(self):
        """모든 데이터를 저장하고 종료 준비를 합니다."""
        try:
            print("앱 종료 중... 데이터 저장")
            
            # 모든 데이터 저장
            self.ui_controller.save_all_data()
            
            # 저장 확인
            if os.path.exists(APP_USAGE_FILE):
                print(f"데이터 파일 저장됨: {APP_USAGE_FILE}")
                print(f"파일 크기: {os.path.getsize(APP_USAGE_FILE)} bytes")
            
            print("데이터 저장 완료")
            
        except Exception as e:
            print(f"앱 종료 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()

    def _start_async_initialization(self):
        """비동기적으로 앱 초기화를 수행합니다."""
        self.async_timer = QTimer(self)
        self.async_timer.timeout.connect(self._async_init_step)
        self.async_timer.start(500)  # 500ms로 설정
        self._init_step = 0
        
    def _async_init_step(self):
        """초기화 단계를 순차적으로 실행합니다."""
        if self._init_step == 0:
            # 기본 타이머 데이터 로드
            timer_data = self.data_manager.load_timer_data()
            self.timer_manager.timer_data = timer_data
            self._init_step += 1
            
        elif self._init_step == 1:
            # 최근 사용 데이터만 로드
            recent_usage = self.data_manager.load_recent_app_usage()
            if recent_usage:
                self.app_tracker.app_usage.update(recent_usage)
            self._init_step += 1
            
        elif self._init_step == 2:
            # 앱 리스트 초기 업데이트
            self.ui_controller.update_app_list()
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
                self.app_tracker.app_usage.update(full_usage)
        except Exception as e:
            print(f"데이터 로딩 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()

    def initUI(self):
        """UI 컴포넌트를 초기화합니다."""
        self.setWindowTitle('타임 트래커')
        self.setFixedSize(1024, 1024)
        
        # 기본 위젯 초기화
        self.home_widget = HomeWidget(self)
        self.time_track_widget = TimerWidget()
        
        # 중앙 위젯 설정
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.addWidget(self.home_widget)
        
        # Timer 위젯 설정 (창 옵션만 설정, 이벤트는 UIController에서 처리)
        self.time_track_widget.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        
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

    def __del__(self):
        """소멸자에서 스레드 풀 정리"""
        if hasattr(self, 'thread_pool'):
            self.thread_pool.shutdown(wait=False)
            
        # 모든 데이터 저장
        self._save_all_data()