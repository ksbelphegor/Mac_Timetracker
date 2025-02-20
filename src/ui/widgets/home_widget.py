from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QHBoxLayout, QApplication
from ui.widgets.app_tracking import Home_app_tracking

class HomeWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        self.home_app_tracking = Home_app_tracking(self)
        
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 10, 0, 0)
        
        quit_button = QPushButton("Quit", self)
        quit_button.clicked.connect(QApplication.instance().quit)
        quit_button.setFixedWidth(100)
        
        button_layout.addStretch()
        button_layout.addWidget(quit_button)
        
        layout.addWidget(self.home_app_tracking, 1)
        layout.addWidget(button_container)