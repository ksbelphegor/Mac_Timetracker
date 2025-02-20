import os
import logging
from pathlib import Path

# 앱 정보
APP_NAME = "Mac Time Tracker"
BUNDLE_ID = "com.ksbelphegor.timetracker"

# 디렉토리 설정
HOME_DIR = str(Path.home())
DATA_DIR = os.path.join(HOME_DIR, '.mac_timetracker')
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

# 로깅 설정
def setup_logging():
    """로깅 시스템을 설정합니다."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    # 로그 파일 크기 제한 (10MB)
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 10 * 1024 * 1024:
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.write('')  # 로그 파일 초기화
