from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, 
                            QTreeWidgetItem, QTreeWidgetItemIterator, QHeaderView, QSizePolicy, QToolTip,
                            QListWidget, QTableWidget, QTableWidgetItem, QListWidgetItem)
from PyQt5.QtCore import QTimer, Qt, QRect, QPoint
from PyQt5.QtGui import QFont, QPainter, QColor, QPen
import time
import traceback
from datetime import datetime, timedelta
from core.data_manager import DataManager
import subprocess
from Foundation import NSWorkspace
import os
from core.config import APP_NAME

class TimeGraphWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)  # 높이를 더 늘림
        self.setMouseTracking(True)  # 마우스 추적 활성화
        
        # 줌 관련 변수
        self.zoom_level = 1.0  # 1.0 = 24시간 (기본 뷰)
        self.visible_hours = 24  # 기본적으로 24시간 표시
        
        # 현재 시각 기준으로 오늘 자정 시간 계산
        now = datetime.now()
        today_midnight = datetime(now.year, now.month, now.day).timestamp()
        self.center_time = today_midnight + 12 * 3600  # 정오를 중심점으로 설정
        
        # 드래그 관련 변수
        self.is_dragging = False
        self.drag_start_pos = None
        self.drag_start_time = None
        
        # 타이머 설정
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update)
        self.update_timer.start(1000)  # 1초마다 업데이트
        
        # 툴팁 폰트 설정
        QToolTip.setFont(QFont('Arial', 10))
        
        # 앱별 색상
        self.app_colors = {}
        self.color_index = 0
        self.colors = [
            QColor(100, 200, 100),  # 연한 초록
            QColor(200, 100, 100),  # 연한 빨강
            QColor(100, 100, 200),  # 연한 파랑
            QColor(200, 200, 100),  # 연한 노랑
            QColor(200, 100, 200),  # 연한 마젠타
            QColor(100, 200, 200),  # 연한 시안
            QColor(150, 150, 100),  # 연한 올리브
            QColor(150, 100, 150),  # 연한 퍼플
            QColor(100, 150, 150),  # 연한 틸
            QColor(180, 140, 100),  # 연한 브라운
        ]
        
        # 데이터 매니저
        self.data_manager = DataManager.get_instance()
        self.app_usage = {'dates': {}}

    def update_data(self, app_usage):
        """앱 사용 데이터를 업데이트합니다."""
        if app_usage != self.app_usage:  # 데이터가 변경된 경우에만 업데이트
            self.app_usage = app_usage.copy()  # 데이터 복사
            self.update()  # 화면 갱신 요청

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 현재 시각 (자정 기준)
        now = datetime.now()
        day_start = datetime(now.year, now.month, now.day).timestamp()
        current_time = time.time()
        width = self.width()
        height = self.height()
        
        # 배경색 설정
        background_color = QColor(30, 30, 30)  # 다크 그레이
        painter.fillRect(self.rect(), background_color)
        
        # 그리드 라인 색상
        grid_color = QColor(60, 60, 60)  # 밝은 다크 그레이
        text_color = QColor(200, 200, 200)  # 밝은 회색
        
        # 영역 계산
        date_height = 25  # 날짜 표시 영역 높이
        timeline_height = 25  # 타임라인 높이 (약간 줄임)
        graph_margin = 5  # 그래프 간 여백
        graph_height = (height - timeline_height * 2 - graph_margin * 2 - date_height) // 2  # 각 그래프의 높이
        
        # 보이는 시간 범위 계산
        visible_duration = self.visible_hours * 3600 * self.zoom_level
        time_start = self.center_time - visible_duration / 2
        time_end = self.center_time + visible_duration / 2
        
        # 날짜 표시
        date_start = datetime.fromtimestamp(time_start)
        date_end = datetime.fromtimestamp(time_end)
        
        # 날짜가 같으면 하나만 표시
        if date_start.date() == date_end.date():
            date_text = date_start.strftime("%Y년 %m월 %d일")
            painter.setPen(text_color)
            painter.setFont(QFont("Arial", 12, QFont.Bold))
            metrics = painter.fontMetrics()
            text_width = metrics.width(date_text)
            painter.drawText(width // 2 - text_width // 2, date_height - 5, date_text)
        else:
            # 날짜가 다르면 시작과 끝 날짜 모두 표시
            date_start_text = date_start.strftime("%Y년 %m월 %d일")
            date_end_text = date_end.strftime("%Y년 %m월 %d일")
            painter.setPen(text_color)
            painter.setFont(QFont("Arial", 12, QFont.Bold))
            painter.drawText(10, date_height - 5, date_start_text)
            metrics = painter.fontMetrics()
            text_width = metrics.width(date_end_text)
            painter.drawText(width - text_width - 10, date_height - 5, date_end_text)
        
        # 상단 타임라인
        painter.setPen(text_color)
        self._draw_timeline(painter, time_start, time_end, date_height, timeline_height)
        
        # 메인 그래프
        graph_y = date_height + timeline_height + graph_margin
        
        # 세로 그리드 라인 (1시간 간격)
        painter.setPen(grid_color)
        interval = 3600  # 1시간
        current_time = time_start - (time_start % interval)
        while current_time <= time_end:
            x = int(width * (current_time - time_start) / (time_end - time_start))
            painter.drawLine(x, graph_y, x, graph_y + graph_height)
            current_time += interval
        
        # 앱 사용 시간 그래프
        self._draw_app_usage(painter, time_start, time_end, graph_y, graph_height)
        
        # 현재 시간 표시선
        now = time.time()
        if time_start <= now <= time_end:
            x = int(width * (now - time_start) / (time_end - time_start))
            painter.setPen(QPen(QColor(255, 50, 50), 2))  # 빨간색 선
            painter.drawLine(x, graph_y, x, graph_y + graph_height)
        
        # 미니맵
        minimap_y = graph_y + graph_height + graph_margin
        day_start = now - (now % 86400)  # 오늘 자정
        
        # 미니맵 배경
        painter.fillRect(0, minimap_y, self.width(), graph_height, background_color)
        
        # 미니맵 그리드 라인
        painter.setPen(grid_color)
        for hour in range(25):  # 0시부터 24시까지
            x = int(self.width() * hour / 24)
            painter.drawLine(x, minimap_y, x, minimap_y + graph_height)
            if hour % 3 == 0:  # 3시간 간격으로 시간 표시
                painter.setPen(text_color)
                painter.drawText(x + 5, minimap_y + graph_height - 5, f"{hour:02d}:00")
                painter.setPen(grid_color)
        
        self._draw_minimap(painter, day_start, now, minimap_y, graph_height)

    def _draw_timeline(self, painter, time_start, time_end, y, height):
        width = self.width()
        
        # 1시간 간격으로 눈금 그리기
        painter.setPen(QPen(QColor(60, 60, 60), 1))
        interval = 3600  # 1시간
        start_time = int(time_start // interval) * interval
        
        for t in range(int(start_time), int(time_end) + interval, interval):
            x = int(width * (t - time_start) / (time_end - time_start))
            
            # 시간 텍스트 (정시만 표시)
            dt = datetime.fromtimestamp(t)
            time_text = dt.strftime('%H:%M')
            
            # 텍스트 중앙 정렬
            metrics = painter.fontMetrics()
            text_width = metrics.width(time_text)
            text_x = x - text_width // 2
            painter.setPen(QPen(QColor(200, 200, 200), 1))
            painter.drawText(text_x, y + height - 5, time_text)

    def _draw_app_usage(self, painter, time_start, time_end, y, height):
        width = self.width()
        opacity = 0.7
        
        # 앱별로 시간 구간을 저장
        app_intervals = []
        current_date = datetime.now().date().strftime('%Y-%m-%d')
        
        # 현재 날짜의 앱 데이터만 사용
        current_apps = self.app_usage.get('dates', {}).get(current_date, {})
        
        for app_name, app_data in current_apps.items():
            if app_name == APP_NAME:
                continue
                
            intervals = []
            current_start = app_data.get('last_update', time.time()) - app_data.get('total_time', 0)
            current_end = app_data.get('last_update', time.time())
            
            # 연속된 시간을 30초 단위로 분할
            while current_start < current_end:
                interval_end = min(current_end, current_start + 30)
                if current_start <= time_end and interval_end >= time_start:
                    intervals.append((current_start, interval_end))
                current_start = interval_end
            
            if intervals:
                app_intervals.append((app_name, intervals))
        
        # 시간순으로 정렬
        app_intervals.sort(key=lambda x: x[1][0][0])
        
        # 각 앱의 사용 시간을 개별적으로 그리기
        for app_name, intervals in app_intervals:
            color = self.get_app_color(app_name)
            color.setAlphaF(opacity)
            
            for start_time, end_time in intervals:
                if start_time <= time_end and end_time >= time_start:
                    x_start = int(width * (max(start_time, time_start) - time_start) / (time_end - time_start))
                    x_end = int(width * (min(end_time, time_end) - time_start) / (time_end - time_start))
                    
                    painter.fillRect(x_start, y, x_end - x_start, height, color)

    def _draw_minimap(self, painter, day_start, current_time, y, height):
        width = self.width()
        visible_duration = 24 * 3600  # 24시간
        current_date = datetime.now().date().strftime('%Y-%m-%d')
        
        # 미니맵 배경
        painter.fillRect(0, y, width, height, QColor(30, 30, 30))
        
        # 현재 보이는 영역 표시
        visible_start = self.center_time - (self.visible_hours * 3600 * self.zoom_level) / 2
        visible_end = self.center_time + (self.visible_hours * 3600 * self.zoom_level) / 2
        
        x_start = int(width * (visible_start - day_start) / visible_duration)
        x_end = int(width * (visible_end - day_start) / visible_duration)
        
        # 현재 날짜의 앱 데이터만 사용
        current_apps = self.app_usage.get('dates', {}).get(current_date, {})
        
        # 각 앱의 사용 시간을 그리기
        for app_name, app_data in current_apps.items():
            if app_name == APP_NAME:
                continue
                
            color = self.get_app_color(app_name)
            color.setAlphaF(0.5)  # 미니맵은 더 투명하게
            
            start_time = app_data.get('last_update', current_time) - app_data.get('total_time', 0)
            end_time = app_data.get('last_update', current_time)
            
            if start_time <= current_time and end_time >= day_start:
                x1 = int(width * (max(start_time, day_start) - day_start) / visible_duration)
                x2 = int(width * (min(end_time, current_time) - day_start) / visible_duration)
                
                painter.fillRect(x1, y, x2 - x1, height, color)
        
        # 현재 보이는 영역 표시
        highlight_color = QColor(255, 255, 255, 50)  # 반투명 흰색
        painter.fillRect(x_start, y, x_end - x_start, height, highlight_color)
        
        # 현재 시각 표시
        current_x = int(width * (current_time - day_start) / visible_duration)
        painter.setPen(QPen(QColor(255, 0, 0), 2))
        painter.drawLine(current_x, y, current_x, y + height)

    def get_app_color(self, app_name):
        """앱별 고유 색상을 반환합니다."""
        if app_name not in self.app_colors:
            color = self.colors[self.color_index % len(self.colors)]
            self.app_colors[app_name] = color
            self.color_index += 1
        return self.app_colors[app_name]

    def wheelEvent(self, event):
        # Ctrl + 휠로 줌 인/아웃
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_level = max(0.1, self.zoom_level * 0.9)  # 줌 인
            else:
                self.zoom_level = min(10.0, self.zoom_level * 1.1)  # 줌 아웃
            self.update()
        else:
            # 일반 휠은 시간 이동
            delta = event.angleDelta().y()
            visible_duration = self.visible_hours * 3600 * self.zoom_level
            self.center_time -= (delta / 120.0) * (visible_duration / 10)
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.drag_start_pos = event.pos()
            self.drag_start_time = self.center_time

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = False

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            dx = event.pos().x() - self.drag_start_pos.x()
            visible_duration = self.visible_hours * 3600 * self.zoom_level
            time_delta = (dx / self.width()) * visible_duration
            self.center_time = self.drag_start_time - time_delta
            self.update()
        
        # 툴팁 표시
        if hasattr(self.window(), 'app_usage'):
            pos = event.pos()
            timeline_height = 30
            graph_margin = 5
            graph_height = (self.height() - timeline_height * 2 - graph_margin * 2) // 2
            graph_y = timeline_height + graph_margin
            
            # 마우스가 그래프 영역 안에 있을 때만 툴팁 표시
            if graph_y <= pos.y() <= graph_y + graph_height:
                visible_duration = self.visible_hours * 3600 * self.zoom_level
                time_at_cursor = self.center_time - visible_duration/2 + (pos.x() / self.width()) * visible_duration
                
                # 해당 시점에서 실행 중인 앱 찾기
                found_app = None
                for app_name, app_data in self.window().app_usage.items():
                    start_time = app_data.get('last_update', time.time()) - app_data.get('total_time', 0)
                    end_time = app_data.get('last_update', time.time())
                    
                    if start_time <= time_at_cursor <= end_time:
                        found_app = (app_name, start_time, end_time)
                        break
                
                if found_app:
                    app_name, start_time, end_time = found_app
                    duration = end_time - start_time
                    start_dt = datetime.fromtimestamp(start_time)
                    end_dt = datetime.fromtimestamp(end_time)
                    duration_str = f"{int(duration // 3600):02d}:{int((duration % 3600) // 60):02d}:{int(duration % 60):02d}"
                    tooltip_text = f"{app_name}\n시작: {start_dt.strftime('%H:%M:%S')}\n종료: {end_dt.strftime('%H:%M:%S')}\n사용 시간: {duration_str}"
                    QToolTip.showText(event.globalPos(), tooltip_text)
                else:
                    QToolTip.hideText()
            else:
                QToolTip.hideText()

class AppTrackingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # 초기화
        self.active_app = None
        self.active_window = None
        self.active_start_time = None
        self._is_active = True
        self.current_date = datetime.now().date()
        self.selected_date = self.current_date.strftime('%Y-%m-%d')
        
        # 데이터 매니저 초기화
        self.data_manager = DataManager.get_instance()
        
        # 앱 사용 데이터 로드
        self.app_usage = self.data_manager.load_app_usage()
        if not self.app_usage:
            self.app_usage = {'dates': {}}
        if 'dates' not in self.app_usage:
            self.app_usage['dates'] = {}
        if self.selected_date not in self.app_usage['dates']:
            self.app_usage['dates'][self.selected_date] = {}
        
        # 타이머 설정 (0.5초마다 업데이트)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_usage_stats)
        self.timer.start(500)  # 0.5초마다
        print("타이머 시작됨")

        # 트리 업데이트 최적화를 위한 변수
        self._last_tree_update = 0
        self._tree_update_interval = 2.0  # 트리 업데이트 간격을 2초로 설정
        self._pending_tree_update = False  # 트리 업데이트 대기 상태 초기화
        self._expanded_items = {}  # 확장된 아이템 상태를 저장할 딕셔너리

    def update_usage_stats(self):
        """현재 활성화된 앱의 사용 통계를 업데이트합니다."""
        try:
            workspace = NSWorkspace.sharedWorkspace()
            active_app = workspace.activeApplication()
            
            if active_app:
                app_name = active_app['NSApplicationName']
                window_title = self.get_active_window_title()
                current_time = time.time()
                
                # 앱이 변경되었을 때
                if app_name != self.active_app:
                    # 이전 앱의 사용 시간 업데이트
                    if self.active_app and self.active_start_time:
                        elapsed_time = current_time - self.active_start_time
                        if elapsed_time > 0:
                            self.update_app_time(self.active_app, self.active_window, elapsed_time)
                    
                    # 현재 날짜의 데이터 확인
                    current_date = datetime.now().date().strftime('%Y-%m-%d')
                    if current_date not in self.app_usage['dates']:
                        self.app_usage['dates'][current_date] = {}
                    
                    # 새로운 앱의 시작 시간 기록
                    if app_name not in self.app_usage['dates'][current_date]:
                        self.app_usage['dates'][current_date][app_name] = {
                            'total_time': 0,
                            'windows': {},
                            'start_times': [datetime.now().strftime('%H:%M:%S')]
                        }
                    else:
                        if 'start_times' not in self.app_usage['dates'][current_date][app_name]:
                            self.app_usage['dates'][current_date][app_name]['start_times'] = []
                        self.app_usage['dates'][current_date][app_name]['start_times'].append(datetime.now().strftime('%H:%M:%S'))
                    
                    self.active_app = app_name
                    self.active_window = window_title
                    self.active_start_time = current_time
                
                # 창 제목이 변경되었을 때
                elif window_title != self.active_window:
                    if self.active_app and self.active_start_time:
                        elapsed_time = current_time - self.active_start_time
                        if elapsed_time > 0:
                            self.update_app_time(self.active_app, self.active_window, elapsed_time)
                    self.active_window = window_title
                    self.active_start_time = current_time
                
                # 동일한 앱/창이 계속 활성화되어 있을 때도 시간을 업데이트
                elif self.active_app and self.active_start_time:
                    elapsed_time = current_time - self.active_start_time
                    if elapsed_time > 0:
                        self.update_app_time(self.active_app, self.active_window, elapsed_time)
                        self.active_start_time = current_time  # 시작 시간을 현재 시간으로 업데이트
                
                # 앱 목록 업데이트 (1초에 한 번)
                if hasattr(self, '_last_time_update') and current_time - self._last_time_update >= self._update_interval:
                    self._update_app_list()
                    self._last_time_update = current_time
            
        except Exception as e:
            print(f"앱 사용 통계 업데이트 중 오류 발생: {e}")
            traceback.print_exc()

    def save_expanded_state(self):
        """더 이상 tree widget을 사용하지 않으므로 빈 메서드로 유지"""
        pass

    def restore_expanded_state(self):
        """더 이상 tree widget을 사용하지 않으므로 빈 메서드로 유지"""
        pass

    def update_app_time(self, app_name=None, window_title=None, elapsed_time=None):
        """앱 사용 시간을 업데이트합니다."""
        try:
            if not all([app_name, elapsed_time]) or app_name == APP_NAME:
                return
                
            current_date = datetime.now().date().strftime('%Y-%m-%d')
            
            # 날짜 데이터가 없으면 초기화
            if current_date not in self.app_usage['dates']:
                self.app_usage['dates'][current_date] = {}
            
            # 앱 데이터가 없으면 초기화
            if app_name not in self.app_usage['dates'][current_date]:
                self.app_usage['dates'][current_date][app_name] = {
                    'total_time': 0,
                    'windows': {},
                    'start_times': []
                }
            
            # 앱의 총 사용 시간 업데이트
            self.app_usage['dates'][current_date][app_name]['total_time'] += elapsed_time
            
            # 창별 사용 시간 업데이트
            if window_title:
                # window_title이 튜플인 경우 첫 번째 요소만 사용
                if isinstance(window_title, tuple):
                    window_title = window_title[1] if len(window_title) > 1 else window_title[0]
                    
                if window_title not in self.app_usage['dates'][current_date][app_name]['windows']:
                    self.app_usage['dates'][current_date][app_name]['windows'][window_title] = 0
                self.app_usage['dates'][current_date][app_name]['windows'][window_title] += elapsed_time
            
        except Exception as e:
            print(f"앱 시간 업데이트 중 오류 발생: {e}")
            traceback.print_exc()

    def get_app_window_title(self, app_name):
        """각 앱의 현재 창/탭 제목을 가져옵니다."""
        try:
            # 앱이 실행 중인지 먼저 확인
            check_script = f'''
                tell application "System Events"
                    set isRunning to (name of processes) contains "{app_name}"
                end tell
            '''
            check_result = subprocess.run(['osascript', '-e', check_script], 
                                        capture_output=True, 
                                        text=True,
                                        timeout=0.5)  # 타임아웃 0.5초로 감소
            
            if check_result.returncode != 0 or "false" in check_result.stdout.lower():
                return app_name
            
            script = f'''
                tell application "System Events"
                    tell process "{app_name}"
                        try
                            get name of front window
                        on error
                            return "{app_name}"
                        end try
                    end tell
                end tell
            '''
            
            result = subprocess.run(['osascript', '-e', script], 
                                  capture_output=True, 
                                  text=True,
                                  timeout=0.5)  # 타임아웃 0.5초로 감소
            
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            return app_name
            
        except subprocess.TimeoutExpired:
            return app_name
        except Exception as e:
            return app_name

    def get_active_window_title(self):
        """현재 활성 창의 제목을 가져옵니다."""
        try:
            workspace = NSWorkspace.sharedWorkspace()
            active_app = workspace.activeApplication()
            if active_app:
                app_name = active_app['NSApplicationName']
                
                # 캐시 키 생성
                cache_key = f"{app_name}_{active_app['NSApplicationProcessIdentifier']}"
                current_time = time.time()
                
                # 캐시된 결과가 있고 유효한 경우 사용 (캐시 시간을 5초로 증가)
                if (hasattr(self, '_window_title_cache') and 
                    cache_key in self._window_title_cache and 
                    current_time - self._window_title_cache[cache_key]['time'] < 5.0):
                    return app_name, self._window_title_cache[cache_key]['title']
                
                # 특정 앱들은 창 제목 가져오기를 시도하지 않음
                skip_apps = {'Finder', 'SystemUIServer', 'loginwindow', APP_NAME}
                if app_name in skip_apps:
                    return app_name, app_name
                
                try:
                    # System Events를 통해 창 제목 가져오기 (타임아웃 0.5초로 감소)
                    window_title = self.get_app_window_title(app_name)
                except:
                    window_title = app_name
                
                # 캐시 업데이트
                if not hasattr(self, '_window_title_cache'):
                    self._window_title_cache = {}
                self._window_title_cache[cache_key] = {
                    'title': window_title,
                    'time': current_time
                }
                
                # 캐시 크기 제한 (50개로 감소)
                if len(self._window_title_cache) > 50:
                    oldest_key = min(self._window_title_cache.items(), 
                                   key=lambda x: x[1]['time'])[0]
                    del self._window_title_cache[oldest_key]
                
                return app_name, window_title
        except Exception as e:
            print(f"활성 창 정보 가져오기 실패: {e}")
        return None

    def update_tree_widget(self):
        """트리 위젯의 내용을 업데이트합니다."""
        try:
            current_date = datetime.now().date().strftime('%Y-%m-%d')
            if current_date not in self.app_usage['dates']:
                return

            # 현재 선택된 정렬 열과 정렬 순서 저장
            header = self.tree_widget.header()
            sort_column = header.sortIndicatorSection()
            sort_order = header.sortIndicatorOrder()

            # 트리가 비어있을 때만 새로 생성
            if self.tree_widget.topLevelItemCount() == 0:
                self.create_tree_items()
            else:
                self.update_tree_items()

            # 이전 정렬 상태 복원
            self.tree_widget.sortItems(sort_column, sort_order)
            
            # 총 사용 시간 업데이트
            self.update_total_time()
            
            # 데이터 저장
            self.data_manager.save_app_usage(self.app_usage)
            
            # 확장 상태 복원
            self.restore_expanded_state()
            
        except Exception as e:
            print(f"트리 위젯 업데이트 중 오류 발생: {e}")
            traceback.print_exc()

    def create_tree_items(self):
        """트리 아이템을 처음 생성합니다."""
        current_date = datetime.now().date().strftime('%Y-%m-%d')
        
        for app_name, app_data in self.app_usage['dates'][current_date].items():
            if app_name == APP_NAME:  # 자기 자신은 표시하지 않음
                continue
                
            # 부모 아이템 생성
            app_item = QTreeWidgetItem(self.tree_widget)
            app_item.setText(0, app_name)  # 앱 이름
            app_item.setText(1, '')  # 시작 시간은 비워둠
            app_item.setText(2, '')  # 종료 시간은 비워둠
            app_item.setData(0, Qt.UserRole, app_name)  # 앱 이름을 데이터로 저장
            
            # 총 사용 시간 계산 및 설정
            total_time = self.calculate_total_time(app_data)
            app_item.setText(3, self.format_time(total_time))
            
            # 창/탭별 세부 정보
            start_times = app_data.get('start_times', [])
            windows = app_data.get('windows', {})
            
            # 각 창에 대해 자식 아이템 생성
            for window_title, window_time in windows.items():
                if window_title:  # 창 제목이 있는 경우만
                    # window_title이 튜플인 경우 첫 번째 요소만 사용
                    if isinstance(window_title, tuple):
                        window_title = window_title[1] if len(window_title) > 1 else window_title[0]
                    
                    # 시작 시간을 역순으로 정렬 (최신 시간이 먼저 오도록)
                    sorted_times = sorted(start_times, reverse=True)
                    
                    # 각 시작 시간에 대해 별도의 항목 생성
                    for start_time in sorted_times:
                        window_item = QTreeWidgetItem(app_item)
                        window_item.setText(0, window_title)  # 창 제목
                        window_item.setData(0, Qt.UserRole, window_title)  # 창 제목을 데이터로 저장
                        window_item.setText(1, start_time)  # 시작 시간
                        window_item.setText(2, '')  # 종료 시간은 비워둠
                        window_item.setText(3, '')  # 시간은 비워둠 (각 시작 시간 항목에는 시간을 표시하지 않음)

    def update_tree_items(self):
        """기존 트리 아이템의 시간 정보만 업데이트합니다."""
        current_date = datetime.now().date().strftime('%Y-%m-%d')
        
        # 모든 최상위 아이템(앱)을 순회
        for i in range(self.tree_widget.topLevelItemCount()):
            app_item = self.tree_widget.topLevelItem(i)
            app_name = app_item.data(0, Qt.UserRole)
            
            if app_name in self.app_usage['dates'][current_date]:
                app_data = self.app_usage['dates'][current_date][app_name]
                
                # 총 사용 시간 업데이트
                total_time = self.calculate_total_time(app_data)
                app_item.setText(3, self.format_time(total_time))
                
                # 시작 시간과 창 정보
                start_times = app_data.get('start_times', [])
                windows = app_data.get('windows', {})
                
                # 각 창에 대해 시작 시간 업데이트
                for window_title, window_time in windows.items():
                    if window_title:
                        if isinstance(window_title, tuple):
                            window_title = window_title[1] if len(window_title) > 1 else window_title[0]
                        
                        # 현재 자식 아이템들의 시작 시간 수집
                        existing_times = []
                        for j in range(app_item.childCount()):
                            child = app_item.child(j)
                            if child.data(0, Qt.UserRole) == window_title:
                                existing_times.append(child.text(1))
                        
                        # 새로운 시작 시간이 있으면 맨 위에 추가
                        sorted_times = sorted(start_times, reverse=True)  # 최신 시간이 먼저 오도록 정렬
                        for start_time in sorted_times:
                            if start_time not in existing_times:
                                # 새 아이템을 맨 앞에 삽입
                                window_item = QTreeWidgetItem()
                                window_item.setText(0, window_title)
                                window_item.setData(0, Qt.UserRole, window_title)
                                window_item.setText(1, start_time)
                                window_item.setText(2, '')
                                window_item.setText(3, '')
                                # 맨 앞에 삽입
                                app_item.insertChild(0, window_item)
        
        # 확장 상태 복원
        # self.restore_expanded_state()

    def calculate_total_time(self, app_data):
        """앱의 총 사용 시간을 계산합니다."""
        total_time = 0
        windows = app_data.get('windows', {})
        for window_time in windows.values():
            if isinstance(window_time, (int, float)):
                total_time += window_time
        return total_time

    def update_total_time(self):
        """총 사용 시간을 업데이트합니다."""
        try:
            current_date = datetime.now().date().strftime('%Y-%m-%d')
            if 'dates' not in self.app_usage or current_date not in self.app_usage['dates']:
                self.total_time_label.setText("00:00:00")
                return
            
            date_data = self.app_usage['dates'][current_date]
            total_time = sum(app_data.get('total_time', 0) 
                           for app_data in date_data.values() 
                           if isinstance(app_data, dict))
            
            self.total_time_label.setText(self.format_time(total_time))
            
        except Exception as e:
            print(f"총 시간 업데이트 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()

    def format_time(self, seconds):
        """초를 시:분:초 형식으로 변환합니다."""
        try:
            if isinstance(seconds, dict):
                seconds = seconds.get('total_time', 0)
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            seconds = int(seconds % 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        except Exception as e:
            print(f"시간 포맷팅 중 오류 발생: {e}")
            return "00:00:00"

    def _update_app_list(self):
        """앱 목록을 업데이트합니다."""
        try:
            current_date = datetime.now().date().strftime('%Y-%m-%d')
            if current_date not in self.app_usage['dates']:
                return
            
            # 현재 선택된 앱 저장
            current_app = self.app_list.currentItem()
            current_app_name = current_app.data(Qt.UserRole) if current_app else None
            
            # 목록 업데이트 시작
            self.app_list.blockSignals(True)
            self.app_list.clear()
            
            # 앱 데이터 정렬 (사용 시간 기준)
            app_data = []
            for app_name, data in self.app_usage['dates'][current_date].items():
                if app_name == APP_NAME:
                    continue
                total_time = sum(window_time for window_time in data.get('windows', {}).values())
                app_data.append((app_name, total_time))
            
            app_data.sort(key=lambda x: x[1], reverse=True)
            
            # 앱 목록 추가
            selected_item = None
            for app_name, total_time in app_data:
                item = QListWidgetItem()
                item.setText(f"{app_name} ({self.format_time(total_time)})")
                item.setData(Qt.UserRole, app_name)
                self.app_list.addItem(item)
                
                # 이전에 선택된 앱과 같은 앱이면 저장
                if app_name == current_app_name:
                    selected_item = item
            
            # 이전 선택 복원
            if selected_item:
                self.app_list.setCurrentItem(selected_item)
            
            self.app_list.blockSignals(False)
            
        except Exception as e:
            print(f"앱 목록 업데이트 중 오류 발생: {e}")
            traceback.print_exc()

    def _on_app_selected(self, current, previous):
        """앱이 선택되었을 때 호출됩니다."""
        if current:
            app_name = current.data(Qt.UserRole)
            self._update_detail_view(app_name)

    def _update_detail_view(self, app_name):
        """선택된 앱의 상세 정보를 업데이트합니다."""
        try:
            current_date = datetime.now().date().strftime('%Y-%m-%d')
            if current_date not in self.app_usage['dates'] or app_name not in self.app_usage['dates'][current_date]:
                return
            
            app_data = self.app_usage['dates'][current_date][app_name]
            windows = app_data.get('windows', {})
            start_times = app_data.get('start_times', [])
            
            # 테이블 업데이트 시작
            self.detail_table.setRowCount(0)
            
            # 창별 정보 추가
            for window_title, window_time in windows.items():
                if isinstance(window_title, tuple):
                    window_title = window_title[1] if len(window_title) > 1 else window_title[0]
                
                row = self.detail_table.rowCount()
                self.detail_table.insertRow(row)
                
                # 창 제목
                title_item = QTableWidgetItem(window_title)
                self.detail_table.setItem(row, 0, title_item)
                
                # 시작 시간 (가장 최근 시간 사용)
                start_time = start_times[-1] if start_times else ""
                time_item = QTableWidgetItem(start_time)
                self.detail_table.setItem(row, 1, time_item)
                
                # 사용 시간
                duration_item = QTableWidgetItem(self.format_time(window_time))
                self.detail_table.setItem(row, 2, duration_item)
            
        except Exception as e:
            print(f"상세 정보 업데이트 중 오류 발생: {e}")
            traceback.print_exc()

    def setup_style(self):
        # 다크 테마 스타일
        dark_style = """
            QWidget {
                background-color: #1E1E1E;
                color: white;
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
            QLabel {
                color: white;
            }
        """
        self.setStyleSheet(dark_style)

class Home_app_tracking(AppTrackingWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 초기화 변수 설정
        self._last_time_update = time.time()
        self._update_interval = 1.0
        self.tree_widget = None  # tree_widget 사용하지 않음
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # UI 초기화
        self._init_ui(layout)
        
        # 타이머 설정
        self.timer.setInterval(1000)
        
        # 그래프 업데이트 타이머
        self.graph_timer = QTimer(self)
        self.graph_timer.timeout.connect(self._update_graph)
        self.graph_timer.start(1000)
        
        # 초기 데이터 업데이트
        self._update_graph()

    def _init_ui(self, layout):
        # Total 시간과 그래프를 포함하는 컨테이너
        total_graph_container = QWidget()
        total_graph_layout = QVBoxLayout(total_graph_container)
        total_graph_layout.setContentsMargins(0, 0, 0, 0)
        
        # Total 시간
        total_container = QWidget()
        total_layout = QHBoxLayout(total_container)
        total_layout.setContentsMargins(0, 0, 0, 0)
        
        self.total_label = QLabel("Total")
        self.total_label.setFont(QFont("Arial", 20, QFont.Bold))
        self.total_time_label = QLabel("00:00:00")
        self.total_time_label.setFont(QFont("Arial", 20, QFont.Bold))
        
        total_layout.addWidget(self.total_label)
        total_layout.addStretch()
        total_layout.addWidget(self.total_time_label)
        
        # 시간 그래프
        self.time_graph = TimeGraphWidget()
        
        # 컨테이너에 위젯 추가
        total_graph_layout.addWidget(total_container)
        total_graph_layout.addWidget(self.time_graph)
        
        # 앱 목록과 상세 정보를 포함할 컨테이너
        content_container = QWidget()
        content_layout = QHBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        # 앱 목록 (왼쪽)
        app_list_container = QWidget()
        app_list_layout = QVBoxLayout(app_list_container)
        app_list_layout.setContentsMargins(0, 0, 0, 0)
        
        # 앱 목록 레이블
        app_list_label = QLabel("Applications")
        app_list_label.setFont(QFont("Arial", 16, QFont.Bold))
        app_list_layout.addWidget(app_list_label)
        
        # 앱 목록 위젯
        self.app_list = QListWidget()
        self.app_list.setFont(QFont("Arial", 14))
        self.app_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.app_list.setHorizontalScrollMode(QListWidget.ScrollPerPixel)
        self.app_list.setUniformItemSizes(True)
        self.app_list.currentItemChanged.connect(self._on_app_selected)
        app_list_layout.addWidget(self.app_list)
        
        # 상세 정보 패널 (오른쪽)
        detail_container = QWidget()
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        
        # 상세 정보 레이블
        detail_label = QLabel("Details")
        detail_label.setFont(QFont("Arial", 16, QFont.Bold))
        detail_layout.addWidget(detail_label)
        
        # 상세 정보 테이블
        self.detail_table = QTableWidget()
        self.detail_table.setColumnCount(3)
        self.detail_table.setHorizontalHeaderLabels(["Window", "Start Time", "Duration"])
        self.detail_table.setFont(QFont("Arial", 14))
        self.detail_table.verticalHeader().setVisible(False)
        self.detail_table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.detail_table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        
        # 테이블 헤더 설정
        header = self.detail_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.detail_table.setColumnWidth(1, 100)
        self.detail_table.setColumnWidth(2, 100)
        
        detail_layout.addWidget(self.detail_table)
        
        # 컨테이너에 위젯 추가
        content_layout.addWidget(app_list_container, 1)
        content_layout.addWidget(detail_container, 2)
        
        # 메인 레이아웃에 위젯 추가
        layout.addWidget(total_graph_container)
        layout.addWidget(content_container)
        
        # 스타일 설정
        self.setup_style()

    def _update_graph(self):
        """그래프와 UI를 업데이트합니다."""
        try:
            if not hasattr(self, 'time_graph') or not hasattr(self, 'app_usage'):
                return
            
            update_start = time.time()
            
            # 그래프 데이터 업데이트
            self.time_graph.update_data(self.app_usage)
            
            # 앱 목록과 상세 정보 업데이트
            if update_start - self._last_time_update >= self._update_interval:
                # 현재 선택된 앱 저장
                current_app = self.app_list.currentItem()
                current_app_name = current_app.data(Qt.UserRole) if current_app else None
                
                # 앱 목록 업데이트
                self._update_app_list()
                
                # 선택된 앱이 있었다면 다시 선택
                if current_app_name:
                    for i in range(self.app_list.count()):
                        item = self.app_list.item(i)
                        if item.data(Qt.UserRole) == current_app_name:
                            self.app_list.setCurrentItem(item)
                            # 상세 정보 업데이트
                            self._update_detail_view(current_app_name)
                            break
                
                self._last_time_update = update_start
            else:
                # 업데이트 간격이 아니더라도 선택된 앱의 상세 정보는 업데이트
                current_app = self.app_list.currentItem()
                if current_app:
                    app_name = current_app.data(Qt.UserRole)
                    self._update_detail_view(app_name)
            
            # 총 시간 업데이트
            self.update_total_time()
            
        except Exception as e:
            print(f"그래프 업데이트 중 오류 발생: {e}")
            traceback.print_exc()

    def _update_app_list(self):
        """앱 목록을 업데이트합니다."""
        try:
            current_date = datetime.now().date().strftime('%Y-%m-%d')
            if current_date not in self.app_usage['dates']:
                return
            
            # 현재 선택된 앱 저장
            current_app = self.app_list.currentItem()
            current_app_name = current_app.data(Qt.UserRole) if current_app else None
            
            # 목록 업데이트 시작
            self.app_list.blockSignals(True)
            self.app_list.clear()
            
            # 앱 데이터 정렬 (사용 시간 기준)
            app_data = []
            for app_name, data in self.app_usage['dates'][current_date].items():
                if app_name == APP_NAME:
                    continue
                total_time = sum(window_time for window_time in data.get('windows', {}).values())
                app_data.append((app_name, total_time))
            
            app_data.sort(key=lambda x: x[1], reverse=True)
            
            # 앱 목록 추가
            selected_item = None
            for app_name, total_time in app_data:
                item = QListWidgetItem()
                item.setText(f"{app_name} ({self.format_time(total_time)})")
                item.setData(Qt.UserRole, app_name)
                self.app_list.addItem(item)
                
                # 이전에 선택된 앱과 같은 앱이면 저장
                if app_name == current_app_name:
                    selected_item = item
            
            # 이전 선택 복원
            if selected_item:
                self.app_list.setCurrentItem(selected_item)
            
            self.app_list.blockSignals(False)
            
        except Exception as e:
            print(f"앱 목록 업데이트 중 오류 발생: {e}")
            traceback.print_exc()

    def _on_app_selected(self, current, previous):
        """앱이 선택되었을 때 호출됩니다."""
        if current:
            app_name = current.data(Qt.UserRole)
            self._update_detail_view(app_name)

    def _update_detail_view(self, app_name):
        """선택된 앱의 상세 정보를 업데이트합니다."""
        try:
            current_date = datetime.now().date().strftime('%Y-%m-%d')
            if current_date not in self.app_usage['dates'] or app_name not in self.app_usage['dates'][current_date]:
                return
            
            app_data = self.app_usage['dates'][current_date][app_name]
            windows = app_data.get('windows', {})
            start_times = app_data.get('start_times', [])
            
            # 테이블 업데이트 시작
            self.detail_table.setRowCount(0)
            
            # 창별 정보 추가
            for window_title, window_time in windows.items():
                if isinstance(window_title, tuple):
                    window_title = window_title[1] if len(window_title) > 1 else window_title[0]
                
                row = self.detail_table.rowCount()
                self.detail_table.insertRow(row)
                
                # 창 제목
                title_item = QTableWidgetItem(window_title)
                self.detail_table.setItem(row, 0, title_item)
                
                # 시작 시간 (가장 최근 시간 사용)
                start_time = start_times[-1] if start_times else ""
                time_item = QTableWidgetItem(start_time)
                self.detail_table.setItem(row, 1, time_item)
                
                # 사용 시간
                duration_item = QTableWidgetItem(self.format_time(window_time))
                self.detail_table.setItem(row, 2, duration_item)
            
        except Exception as e:
            print(f"상세 정보 업데이트 중 오류 발생: {e}")
            traceback.print_exc()

    def setup_style(self):
        # 다크 테마 스타일
        dark_style = """
            QWidget {
                background-color: #1E1E1E;
                color: white;
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
            QLabel {
                color: white;
            }
        """
        self.setStyleSheet(dark_style)