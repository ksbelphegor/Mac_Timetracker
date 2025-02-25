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
