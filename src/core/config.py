import os
import logging
import json
from logging.handlers import RotatingFileHandler

# 앱 정보
APP_NAME = "Mac Time Tracker"
BUNDLE_ID = "com.ksbelphegor.mactimetracker"
APP_VERSION = "1.2.0"

# 디렉토리 설정
DATA_DIR = os.path.expanduser("~/.mactimetracker")
APP_USAGE_FILE = os.path.join(DATA_DIR, 'app_usage.json')
TIMER_DATA_FILE = os.path.join(DATA_DIR, 'timer_data.json')
LOG_FILE = os.path.join(DATA_DIR, 'app.log')
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')

# 기본 설정값
DEFAULT_CONFIG = {
    "cache": {
        "max_size": 1024 * 1024,
        "cleanup_interval": 3600,
        "app_lifetime": 2.0,
    },
    "data_management": {
        "save_interval": 30,
        "retention_days": 30,
    },
    "ui": {
        "status_bar_width": 140,
        "status_bar_height": 22,
        "icon_size": 20,
    },
    "logging": {
        "level": "INFO",
        "max_size": 10 * 1024 * 1024,
        "backup_count": 3,
    }
}


def load_config():
    """설정 파일을 로드하거나 기본값을 반환합니다."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                user_config = json.load(f)

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
            logging.error(f"설정 로드 실패: {e}")

    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"기본 설정 저장 실패: {e}")

    return DEFAULT_CONFIG


def save_config(config):
    """설정을 파일에 저장합니다."""
    try:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        logging.error(f"설정 저장 실패: {e}")
        return False


CONFIG = load_config()


def setup_logging():
    """로깅 시스템을 설정합니다."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)

    log_level = getattr(logging, CONFIG["logging"]["level"], logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
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
