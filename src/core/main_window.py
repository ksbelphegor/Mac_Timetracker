"""
Mac Time Tracker — AppKit 네이티브 메인 창

앱 사용 통계를 보여주는 메인 윈도우를 관리합니다.
"""
import os
import time
import logging
from datetime import datetime

import objc
from Foundation import NSObject, NSMakeRect, NSMakeSize
from AppKit import (
    NSApplication, NSWindow,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable, NSWindowStyleMaskResizable,
    NSTableView, NSTableColumn, NSTableViewSelectionHighlightStyleRegular,
    NSTableViewColumnAutoresizingMask,
    NSScrollView, NSScrollViewHasVerticalScroller,
    NSView, NSTextField,
    NSColor, NSFont,
    NSSplitView, NSScreen,
)

from src.core.config import APP_NAME, APP_VERSION
from src.core.data_manager import DataManager

logger = logging.getLogger(APP_NAME)


class MainWindow(NSObject):
    """메인 윈도우 컨트롤러 — 앱 사용 통계 표시"""

    def init(self):
        self = objc.super(MainWindow, self).init()
        if self is None:
            return None
        self.window = None
        self.data_manager = DataManager.get_instance()
        self._app_items = []
        self.tableView = None
        self.detailLabel = None
        self.windowDetailLabel = None
        self._last_refresh = 0
        self._refresh_interval = 2.0
        return self

    def show(self):
        """윈도우를 생성/표시합니다."""
        if self.window is None:
            self._create_window()
        self.window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def _create_window(self):
        screen = NSScreen.mainScreen().visibleFrame()
        win_w, win_h = 800, 500
        x = (screen.size.width - win_w) / 2
        y = (screen.size.height - win_h) / 2

        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, win_w, win_h),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
            NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable,
            2, False
        )
        self.window.setTitle_(f"{APP_NAME} v{APP_VERSION}")
        self.window.setMinSize_(NSMakeSize(500, 300))
        self.window.setReleasedWhenClosed_(False)
        self.window.setDelegate_(self)
        self.window.setBackgroundColor_(NSColor.darkGrayColor())

        self._refresh_app_data()
        self._build_ui()

    def _build_ui(self):
        """UI 구성"""
        frame = self.window.contentView().bounds()

        self.splitView = NSSplitView.alloc().initWithFrame_(frame)
        self.splitView.setVertical_(True)
        self.splitView.setDividerStyle_(1)  # Thin divider

        # 왼쪽: 앱 목록
        self._build_app_list()

        # 오른쪽: 상세
        self._build_detail()

        self.window.contentView().addSubview_(self.splitView)
        self.splitView.adjustSubviews()

    def _build_app_list(self):
        """앱 목록 테이블"""
        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, 250, 100))
        scroll.setHasVerticalScroller_(True)
        scroll.setAutoresizesSubviews_(True)

        self.tableView = NSTableView.alloc().initWithFrame_(NSMakeRect(0, 0, 250, 100))

        col_name = NSTableColumn.alloc().initWithIdentifier_("app_name")
        col_name.headerCell().setStringValue_("앱")
        col_name.setWidth_(150)
        self.tableView.addTableColumn_(col_name)

        col_time = NSTableColumn.alloc().initWithIdentifier_("app_time")
        col_time.headerCell().setStringValue_("사용 시간")
        col_time.setWidth_(80)
        col_time.setResizingMask_(NSTableViewColumnAutoresizingMask)
        self.tableView.addTableColumn_(col_time)

        self.tableView.setDataSource_(self)
        self.tableView.setDelegate_(self)
        self.tableView.setSelectionHighlightStyle_(NSTableViewSelectionHighlightStyleRegular)
        self.tableView.setTarget_(self)
        self.tableView.setDoubleAction_("tableViewDoubleClick:")

        scroll.setDocumentView_(self.tableView)
        self.splitView.addSubview_(scroll)

    def _build_detail(self):
        """상세 정보 패널"""
        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, 500, 100))
        scroll.setHasVerticalScroller_(True)

        content = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 500, 300))

        self.detailLabel = NSTextField.alloc().initWithFrame_(NSMakeRect(15, 250, 470, 24))
        self.detailLabel.setBezeled_(False)
        self.detailLabel.setDrawsBackground_(False)
        self.detailLabel.setTextColor_(NSColor.whiteColor())
        self.detailLabel.setFont_(NSFont.boldSystemFontOfSize_(16))
        self.detailLabel.setStringValue_("앱을 선택하세요")
        content.addSubview_(self.detailLabel)

        # 구분선 (간단한 라벨로)
        sep = NSTextField.alloc().initWithFrame_(NSMakeRect(15, 240, 470, 1))
        sep.setBezeled_(False)
        sep.setDrawsBackground_(True)
        sep.setBackgroundColor_(NSColor.grayColor())
        sep.setEditable_(False)
        content.addSubview_(sep)

        self.windowDetailLabel = NSTextField.alloc().initWithFrame_(NSMakeRect(15, 10, 470, 220))
        self.windowDetailLabel.setBezeled_(False)
        self.windowDetailLabel.setDrawsBackground_(False)
        self.windowDetailLabel.setTextColor_(NSColor.lightGrayColor())
        self.windowDetailLabel.setFont_(NSFont.systemFontOfSize_(12))
        self.windowDetailLabel.setStringValue_("선택한 앱의 창별 사용 시간이 여기에 표시됩니다.")
        content.addSubview_(self.windowDetailLabel)

        scroll.setDocumentView_(content)
        self.splitView.addSubview_(scroll)

    def _refresh_app_data(self):
        """DataManager에서 오늘 데이터 로드"""
        today = datetime.now().strftime('%Y-%m-%d')
        usage = self.data_manager.load_app_usage()
        dates = usage.get('dates', {}) if usage else {}
        today_data = dates.get(today, {})

        items = []
        for name, data in today_data.items():
            if name == APP_NAME:
                continue
            total = data.get('total_time', 0) if isinstance(data, dict) else 0
            items.append((name, total))

        items.sort(key=lambda x: x[1], reverse=True)
        self._app_items = items

    def refresh(self):
        """화면 갱신 (timer-driven)"""
        now = time.time()
        if now - self._last_refresh < self._refresh_interval:
            return
        self._last_refresh = now

        self._refresh_app_data()
        if self.tableView:
            self.tableView.reloadData()

        sel = self.tableView.selectedRow()
        if sel >= 0 and sel < len(self._app_items):
            self._update_detail(sel)

    def _update_detail(self, row):
        """선택한 앱의 상세 정보 갱신"""
        if row < 0 or row >= len(self._app_items):
            return
        app_name, total_time = self._app_items[row]

        h = int(total_time // 3600)
        m = int((total_time % 3600) // 60)
        s = int(total_time % 60)
        self.detailLabel.setStringValue_(f"{app_name} — {h:02d}:{m:02d}:{s:02d}")

        # 창 정보
        today = datetime.now().strftime('%Y-%m-%d')
        usage = self.data_manager.load_app_usage()
        dates = usage.get('dates', {}) if usage else {}
        app_data = dates.get(today, {}).get(app_name, {})
        windows = app_data.get('windows', {}) if isinstance(app_data, dict) else {}

        lines = [f"「{app_name}」 창별 사용 시간:\n"]
        for win, wt in sorted(windows.items(), key=lambda x: x[1], reverse=True):
            wh = int(wt // 3600)
            wm = int((wt % 3600) // 60)
            ws = int(wt % 60)
            display_win = str(win).split("::")[-1] if "::" in str(win) else str(win)
            lines.append(f"  • {display_win}  {wh:02d}:{wm:02d}:{ws:02d}")

        self.windowDetailLabel.setStringValue_(
            "\n".join(lines) if len(lines) > 1 else "  (기록된 창 정보 없음)"
        )

    # ── NSTableViewDataSource ──
    def numberOfRowsInTableView_(self, tableView):
        return len(self._app_items)

    def tableView_objectValueForTableColumn_row_(self, tv, col, row):
        if row < 0 or row >= len(self._app_items):
            return ""
        name, total = self._app_items[row]
        if col.identifier() == "app_name":
            return name
        h = int(total // 3600)
        m = int((total % 3600) // 60)
        return f"{h:02d}:{m:02d}"

    # ── NSTableViewDelegate ──
    def tableViewSelectionDidChange_(self, notification):
        self._update_detail(self.tableView.selectedRow())

    def tableViewDoubleClick_(self, sender):
        row = self.tableView.clickedRow()
        if 0 <= row < len(self._app_items):
            name = self._app_items[row][0]
            logger.info(f"앱 선택됨: {name}")

    # ── NSWindowDelegate ──
    def windowWillClose_(self, notification):
        pass
