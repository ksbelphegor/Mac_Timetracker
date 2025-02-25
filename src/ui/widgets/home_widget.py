from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QHBoxLayout, QApplication
from ui.widgets.app_tracking import Home_app_tracking
import os

class HomeWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # parent.our_pid 값을 전달
        our_pid = parent.our_pid if hasattr(parent, 'our_pid') else os.getpid()
        self.home_app_tracking = Home_app_tracking(self, our_pid)
        
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 10, 0, 0)
        
        close_button = QPushButton("Close", self)
        close_button.clicked.connect(self.parent().hide)
        close_button.setFixedWidth(100)
        
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        
        layout.addWidget(self.home_app_tracking, 1)
        layout.addWidget(button_container)