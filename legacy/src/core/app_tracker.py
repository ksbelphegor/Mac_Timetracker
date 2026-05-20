import time as time_module
import datetime
import traceback
import logging
from AppKit import NSWorkspace, NSApplicationActivationPolicyRegular
from src.core.config import APP_NAME, BUNDLE_ID, CONFIG
import os

class AppTracker:
    """
    앱 추적 로직을 처리하는 클래스
    
    이 클래스는 macOS에서 실행 중인 앱들의 사용 시간을 추적하고 관리합니다.
    NSWorkspace API를 사용하여 현재 활성화된 앱 정보를 가져오고,
    각 앱의 사용 시간을 기록하며, 창(윈도우) 단위로 세부 사용 시간을 추적합니다.
    
    Attributes:
        data_manager: 데이터 저장 및 로드를 담당하는 DataManager 인스턴스
        our_pid: 현재 프로세스의 PID
        our_bundle_id: 현재 앱의 번들 ID
        our_app_name: 현재 앱의 이름
        current_date: 현재 날짜 (YYYY-MM-DD 형식)
        app_usage: 앱 사용 데이터를 저장하는 딕셔너리
        _window_title_cache: 창 제목 캐시
        _app_list_cache: 실행 중인 앱 목록 캐시
        _last_app_update: 마지막 앱 목록 업데이트 시간
        _last_window_check: 마지막 창 확인 시간
        _window_check_interval: 창 확인 간격 (초)
        _app_cache_lifetime: 앱 캐시 수명 (초)
        _cache_cleanup_counter: 캐시 정리 카운터
        running_apps: 현재 실행 중인 앱 목록
    """
    
    def __init__(self, data_manager):
        """
        AppTracker 초기화
        
        Args:
            data_manager: 데이터 저장 및 로드를 담당하는 DataManager 인스턴스
        """
        self.data_manager = data_manager
        self.our_pid = os.getpid()
        self.our_bundle_id = BUNDLE_ID
        self.our_app_name = APP_NAME
        
        # 기본 데이터 초기화
        self.current_date = datetime.datetime.now().date().strftime('%Y-%m-%d')
        loaded_usage = self.data_manager.load_app_usage()
        if not loaded_usage or 'dates' not in loaded_usage:
            loaded_usage = {'dates': {}}
        self.app_usage = loaded_usage
        self.app_usage.setdefault('dates', {})
        self.app_usage['dates'].setdefault(self.current_date, {})
        # 타이머 누적값 스냅샷
        self._last_timer_totals = {}
        
        # 캐시 및 상태 관리
        self._window_title_cache = {}
        self._app_list_cache = set()
        self._last_app_update = 0
        self._last_window_check = 0
        self._window_check_interval = 1.0
        self._app_cache_lifetime = CONFIG["cache"]["app_lifetime"]
        self._cache_cleanup_counter = 0
        
        # 실행 중인 앱 목록
        self.running_apps = set()
        
        logging.info("AppTracker 초기화 완료")
    
    def get_active_window_title(self):
        """
        현재 활성 창의 제목을 가져옵니다.
        
        NSWorkspace API를 사용하여 현재 활성화된 앱 정보를 가져오고,
        해당 앱의 이름과 창 제목을 반환합니다.
        
        Returns:
            tuple: (앱 이름, 창 제목) 형태의 튜플. 정보를 가져올 수 없는 경우 (None, None) 반환
        """
        try:
            # NSWorkspace를 사용하여 현재 활성 앱 정보를 가져옵니다
            workspace = NSWorkspace.sharedWorkspace()
            active_app = workspace.activeApplication()
            if not active_app:
                return None, None
            
            app_name = active_app['NSApplicationName']
            
            # 현재 앱이 우리 앱인 경우 처리
            if active_app['NSApplicationProcessIdentifier'] == self.our_pid:
                return app_name, "App"
            
            # 시스템 앱은 제외
            skip_apps = {'Finder', 'SystemUIServer', 'loginwindow', 'Dock', 'Control Center', 'Notification Center'}
            if app_name in skip_apps:
                return app_name, app_name
            
            # 캐시 확인
            cache_key = f"{app_name}_{active_app['NSApplicationProcessIdentifier']}"
            current_time = time_module.time()
            
            if (cache_key in self._window_title_cache and 
                current_time - self._window_title_cache[cache_key]['time'] < 10.0):
                return app_name, self._window_title_cache[cache_key]['title']
            
            # 캐시 업데이트
            window_title = app_name
            self._window_title_cache[cache_key] = {
                'title': window_title,
                'time': current_time
            }
            
            # 주기적으로 캐시 정리 (100회마다)
            self._cache_cleanup_counter += 1
            if self._cache_cleanup_counter >= 100:
                self._cleanup_cache()
                self._cache_cleanup_counter = 0
            
            return app_name, window_title
            
        except Exception as e:
            print(f"활성 창 정보 가져오기 실패: {e}")
            return None, None
    
    def _cleanup_cache(self):
        """오래된 캐시 항목을 정리합니다."""
        try:
            current_time = time_module.time()
            expired_keys = []
            
            for key, data in self._window_title_cache.items():
                if current_time - data['time'] > 300:  # 5분 이상 지난 항목 제거
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._window_title_cache[key]
                
            print(f"{len(expired_keys)}개의 캐시 항목 정리됨")
            
        except Exception as e:
            print(f"캐시 정리 중 오류 발생: {e}")
    
    def update_app_list(self):
        """실행 중인 앱 목록을 업데이트합니다."""
        current_time = time_module.time()
        
        # 캐시가 유효한 경우 캐시된 앱 리스트 사용
        if (current_time - self._last_app_update < self._app_cache_lifetime and 
            self._app_list_cache):
            return self._app_list_cache
        
        # 앱 리스트 업데이트
        new_apps = set()
        for app in NSWorkspace.sharedWorkspace().runningApplications():
            if app.activationPolicy() == NSApplicationActivationPolicyRegular:
                app_name = app.localizedName()
                if app_name:
                    new_apps.add(app_name)
        
        # 변경사항이 있을 때만 업데이트
        if new_apps != self._app_list_cache:
            self.running_apps = new_apps
            self._app_list_cache = new_apps.copy()
            self._last_app_update = current_time
        
        return self._app_list_cache
    
    def update_usage_stats(self, timer_data):
        """현재 실행 중인 앱의 시간을 업데이트합니다."""
        try:
            if not timer_data or not timer_data.get('app_name'):
                return
                
            current_time = time_module.time()
            current_date = datetime.datetime.now().date().strftime('%Y-%m-%d')
            
            # 날짜가 변경되었는지 확인
            if current_date != self.current_date:
                # 새로운 날짜의 데이터 초기화
                if current_date not in self.app_usage['dates']:
                    self.app_usage['dates'][current_date] = {}
                
                # 현재 날짜 업데이트
                self.current_date = current_date
            
            # 현재 활성화된 앱의 시간 업데이트
            app_name = timer_data['app_name']
            app_records = self.app_usage['dates'][current_date]
            if app_name not in app_records:
                app_records[app_name] = {
                    'total_time': 0,
                    'windows': {},
                    'is_active': False,
                    'last_update': current_time
                }

            app_data = app_records[app_name]

            # 타이머 매니저가 추적 중인 누적 시간(정지 상태 포함)
            baseline_total = timer_data.get('total_time', 0) or 0
            start_time = timer_data.get('start_time')
            if timer_data.get('is_active') and start_time:
                baseline_total += max(0, current_time - start_time)

            previous_total = self._last_timer_totals.get(app_name, 0)
            if baseline_total < previous_total:
                # 타이머가 리셋된 경우, 스냅샷을 새로 시작
                previous_total = 0

            delta = baseline_total - previous_total

            if delta > 0:
                app_data['total_time'] += delta
                window_key = timer_data.get('current_window')
                if window_key:
                    if window_key not in app_data['windows']:
                        app_data['windows'][window_key] = 0
                    app_data['windows'][window_key] += delta

            app_data['is_active'] = timer_data.get('is_active', False)
            app_data['last_update'] = current_time
            self._last_timer_totals[app_name] = baseline_total
            
        except Exception as e:
            print(f"앱 사용 통계 업데이트 중 오류 발생: {e}")
            traceback.print_exc()
    
    def save_app_usage(self):
        """앱 사용 통계를 저장합니다."""
        self.data_manager.save_app_usage(self.app_usage) 