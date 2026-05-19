import objc
import time
from Foundation import NSObject, NSMakeRect, NSMakePoint, NSMakeSize
from AppKit import (
    NSStatusBar, NSVariableStatusItemLength,
    NSImage, NSMenu, NSMenuItem,
    NSView, NSButton, NSButtonTypeMomentaryLight,
    NSTextField, NSTextAlignmentCenter,
    NSColor, NSBezierPath, NSFontWeightBold, NSFont
)
from src.core.config import APP_NAME, BUNDLE_ID, CONFIG


class StatusBarController(NSObject):
    """macOS 상태바 아이콘 + 시간 표시를 담당하는 AppKit 컨트롤러"""

    def init(self):
        self = objc.super(StatusBarController, self).init()
        if self is None:
            return None
        self.menu = None
        self._setup_status_item()
        self._setup_custom_view()
        return self

    def _setup_status_item(self):
        self.statusItem = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength)
        self.statusItem.setHighlightMode_(True)

    def _setup_custom_view(self):
        ui_config = CONFIG["ui"]
        bar_width = ui_config["status_bar_width"]
        bar_height = ui_config["status_bar_height"]
        icon_size = ui_config["icon_size"]

        self.custom_view = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, bar_width, bar_height))

        # 아이콘 버튼
        self.icon_view = NSButton.alloc().initWithFrame_(
            NSMakeRect(0, 0, icon_size, icon_size))
        self.icon_view.setButtonType_(NSButtonTypeMomentaryLight)
        self.icon_view.setBordered_(False)

        icon_image = NSImage.alloc().initWithSize_(
            NSMakeSize(icon_size, icon_size))
        icon_image.lockFocus()
        self._draw_clock_icon(icon_size)
        icon_image.unlockFocus()
        self.icon_view.setImage_(icon_image)
        self.icon_view.setTarget_(self)
        self.icon_view.setAction_(objc.selector(self._iconClicked_, signature=b'v@:'))
        self.custom_view.addSubview_(self.icon_view)

        # 시간 레이블
        self.time_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(icon_size + 4, 2,
                       bar_width - icon_size - 6,
                       bar_height - 4))
        self.time_label.setBezeled_(False)
        self.time_label.setDrawsBackground_(False)
        self.time_label.setEditable_(False)
        self.time_label.setSelectable_(False)
        self.time_label.setAlignment_(NSTextAlignmentCenter)

        font = NSFont.monospacedDigitSystemFontOfSize_weight_(12, NSFontWeightBold)
        self.time_label.setFont_(font)
        self.time_label.setStringValue_("00:00")
        self.time_label.setToolTip_("Mac Time Tracker — 대기 중")
        self.custom_view.addSubview_(self.time_label)

        self.statusItem.setView_(self.custom_view)

    def _draw_clock_icon(self, icon_size):
        """시계 아이콘 그리기"""
        s = icon_size
        NSColor.blackColor().set()
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(1, 1, s-2, s-2)).fill()
        NSColor.whiteColor().set()
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(2, 2, s-4, s-4)).fill()
        NSColor.blackColor().set()
        path = NSBezierPath.bezierPath()
        path.moveToPoint_(NSMakePoint(s/2, s/2))
        path.lineToPoint_(NSMakePoint(s/2, s/2+7))
        path.moveToPoint_(NSMakePoint(s/2, s/2))
        path.lineToPoint_(NSMakePoint(s/2+5, s/2))
        path.setLineWidth_(2)
        path.stroke()

    def _iconClicked_(self, sender):
        """아이콘 클릭 → 메뉴 표시"""
        if self.menu:
            self.statusItem.popUpStatusItemMenu_(self.menu)

    def setMenu_(self, menu):
        self.menu = menu

    @objc.python_method
    def _format_time(self, time_text):
        """HH:MM:SS → MM:SS (1시간 미만시)"""
        if time_text.startswith("00:"):
            return time_text[3:]
        return time_text

    @objc.python_method
    def update_time_display(self, time_text):
        """상태바 시간 텍스트 업데이트"""
        formatted = self._format_time(time_text)
        self.time_label.setStringValue_(formatted)

        # 툴팁
        parts = time_text.split(":")
        hours = int(parts[0])
        if hours > 0:
            self.time_label.setToolTip_(f"현재 앱 사용 시간: {hours}시간 {time_text[3:]}")
        else:
            self.time_label.setToolTip_(f"현재 앱 사용 시간: {formatted}")
