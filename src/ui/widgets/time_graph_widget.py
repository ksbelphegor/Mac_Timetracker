from PyQt5.QtWidgets import QWidget, QToolTip
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont, QPainter, QColor, QPen
import time
from datetime import datetime
from src.core.config import APP_NAME
from src.core.data_manager import DataManager

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
                    duration_str = f"{int(duration // 3600):02d}:{int((duration % 3600) // 60):02d}"
                    tooltip_text = f"{app_name}\n시작: {start_dt.strftime('%H:%M:%S')}\n종료: {end_dt.strftime('%H:%M:%S')}\n사용 시간: {duration_str}"
                    QToolTip.showText(event.globalPos(), tooltip_text)
                else:
                    QToolTip.hideText()
            else:
                QToolTip.hideText()

    def _get_window_display_title(self, window_title):
        """창 제목을 표시용으로 변환합니다."""
        if isinstance(window_title, tuple):
            return window_title[1] if len(window_title) > 1 else window_title[0]
        return window_title 