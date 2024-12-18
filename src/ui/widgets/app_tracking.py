from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, 
                            QTreeWidgetItem, QHeaderView, QToolTip)
from PyQt5.QtCore import QTimer, Qt, QRect, QPoint
from PyQt5.QtGui import QFont, QPainter, QColor, QPen
import time
from datetime import datetime, timedelta
from core.data_manager import DataManager
import subprocess
from Foundation import NSWorkspace
import os
from core.config import APP_NAME

class TimeGraphWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(50)
        self.setMouseTracking(True)  # 마우스 추적 활성화
        
        # 줌 관련 변수
        self.zoom_level = 1.0  # 1.0 = 24시간
        self.center_time = None  # 줌 중심점 (현재 시각)
        
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
            QColor(255, 50, 50),   # 빨강
            QColor(50, 255, 50),   # 초록
            QColor(50, 50, 255),   # 파랑
            QColor(255, 255, 50),  # 노랑
            QColor(255, 50, 255),  # 마젠타
            QColor(50, 255, 255),  # 시안
        ]
    
    def wheelEvent(self, event):
        """마우스 휠 이벤트 처리"""
        # 현재 마우스 위치의 시각 계산
        width = self.width()
        x = event.pos().x()
        now = datetime.now()
        day_start = datetime(now.year, now.month, now.day).timestamp()
        
        # 줌 중심점이 없으면 마우스 위치를 중심점으로 설정
        if self.center_time is None:
            self.center_time = day_start + (x / width * 24 * 3600 * self.zoom_level)
        
        # 줌 레벨 조정 (휠 위로 = 확대, 아래로 = 축소)
        if event.angleDelta().y() > 0:
            self.zoom_level = max(0.1, self.zoom_level * 0.9)  # 확대
        else:
            self.zoom_level = min(2.0, self.zoom_level * 1.1)  # 축소
        
        self.update()
    
    def mousePressEvent(self, event):
        """마우스 클릭 이벤트 처리"""
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.drag_start_pos = event.pos()
            self.drag_start_time = self.center_time
    
    def mouseReleaseEvent(self, event):
        """마우스 릴리즈 이벤트 처리"""
        if event.button() == Qt.LeftButton:
            self.is_dragging = False
            self.drag_start_pos = None
            self.drag_start_time = None
    
    def mouseMoveEvent(self, event):
        """마우스 이동 시 드래그 및 툴팁 처리"""
        if self.is_dragging and self.drag_start_pos is not None:
            # 드래그 거리를 시간으로 변환
            dx = self.drag_start_pos.x() - event.pos().x()
            visible_duration = 24 * 3600 * self.zoom_level
            dt = dx * visible_duration / self.width()
            
            # 중심 시간 이동
            self.center_time = self.drag_start_time + dt
            self.update()
        
        # 툴팁 표시
        if hasattr(self.window(), 'app_usage'):
            current_time = time.time()
            width = self.width()
            x = event.pos().x()
            
            # 현재 시각 (자정 기준)
            now = datetime.now()
            day_start = datetime(now.year, now.month, now.day).timestamp()
            
            # 마우스 위치의 시각 (줌 레벨 적용)
            visible_duration = 24 * 3600 * self.zoom_level
            if self.center_time is None:
                self.center_time = day_start + visible_duration / 2
            
            time_start = self.center_time - visible_duration / 2
            hover_time = time_start + (x / width * visible_duration)
            
            # 해당 시각에 실행 중이던 앱 찾기
            active_apps = []
            for app_name, app_data in self.window().app_usage.items():
                start_time = max(day_start, 
                              app_data.get('last_update', current_time) - app_data.get('total_time', 0))
                end_time = app_data.get('last_update', current_time)
                
                if start_time <= hover_time <= end_time:
                    # 해당 시점의 시간 표시
                    hover_dt = datetime.fromtimestamp(hover_time)
                    window_name = app_data.get('last_window', '')
                    active_apps.append(f"{app_name}\n- {window_name}\n- 시각: {hover_dt.strftime('%H:%M:%S')}")
            
            if active_apps:
                QToolTip.showText(event.globalPos(), "\n\n".join(active_apps))
            else:
                QToolTip.hideText()
    
    def get_app_color(self, app_name):
        """앱별로 고유한 색상 반환"""
        if app_name not in self.app_colors:
            self.app_colors[app_name] = self.colors[self.color_index % len(self.colors)]
            self.color_index += 1
        return self.app_colors[app_name]
    
    def format_duration(self, seconds):
        """초를 시:분:초 형식으로 변환"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 현재 시각 (자정 기준)
        now = datetime.now()
        day_start = datetime(now.year, now.month, now.day).timestamp()
        current_time = time.time()
        width = self.width()
        height = self.height()
        
        # 배경 (회색)
        painter.fillRect(self.rect(), QColor(50, 50, 50))
        
        # 보이는 시간 범위 계산
        visible_duration = 24 * 3600 * self.zoom_level
        if self.center_time is None:
            self.center_time = day_start + visible_duration / 2
        
        time_start = self.center_time - visible_duration / 2
        time_end = self.center_time + visible_duration / 2
        
        # 시간 눈금 (1시간 간격)
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        hour_start = int(time_start / 3600)
        hour_end = int(time_end / 3600) + 1
        
        for hour in range(hour_start, hour_end):
            hour_time = hour * 3600
            if time_start <= hour_time <= time_end:
                x = int(width * (hour_time - time_start) / visible_duration)
                painter.drawLine(x, 0, x, height)
                time_text = f"{hour % 24:02d}:00"
                painter.drawText(x + 2, height - 2, time_text)
        
        # 앱 사용 시간
        if hasattr(self.window(), 'app_usage'):
            bar_height = height - 20  # 모든 앱이 전체 높이 사용
            
            # 앱별 투명도 설정
            opacity = min(0.7, 1.0 / len(self.window().app_usage))
            
            for app_name, app_data in self.window().app_usage.items():
                # 앱의 시작 시간을 오늘 자정 이후로 조정
                start_time = max(day_start, 
                              app_data.get('last_update', current_time) - app_data.get('total_time', 0))
                end_time = app_data.get('last_update', current_time)
                
                # 시작 시간과 현재 시간을 화면 좌표로 변환
                if start_time <= time_end and end_time >= time_start:
                    x_start = int(width * (max(start_time, time_start) - time_start) / visible_duration)
                    x_end = int(width * (min(end_time, time_end) - time_start) / visible_duration)
                    
                    color = self.get_app_color(app_name)
                    color.setAlphaF(opacity)  # 투명도 설정
                    painter.fillRect(x_start, 0, x_end - x_start, bar_height, color)
        
        # 테두리
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        painter.drawRect(0, 0, width - 1, height - 1)

class Home_app_tracking(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # 시작 시간 및 업데이트 관련 변수 초기화
        self.start_time = time.time()
        self._last_update = time.time()
        self._update_interval = 1.0  # 1초로 변경
        self._pending_updates = set()
        
        # 앱 사용 시간 데이터
        self.app_usage = DataManager.load_app_usage() or {}
        self.active_app = None
        self.active_window = None
        self.active_start_time = None
        
        # 트리 위젯의 확장 상태 저장
        self._expanded_items = set()
        
        # 폰트 설정
        self.app_font = QFont("Arial", 15)  # 14에서 15로 변경
        self.window_font = QFont("Arial", 13)  # 12에서 13으로 변경
        
        # 캐시 및 상태 변수 초기화
        self._widgets_cache = {}
        self._is_active = True
        self.MAX_ITEMS = 100
        
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
        
        # 트리 위젯 설정
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderHidden(False)
        self.tree_widget.setColumnCount(2)
        self.tree_widget.setHeaderLabels(["Name", "Time"])
        
        # 헤더 설정
        header = self.tree_widget.header()
        header.setSectionsMovable(True)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        
        # Name 열의 너비를 화면의 절반으로 설정
        self.tree_widget.setColumnWidth(0, 512)
        self.tree_widget.setColumnWidth(1, 200)
        
        # 헤더 클릭 시 정렬 이벤트 연결
        self.tree_widget.header().sectionClicked.connect(self.on_header_clicked)
        
        # 정렬 상태 추적을 위한 변수
        self.sort_column = 1
        self.sort_order = Qt.DescendingOrder
        
        # 초기 정렬 설정
        self.tree_widget.sortItems(self.sort_column, self.sort_order)
        
        # 스타일 설정
        self.setup_style()
        
        # 레이아웃에 위젯 추가
        layout.addWidget(total_graph_container)
        layout.addWidget(self.tree_widget)
        
        # 타이머 설정
        self.setup_timers()

    def setup_style(self):
        # 헤더와 아이템 폰트 크기 설정
        header_font = QFont("Arial", 17, QFont.Bold)
        item_font = QFont("Arial", 15)
        
        self.tree_widget.headerItem().setFont(0, header_font)
        self.tree_widget.headerItem().setFont(1, header_font)
        
        self.tree_widget.setStyleSheet("""
            QTreeWidget {
                background-color: #1E1E1E;
                color: white;
                border: none;
                font-size: 15px;
            }
            QTreeWidget::item {
                padding: 8px;
                border-bottom: 1px solid #3C3C3C;
                height: 35px;
            }
            QTreeWidget::item:selected {
                background-color: #404040;
            }
            QHeaderView::section {
                background-color: #2C2C2C;
                color: white;
                padding: 10px;
                border: 1px solid #3C3C3C;
                font-size: 17px;
            }
            QHeaderView::section:hover {
                background-color: #404040;
            }
        """)

    def setup_timers(self):
        # 앱 사용 시간 업데이트 타이머
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_usage_stats)
        self.update_timer.start(1000)  # 1초마다 업데이트
        
        # 총 시간 업데이트 타이머
        self.total_timer = QTimer(self)
        self.total_timer.timeout.connect(self.update_total_time)
        self.total_timer.start(1000)
        
        # 레이아웃 업데이트 타이머
        self._layout_update_timer = QTimer(self)
        self._layout_update_timer.timeout.connect(self._update_layout)
        self._layout_update_timer.setSingleShot(True)

    def showEvent(self, event):
        self._is_active = True
        super().showEvent(event)
        
    def hideEvent(self, event):
        self._is_active = False
        super().hideEvent(event)

    def update_usage_stats(self):
        if not self._is_active:
            return
            
        current_time = time.time()
        if current_time - self._last_update < self._update_interval:
            return

        try:
            # 현재 활성 앱 정보 가져오기
            active_app = NSWorkspace.sharedWorkspace().activeApplication()
            if active_app:
                app_bundle = active_app.get('NSApplicationBundleIdentifier', '')
                app_name = active_app.get('NSApplicationName', '')
                app_path = active_app.get('NSApplicationPath', '')
                
                print(f"Debug - App Info: name={app_name}, bundle={app_bundle}, path={app_path}")
                
                # Python 관련 프로세스인 경우 APP_NAME 사용
                if (app_name.lower() in ['python', 'python3', 'python.app'] or 
                    'python' in app_name.lower() or
                    'python' in app_bundle.lower() or
                    'python' in app_path.lower()):
                    print(f"Debug - Detected Python process, changing name from {app_name} to {APP_NAME}")
                    app_name = APP_NAME
                
                window_title = self.get_active_window_title()
                print(f"Debug - Window Title: {window_title}")
                
                # 앱이 변경되었거나 처음 시작할 때
                if app_name != self.active_app:
                    if self.active_app and self.active_start_time:
                        # 이전 앱의 사용 시간 업데이트
                        elapsed = current_time - self.active_start_time
                        self.update_app_time(self.active_app, self.active_window, elapsed)
                    
                    # 새 앱 정보 설정
                    self.active_app = app_name
                    self.active_window = window_title
                    self.active_start_time = current_time
                    print(f"Debug - App changed to: {app_name}")
                elif window_title != self.active_window:
                    # 같은 앱의 다른 창으로 전환
                    if self.active_start_time:
                        elapsed = current_time - self.active_start_time
                        self.update_app_time(self.active_app, self.active_window, elapsed)
                    self.active_window = window_title
                    self.active_start_time = current_time
                else:
                    # 같은 앱을 계속 사용 중일 때도 시간 업데이트
                    elapsed = current_time - self.active_start_time
                    self.update_app_time(self.active_app, self.active_window, elapsed)
                    self.active_start_time = current_time  # 시작 시간 갱신
            
            # 트리 위젯 업데이트
            self.update_tree_widget()
            
            # 현재 상태 저장
            DataManager.save_app_usage(self.app_usage)
            self._last_update = current_time

        except Exception as e:
            print(f"Error in update_usage_stats: {e}")
    
    def update_app_time(self, app_name, window_title, elapsed):
        """앱과 창의 사용 시간을 업데이트합니다."""
        if not app_name:
            return
            
        if app_name not in self.app_usage:
            self.app_usage[app_name] = {
                'total_time': 0,
                'windows': {}
            }
        
        self.app_usage[app_name]['total_time'] = self.app_usage[app_name].get('total_time', 0) + elapsed
        
        if window_title:
            if 'windows' not in self.app_usage[app_name]:
                self.app_usage[app_name]['windows'] = {}
            self.app_usage[app_name]['windows'][window_title] = (
                self.app_usage[app_name]['windows'].get(window_title, 0) + elapsed
            )
    
    def update_tree_widget(self):
        """트리 위젯의 내용을 업데이트합니다."""
        current_sort_column = self.tree_widget.sortColumn()
        current_sort_order = self.tree_widget.header().sortIndicatorOrder()
        
        # 현재 선택된 아이템 저장
        selected_items = []
        for item in self.tree_widget.selectedItems():
            path = []
            current = item
            while current:
                path.insert(0, current.text(0))
                current = current.parent()
            selected_items.append(path)
        
        # 현재 확장된 아이템들 저장
        self._expanded_items = {
            self.tree_widget.itemFromIndex(index).text(0)
            for index in self._iter_tree_indexes()
            if self.tree_widget.isExpanded(index)
        }
        
        self.tree_widget.setSortingEnabled(False)
        self.tree_widget.clear()
        
        # 아이템 맵 초기화 (경로로 아이템을 찾기 위함)
        self._item_map = {}
        
        for app_name, app_data in self.app_usage.items():
            total_time = app_data.get('total_time', 0)
            if total_time > 0:
                app_item = QTreeWidgetItem(self.tree_widget)
                app_item.setText(0, app_name)
                app_item.setFont(0, self.app_font)
                app_item.setFont(1, self.app_font)
                
                time_str = self.format_time(total_time)
                app_item.setText(1, time_str)
                app_item.setData(1, Qt.UserRole, total_time)
                
                self._item_map[app_name] = app_item
                
                # 이전에 확장되어 있었다면 다시 확장
                if app_name in self._expanded_items:
                    self.tree_widget.expandItem(app_item)
                
                for window_name, window_time in app_data.get('windows', {}).items():
                    window_item = QTreeWidgetItem(app_item)
                    window_item.setText(0, window_name)
                    window_item.setFont(0, self.window_font)
                    window_item.setFont(1, self.window_font)
                    
                    window_time_str = self.format_time(window_time)
                    window_item.setText(1, window_time_str)
                    window_item.setData(1, Qt.UserRole, window_time)
                    
                    self._item_map[f"{app_name}/{window_name}"] = window_item
        
        # 이전에 선택된 아이템 복원
        for path in selected_items:
            item = None
            full_path = ""
            for i, name in enumerate(path):
                full_path = "/".join(path[:i+1])
                item = self._item_map.get(full_path)
                if item:
                    item.setSelected(True)
                    if i < len(path) - 1:  # 마지막 아이템이 아니면 확장
                        self.tree_widget.expandItem(item)
        
        self.tree_widget.setSortingEnabled(True)
        self.tree_widget.sortItems(current_sort_column, current_sort_order)
    
    def _iter_tree_indexes(self):
        """트리 위젯의 모든 인덱스를 순회합니다."""
        def recurse(parent_index):
            if not parent_index.isValid():
                for i in range(self.tree_widget.topLevelItemCount()):
                    child_index = self.tree_widget.model().index(i, 0)
                    yield child_index
                    yield from recurse(child_index)
            else:
                for i in range(self.tree_widget.model().rowCount(parent_index)):
                    child_index = self.tree_widget.model().index(i, 0, parent_index)
                    yield child_index
                    yield from recurse(child_index)
        
        yield from recurse(self.tree_widget.rootIndex())
    
    def get_active_window_title(self):
        """현재 활성 창의 제목을 가져옵니다."""
        try:
            active_app = NSWorkspace.sharedWorkspace().activeApplication()
            if not active_app:
                return None
            
            app_name = active_app['NSApplicationName']
            app_path = active_app.get('NSApplicationPath', '')
            
            print(f"Debug - Active Window Check: app_name={app_name}, is_active={self.window().isActiveWindow() if hasattr(self, 'window') else False}")
            
            # 현재 앱이 맥 타임좌인 경우
            if ('python' in app_name.lower() or 'python' in app_path.lower()):
                # 현재 창이 활성화되어 있는지 확인
                current_window = self.window() if hasattr(self, 'window') else None
                if current_window and current_window.isActiveWindow():
                    print("Debug - Detected Home UI is active")
                    return 'Home'
                
                print(f"Debug - Window detection: has_window={hasattr(self, 'window')}, window_active={current_window.isActiveWindow() if current_window else False}")
            
            script = f'''
                tell application "System Events"
                    tell process "{app_name}"
                        try
                            get name of window 1
                        on error
                            return "{app_name}"
                        end try
                    end tell
                end tell
            '''
            
            p = subprocess.Popen(['osascript', '-e', script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                out, err = p.communicate(timeout=0.3)
                if p.returncode == 0 and out:
                    window_title = out.decode('utf-8').strip()
                    print(f"Debug - AppleScript window title: {window_title}")
                    return window_title
            except subprocess.TimeoutExpired:
                p.kill()
            
            print(f"Debug - Fallback to app_name: {app_name}")
            return app_name
            
        except Exception as e:
            print(f"Debug - Error getting window title: {e}")
            return None
    
    def format_time(self, seconds):
        """초를 시:분:초 형식으로 변환합니다."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def update_total_time(self):
        elapsed_time = time.time() - self.start_time
        hours, remainder = divmod(int(elapsed_time), 3600)
        minutes, seconds = divmod(remainder, 60)
        self.total_time_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    def _get_or_create_item(self, app_name):
        for i in range(self.tree_widget.topLevelItemCount()):
            item = self.tree_widget.topLevelItem(i)
            if item.text(0) == app_name:
                return item
        
        item = QTreeWidgetItem([app_name])
        self.tree_widget.addTopLevelItem(item)
        item_font = QFont("Arial", 15)
        item.setFont(0, item_font)
        item.setFont(1, item_font)
        return item

    def _get_or_create_window_item(self, parent_item, window_name):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.text(0) == window_name:
                return child
        
        child = QTreeWidgetItem([window_name])
        parent_item.addChild(child)
        item_font = QFont("Arial", 15)
        child.setFont(0, item_font)
        child.setFont(1, item_font)
        return child

    def on_header_clicked(self, logical_index):
        if logical_index == self.sort_column:
            self.sort_order = Qt.AscendingOrder if self.sort_order == Qt.DescendingOrder else Qt.DescendingOrder
        else:
            self.sort_column = logical_index
            self.sort_order = Qt.AscendingOrder if logical_index == 0 else Qt.DescendingOrder
        
        self.tree_widget.sortItems(self.sort_column, self.sort_order)

    def _update_layout(self):
        if not self._is_active:
            return

        try:
            main_window = self.window()
            if not hasattr(main_window, 'app_usage'):
                return

            self.tree_widget.setUpdatesEnabled(False)
            self.tree_widget.setSortingEnabled(False)

            # 가장 많이 사용된 앱 순으로 정렬
            sorted_apps = sorted(
                ((name, data) for name, data in main_window.app_usage.items() 
                 if data['total_time'] > 0),
                key=lambda x: x[1]['total_time'],
                reverse=True
            )[:self.MAX_ITEMS]

            # 현재 표시된 항목 추적
            current_items = set()

            for app_name, app_data in sorted_apps:
                current_items.add(app_name)
                app_item = self._widgets_cache.get(app_name)
                if not app_item:
                    app_item = QTreeWidgetItem()
                    self.tree_widget.addTopLevelItem(app_item)
                    self._widgets_cache[app_name] = app_item

                app_item.setText(0, app_name)
                total_time = app_data['total_time']
                hours, remainder = divmod(int(total_time), 3600)
                minutes, seconds = divmod(remainder, 60)
                app_item.setText(1, f"{hours:02d}:{minutes:02d}:{seconds:02d}")
                app_item.setData(1, Qt.UserRole, total_time)

            # 사용하지 않는 항목 제거
            for app_name in list(self._widgets_cache.keys()):
                if app_name not in current_items:
                    item = self._widgets_cache.pop(app_name)
                    index = self.tree_widget.indexOfTopLevelItem(item)
                    if index >= 0:
                        self.tree_widget.takeTopLevelItem(index)

            # 정렬 활성화 및 적용
            self.tree_widget.setSortingEnabled(True)
            self.tree_widget.sortItems(self.sort_column, self.sort_order)
            
            self.tree_widget.setUpdatesEnabled(True)

        except Exception as e:
            print(f"Error in _update_layout: {e}")
            self.tree_widget.setUpdatesEnabled(True)