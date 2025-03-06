import os
import logging
import json
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
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')

# 기본 설정값
DEFAULT_CONFIG = {
    # 캐시 설정
    "cache": {
        "max_size": 1024 * 1024,  # 1MB 캐시 크기 제한
        "cleanup_interval": 3600,  # 1시간마다 캐시 정리
        "app_lifetime": 2.0,       # 앱 캐시 수명 (초)
    },
    
    # 데이터 관리 설정
    "data_management": {
        "save_interval": 60,       # 데이터 저장 간격 (초)
        "retention_days": 30,      # 데이터 보관 기간 (일)
    },
    
    # UI 설정
    "ui": {
        "app_list_update_interval": 10000,  # 앱 목록 업데이트 간격 (밀리초)
        "time_update_interval": 1000,       # 시간 업데이트 간격 (밀리초)
        "status_bar_width": 120,
        "status_bar_height": 22,
        "icon_size": 20,
    },
    
    # 로깅 설정
    "logging": {
        "level": "INFO",
        "max_size": 10 * 1024 * 1024,  # 10MB
        "backup_count": 3,
    }
}

# 기존 설정 유지를 위한 변수들
APP_CACHE_LIFETIME = DEFAULT_CONFIG["cache"]["app_lifetime"]
APP_LIST_UPDATE_INTERVAL = DEFAULT_CONFIG["ui"]["app_list_update_interval"]
TIME_UPDATE_INTERVAL = DEFAULT_CONFIG["ui"]["time_update_interval"]
STATUS_BAR_WIDTH = DEFAULT_CONFIG["ui"]["status_bar_width"]
STATUS_BAR_HEIGHT = DEFAULT_CONFIG["ui"]["status_bar_height"]
ICON_SIZE = DEFAULT_CONFIG["ui"]["icon_size"]
DATA_RETENTION_DAYS = DEFAULT_CONFIG["data_management"]["retention_days"]

# 설정 로드 함수
def load_config():
    """설정 파일을 로드하거나 기본값을 반환합니다."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                
            # 기본 설정과 사용자 설정 병합
            config = DEFAULT_CONFIG.copy()
            for section in user_config:
                if section in config:
                    if isinstance(config[section], dict) and isinstance(user_config[section], dict):
                        config[section].update(user_config[section])
                    else:
                        config[section] = user_config[section]
                else:
                    config[section] = user_config[section]
                    
            return config
        except Exception as e:
            logging.error(f"설정 파일 로드 중 오류 발생: {e}")
            
    # 설정 파일이 없거나 오류 발생 시 기본 설정 저장
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"기본 설정 파일 저장 중 오류 발생: {e}")
        
    return DEFAULT_CONFIG

# 전역 설정 객체
CONFIG = load_config()

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
    
    log_level = getattr(logging, CONFIG["logging"]["level"], logging.INFO)
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            RotatingFileHandler(
                LOG_FILE,
                maxBytes=CONFIG["logging"]["max_size"],
                backupCount=CONFIG["logging"]["backup_count"],
                encoding='utf-8'
            ),
            logging.StreamHandler()
        ]
    )
