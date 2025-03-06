import time as time_module
import datetime
import logging
from src.core.config import CONFIG

class TimerManager:
    """
    타이머 관리 클래스
    
    이 클래스는 앱 사용 시간 추적을 위한 타이머 기능을 관리합니다.
    타이머 시작, 정지, 일시 중지 및 재개 기능을 제공하며,
    현재 추적 중인 앱과 창에 대한 시간 정보를 관리합니다.
    
    Attributes:
        data_manager: 데이터 저장 및 로드를 담당하는 DataManager 인스턴스
        timer_data: 타이머 데이터를 저장하는 딕셔너리
        _is_initialized: 초기화 완료 여부
    """
    
    def __init__(self, data_manager):
        """
        TimerManager 초기화
        
        Args:
            data_manager: 데이터 저장 및 로드를 담당하는 DataManager 인스턴스
        """
        self.data_manager = data_manager
        self.timer_data = self.data_manager.load_timer_data()
        self._is_initialized = True
        logging.info("TimerManager 초기화 완료")
        
        # 메모리 캐시 최적화
        self._memory_cache = {
            'active_app': None,
            'window_title': None,
            'last_update': 0,
            'last_ui_update': 0,
            'last_save': 0,
            'pending_updates': set(),
            'cache_hits': 0,
            'cache_misses': 0
        }
        
        # 성능 최적화를 위한 설정
        self._batch_size = 20
        self._min_update_interval = 0.2
        self._last_batch_process = 0
        self._window_check_interval = 1.0
    
    def _create_default_timer_data(self):
        """기본 타이머 데이터 구조를 생성합니다."""
        return {
            'app_name': None,
            'start_time': None,
            'total_time': 0,
            'is_active': False,
            'windows': {},
            'current_window': None,
            'last_update': time_module.time()
        }
    
    def reset_timer(self):
        """타이머를 초기화합니다."""
        self.timer_data = self._create_default_timer_data()
        return self.timer_data
    
    def select_app(self, app_name, is_active=False):
        """앱을 선택하고 타이머 데이터를 초기화합니다."""
        self.timer_data = self._create_default_timer_data()
        self.timer_data['app_name'] = app_name
        
        if is_active:
            self.start_timer()
        
        return self.timer_data
    
    def start_timer(self):
        """타이머를 시작합니다."""
        current_time = time_module.time()
        self.timer_data['start_time'] = current_time
        self.timer_data['is_active'] = True
        self.timer_data['last_update'] = current_time
        self._memory_cache['pending_updates'].add('timer_data')
        return self.timer_data
    
    def stop_timer(self):
        """타이머를 정지합니다."""
        if not self.timer_data['is_active']:
            return self.timer_data
            
        current_time = time_module.time()
        elapsed = current_time - self.timer_data['start_time']
        self.timer_data['total_time'] += elapsed
        self.timer_data['is_active'] = False
        self.timer_data['last_update'] = current_time
        self._memory_cache['pending_updates'].add('timer_data')
        return self.timer_data
    
    def update_timer_status(self, is_active_app, current_time=None):
        """앱의 활성 상태에 따라 타이머 상태를 업데이트합니다."""
        if not self.timer_data.get('app_name'):
            return None, False
        
        if current_time is None:
            current_time = time_module.time()
            
        state_changed = False
            
        # 상태가 변경된 경우만 업데이트
        if is_active_app != self.timer_data['is_active']:
            if is_active_app:
                # 타이머 시작
                self.timer_data['start_time'] = current_time
                self.timer_data['is_active'] = True
            else:
                # 타이머 정지
                if self.timer_data['is_active']:
                    elapsed = current_time - self.timer_data['start_time']
                    self.timer_data['total_time'] += elapsed
                    self.timer_data['is_active'] = False
            
            self.timer_data['last_update'] = current_time
            self._memory_cache['pending_updates'].add('timer_data')
            state_changed = True
        
        return self.timer_data, state_changed
    
    def get_formatted_time(self, include_active_time=True):
        """현재 타이머 상태에 따른 시간을 형식에 맞게 변환합니다."""
        if not self.timer_data.get('app_name'):
            return "00:00:00"
        
        current_time = time_module.time()
        
        if include_active_time and self.timer_data['is_active']:
            elapsed = current_time - self.timer_data['start_time']
            current_total = self.timer_data['total_time'] + elapsed
        else:
            current_total = self.timer_data['total_time']
        
        hours = int(current_total // 3600)
        minutes = int((current_total % 3600) // 60)
        seconds = int(current_total % 60)
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def update_window_info(self, window_title):
        """현재 창 정보를 업데이트합니다."""
        if window_title and self.timer_data.get('app_name'):
            self.timer_data['current_window'] = window_title
            
            if window_title not in self.timer_data['windows']:
                self.timer_data['windows'][window_title] = 0
            
            return True
        return False
    
    def _process_pending_updates(self):
        """배치로 대기 중인 업데이트를 처리합니다."""
        try:
            current_time = time_module.time()
            if 'timer_data' in self._memory_cache['pending_updates']:
                self.data_manager.save_timer_data(self.timer_data)
            self._memory_cache['pending_updates'].clear()
            self._last_batch_process = current_time
            return True
        except Exception as e:
            print(f"업데이트 처리 중 오류 발생: {e}")
            return False
    
    def should_process_updates(self, current_time=None):
        """대기 중인 업데이트를 처리할지 여부를 결정합니다."""
        if current_time is None:
            current_time = time_module.time()
            
        return (len(self._memory_cache['pending_updates']) >= self._batch_size or 
                (self._memory_cache['pending_updates'] and 
                 current_time - self._last_batch_process >= 30.0))
    
    def save_timer_data(self):
        """타이머 데이터를 저장합니다."""
        return self.data_manager.save_timer_data(self.timer_data)
    
    def format_time(self, seconds):
        """초를 HH:MM:SS 형식으로 변환합니다."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}" 