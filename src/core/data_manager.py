import json
import os
import traceback
from core.config import DATA_DIR, APP_USAGE_FILE, TIMER_DATA_FILE
import threading
from time import time

class DataManager:
    _instance = None
    _lock = threading.Lock()
    _data_cache = {}
    _last_save = {}
    _save_interval = 60  # 60초
    _max_cache_size = 1024 * 1024  # 1MB 캐시 크기 제한
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        self.ensure_data_directory()
        self._data_cache = {
            'app_usage': None,
            'timer_data': None
        }
        self._last_save = {
            'app_usage': 0,
            'timer_data': 0
        }
        self._dirty = {
            'app_usage': False,
            'timer_data': False
        }
        self._cache_size = 0
    
    def _update_cache_size(self, data):
        """캐시 크기를 업데이트하고 제한을 확인합니다."""
        try:
            # 문자열로 변환하여 대략적인 메모리 사용량 계산
            data_size = len(json.dumps(data))
            if data_size > self._max_cache_size:
                return False
            self._cache_size = data_size
            return True
        except Exception as e:
            print(f"캐시 크기 계산 중 오류 발생: {e}")
            return False

    def ensure_data_directory(self):
        """데이터 디렉토리가 없으면 생성합니다."""
        if not hasattr(self, '_dir_checked'):
            if not os.path.exists(DATA_DIR):
                os.makedirs(DATA_DIR)
            self._dir_checked = True

    def load_app_usage(self):
        """앱 사용 데이터를 로드합니다."""
        if self._data_cache['app_usage'] is not None:
            return self._data_cache['app_usage']
            
        try:
            if not os.path.exists(APP_USAGE_FILE):
                self._data_cache['app_usage'] = {'dates': {}}
                return self._data_cache['app_usage']
                
            with open(APP_USAGE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if self._update_cache_size(data):
                    self._data_cache['app_usage'] = data
                    return self._data_cache['app_usage']
                else:
                    print("앱 사용 데이터가 캐시 크기 제한을 초과했습니다")
                    return data
                
        except json.JSONDecodeError as e:
            print(f"앱 사용 데이터 파일 손상: {e}")
            self._data_cache['app_usage'] = {'dates': {}}
            return self._data_cache['app_usage']
        except Exception as e:
            print(f"앱 사용 데이터 로드 중 오류 발생: {e}")
            self._data_cache['app_usage'] = {'dates': {}}
            return self._data_cache['app_usage']

    def save_app_usage(self, data):
        """앱 사용 데이터를 저장합니다."""
        current_time = time()
        if self._update_cache_size(data):
            self._data_cache['app_usage'] = data
        self._dirty['app_usage'] = True
        
        # 마지막 저장 후 일정 시간이 지났을 때만 저장
        if current_time - self._last_save['app_usage'] >= self._save_interval:
            try:
                with self._lock:
                    if self._dirty['app_usage']:
                        with open(APP_USAGE_FILE, 'w', encoding='utf-8') as f:
                            json.dump(data, f, ensure_ascii=False)
                        self._last_save['app_usage'] = current_time
                        self._dirty['app_usage'] = False
            except (IOError, OSError) as e:
                print(f"앱 사용 데이터 저장 중 I/O 오류 발생: {e}")
            except Exception as e:
                print(f"앱 사용 데이터 저장 중 예상치 못한 오류 발생: {e}")

    def load_timer_data(self):
        """타이머 데이터를 로드합니다."""
        if self._data_cache['timer_data'] is not None:
            return self._data_cache['timer_data']
            
        try:
            if os.path.exists(TIMER_DATA_FILE):
                with open(TIMER_DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if self._update_cache_size(data):
                        self._data_cache['timer_data'] = data
                        return self._data_cache['timer_data']
                    else:
                        print("타이머 데이터가 캐시 크기 제한을 초과했습니다")
                        return data
        except json.JSONDecodeError as e:
            print(f"타이머 데이터 파일 손상: {e}")
        except Exception as e:
            print(f"타이머 데이터 로드 중 오류 발생: {e}")
            
        self._data_cache['timer_data'] = {
            'app_name': None,
            'start_time': None,
            'total_time': 0,
            'windows': {},
            'current_window': None
        }
        return self._data_cache['timer_data']

    def save_timer_data(self, data):
        """타이머 데이터를 저장합니다."""
        current_time = time()
        if self._update_cache_size(data):
            self._data_cache['timer_data'] = data
        self._dirty['timer_data'] = True
        
        # 마지막 저장 후 일정 시간이 지났을 때만 저장
        if current_time - self._last_save['timer_data'] >= self._save_interval:
            try:
                with self._lock:
                    if self._dirty['timer_data']:
                        with open(TIMER_DATA_FILE, 'w', encoding='utf-8') as f:
                            json.dump(data, f, ensure_ascii=False)
                        self._last_save['timer_data'] = current_time
                        self._dirty['timer_data'] = False
            except (IOError, OSError) as e:
                print(f"타이머 데이터 저장 중 I/O 오류 발생: {e}")
            except Exception as e:
                print(f"타이머 데이터 저장 중 예상치 못한 오류 발생: {e}")

    @classmethod
    def force_save_all(cls):
        """모든 데이터를 강제로 저장합니다."""
        instance = cls.get_instance()
        try:
            with instance._lock:
                if instance._dirty['app_usage']:
                    with open(APP_USAGE_FILE, 'w', encoding='utf-8') as f:
                        json.dump(instance._data_cache['app_usage'], f, ensure_ascii=False)
                    instance._dirty['app_usage'] = False
                
                if instance._dirty['timer_data']:
                    with open(TIMER_DATA_FILE, 'w', encoding='utf-8') as f:
                        json.dump(instance._data_cache['timer_data'], f, ensure_ascii=False)
                    instance._dirty['timer_data'] = False
        except (IOError, OSError) as e:
            print(f"강제 저장 중 I/O 오류 발생: {e}")
        except Exception as e:
            print(f"강제 저장 중 예상치 못한 오류 발생: {e}")
