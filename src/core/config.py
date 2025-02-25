import os
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

# 앱 정보
APP_NAME = "Mac 타임좌"
BUNDLE_ID = "com.ksbelphegor.mactimetracker"
APP_VERSION = "1.0.0"

# 디렉토리 설정
HOME_DIR = str(Path.home())
DATA_DIR = os.path.expanduser("~/.mactimetracker")
APP_USAGE_FILE = os.path.join(DATA_DIR, 'app_usage.json')
TIMER_DATA_FILE = os.path.join(DATA_DIR, 'timer_data.json')
LOG_FILE = os.path.join(DATA_DIR, 'app.log')

# 캐시 설정
APP_CACHE_LIFETIME = 2.0  # 초
APP_LIST_UPDATE_INTERVAL = 10000  # 밀리초
TIME_UPDATE_INTERVAL = 1000  # 밀리초

# UI 설정
STATUS_BAR_WIDTH = 120
STATUS_BAR_HEIGHT = 22
ICON_SIZE = 20

# 데이터 보관 설정
DATA_RETENTION_DAYS = 30  # 기본값: 30일간 데이터 보관

# 공통 스타일시트
COMMON_STYLE = """
    QWidget {
        background-color: #1E1E1E;
        color: white;
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
    QComboBox {
        background-color: #2C2C2C;
        color: white;
        border: none;
        padding: 5px;
        border-radius: 3px;
    }
    QComboBox::drop-down {
        border: none;
    }
    QComboBox QAbstractItemView {
        background-color: #2C2C2C;
        color: white;
        selection-background-color: #404040;
        selection-color: white;
        border: none;
    }
"""

# 로깅 설정
def setup_logging():
    """로깅 시스템을 설정합니다."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            RotatingFileHandler(
                LOG_FILE,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=3,  # 최대 3개의 백업 파일 유지
                encoding='utf-8'
            ),
            logging.StreamHandler()
        ]
    )
