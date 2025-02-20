from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                         QLabel, QFrame, QComboBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from core.data_manager import DataManager

class TimerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        layout.setSpacing(5)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 앱 선택 콤보박스 추가
        self.app_combo = QComboBox()
        self.app_combo.setStyleSheet("""
            QComboBox {
                background-color: #2C2C2C;
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
                min-width: 200px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid #2C2C2C;
                border-right: 5px solid #2C2C2C;
                border-top: 5px solid white;
                width: 0;
                height: 0;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background-color: #2C2C2C;
                color: white;
                selection-background-color: #404040;
                selection-color: white;
                border: none;
            }
        """)
        
        # 시간 프레임
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
        
        # 버튼 컨테이너 추가
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 5, 0, 0)
        
        # 초기화 버튼 추가
        self.reset_button = QPushButton("Reset Timer")
        self.reset_button.setStyleSheet("""
            QPushButton {
                background-color: #FF6B6B;
                color: white;
                border: none;
                padding: 5px 10px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #FF8787;
            }
            QPushButton:pressed {
                background-color: #FF4F4F;
            }
        """)
        button_layout.addWidget(self.reset_button)
        
        # 레이아웃에 위젯 추가
        layout.addWidget(self.app_combo)
        layout.addWidget(self.time_frame)
        layout.addWidget(button_container)
        self.setLayout(layout)
        
        # 창 크기 조정
        self.setFixedSize(250, 150)

    def update_app_list(self, apps, current_app=None):
        # 콤보박스 업데이트
        self.app_combo.clear()
        self.app_combo.addItem("Select App...")  # 기본 항목 추가
        for app in sorted(apps):
            self.app_combo.addItem(app)
        
        # 현재 선택된 앱이 있으면 선택
        if current_app:
            index = self.app_combo.findText(current_app)
            if index >= 0:
                self.app_combo.setCurrentIndex(index)

    def update_time_display(self, total_time):
        # 시간을 HH:MM:SS 형식으로 변환하여 표시
        if isinstance(total_time, str):
            self.time_label.setText(total_time)
        else:
            hours = int(total_time // 3600)
            minutes = int((total_time % 3600) // 60)
            seconds = int(total_time % 60)
            
            time_text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            self.time_label.setText(time_text)