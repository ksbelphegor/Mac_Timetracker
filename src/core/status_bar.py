import objc
import time
from Foundation import NSObject, NSMakeRect, NSMakePoint, NSMakeSize
from AppKit import (NSStatusBar, NSVariableStatusItemLength, NSImage, NSMenuItem, NSMenu,
                   NSView, NSButton, NSButtonTypeMomentaryLight, NSTextField, 
                   NSTextAlignmentCenter, NSColor, NSBezierPath)
from PyQt5.QtCore import QTimer

from core.config import APP_NAME, BUNDLE_ID, STATUS_BAR_WIDTH, STATUS_BAR_HEIGHT, ICON_SIZE

class StatusBarController(NSObject):
    def init(self):
        self = objc.super(StatusBarController, self).init()
        if self is None:
            return None
        self.menu = None  # 메뉴 초기화
        self._setup_status_item()
        self._setup_custom_view()
        return self

    def _setup_status_item(self):
        self.statusItem = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength)
        self.statusItem.setHighlightMode_(True)

    def _setup_custom_view(self):
        self.custom_view = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, STATUS_BAR_WIDTH, STATUS_BAR_HEIGHT))
        
        # 아이콘 설정
        self.icon_view = NSButton.alloc().initWithFrame_(
            NSMakeRect(0, 0, ICON_SIZE, ICON_SIZE))
        self.icon_view.setButtonType_(NSButtonTypeMomentaryLight)
        self.icon_view.setBordered_(False)
        icon_image = NSImage.alloc().initWithSize_(
            NSMakeSize(ICON_SIZE, ICON_SIZE))
        icon_image.lockFocus()
        self.draw_clock_icon()
        icon_image.unlockFocus()
        self.icon_view.setImage_(icon_image)
        self.icon_view.setTarget_(self)
        self.icon_view.setAction_(objc.selector(self.iconClicked_, signature=b'v@:'))
        self.custom_view.addSubview_(self.icon_view)
        
        # 시간 레이블 설정
        self.time_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(24, 2, STATUS_BAR_WIDTH - ICON_SIZE - 2, STATUS_BAR_HEIGHT - 4))
        self.time_label.setBezeled_(False)
        self.time_label.setDrawsBackground_(False)
        self.time_label.setEditable_(False)
        self.time_label.setSelectable_(False)
        self.time_label.setAlignment_(NSTextAlignmentCenter)
        self.time_label.setStringValue_("00:00:00")
        self.custom_view.addSubview_(self.time_label)
        
        self.statusItem.setView_(self.custom_view)

    def draw_clock_icon(self):
        """시계 아이콘을 그립니다."""
        width, height = ICON_SIZE, ICON_SIZE
        NSColor.blackColor().set()
        path = NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(1, 1, width-2, height-2))
        path.fill()
        NSColor.whiteColor().set()
        path = NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(2, 2, width-4, height-4))
        path.fill()
        NSColor.blackColor().set()
        path = NSBezierPath.bezierPath()
        path.moveToPoint_(NSMakePoint(width/2, height/2))
        path.lineToPoint_(NSMakePoint(width/2, height/2+7))
        path.moveToPoint_(NSMakePoint(width/2, height/2))
        path.lineToPoint_(NSMakePoint(width/2+5, height/2))
        path.setLineWidth_(2)
        path.stroke()

    def iconClicked_(self, sender):
        """아이콘 클릭 이벤트를 처리합니다."""
        if self.menu:
            self.statusItem.popUpStatusItemMenu_(self.menu)

    def setMenu_(self, menu):
        """상태바 메뉴를 설정합니다."""
        self.menu = menu

    def update_time_display(self, time_text):
        """상태바의 시간 표시를 업데이트합니다."""
        self.time_label.setStringValue_(time_text)