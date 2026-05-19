#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mac Time Tracker — 순수 macOS AppKit 상태바 앱

PyQt5 없이 pyobjc(Apple 프레임워크)만으로 동작하는 경량 macOS 상태바 앱입니다.
상태바에서 현재 앱 사용 시간을 확인하고, 메뉴에서 통계를 볼 수 있습니다.
"""
import os
import sys
import time
import json
import logging
import threading

import objc
from Foundation import (
    NSObject,
    NSTimer, NSRunLoop, NSDefaultRunLoopMode,
    NSDate, NSBundle
)
from AppKit import (
    NSApplication, NSStatusBar, NSVariableStatusItemLength,
    NSImage, NSMenu, NSMenuItem, NSWorkspace,
    NSApplicationActivationPolicyRegular, NSApp
)

# 현재 디렉토리를 Python 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from src.core.config import APP_NAME, BUNDLE_ID, APP_VERSION, setup_logging, CONFIG
from src.core.config import APP_USAGE_FILE, TIMER_DATA_FILE
from src.core.data_manager import DataManager
from src.core.app_tracker import AppTracker
from src.core.timer_manager import TimerManager
from src.core.status_bar import StatusBarController
from src.core.main_window import MainWindow

logger = logging.getLogger(APP_NAME)

# ──────────────────────────────────────────────
# 메인 앱 델리게이트 — NSApplication 라이프사이클 관리
# ──────────────────────────────────────────────

class AppDelegate(NSObject):
    """NSApplication 델리게이트. 앱 초기화 및 라이프사이클 담당."""

    def init(self):
        self = objc.super(AppDelegate, self).init()
        if self is None:
            return None

        # 데이터 레이어 초기화
        self.data_manager = DataManager.get_instance()
        self.data_manager.ensure_data_directory()

        # 상태바 컨트롤러 (AppKit 네이티브, PyQt5 없음)
        self.status_bar = StatusBarController.alloc().init()

        # 코어 모듈
        self.app_tracker = AppTracker(self.data_manager)
        self.timer_manager = TimerManager(self.data_manager)

        # 메인 윈도우
        self.main_window = MainWindow.alloc().init()

        # 타이머 참조를 저장 (GC 방지)
        self.update_timer = None
        self.save_timer = None

        # 타이머가 깨어났는지 추적
        self._is_active_window = False

        return self

    def applicationDidFinishLaunching_(self, notification):
        """앱이 실행된 후 호출됩니다."""
        logger.info(f"{APP_NAME} 시작됨")

        # 메뉴 생성 및 연결
        self._setup_menu()

        # 1초 주기 업데이트 타이머
        self.update_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, b'tick:', None, True
        )
        NSRunLoop.currentRunLoop().addTimer_forMode_(
            self.update_timer, NSDefaultRunLoopMode
        )

        # 30초 주기 자동 저장 타이머
        self.save_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            30.0, self, b'autoSave:', None, True
        )
        NSRunLoop.currentRunLoop().addTimer_forMode_(
            self.save_timer, NSDefaultRunLoopMode
        )

        # 초기 앱 목록 업데이트
        self._update_app_list()

    def _setup_menu(self):
        """상태바 메뉴를 구성합니다."""
        menu = NSMenu.alloc().init()

        # 현재 추적 중인 앱 정보 (동적 업데이트용 플레이스홀더)
        self._current_app_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "앱을 선택하세요", None, ""
        )
        menu.addItem_(self._current_app_item)

        # 구분선
        menu.addItem_(NSMenuItem.separatorItem())

        # 오늘 통계
        self._today_stat_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "오늘: 불러오는 중...", None, ""
        )
        menu.addItem_(self._today_stat_item)

        # 구분선
        menu.addItem_(NSMenuItem.separatorItem())

        # 메인 창 열기
        show_window_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "📊 메인 창 열기", objc.selector(self._show_main_window_, signature=b'v@:'), "o"
        )
        menu.addItem_(show_window_item)

        # 구분선
        menu.addItem_(NSMenuItem.separatorItem())

        # 종료 버튼
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "종료", objc.selector(self._quit_, signature=b'v@:'), "q"
        )
        menu.addItem_(quit_item)

        self.status_bar.setMenu_(menu)

    def _update_app_list(self):
        """현재 실행 중인 앱 목록을 업데이트합니다."""
        try:
            self.app_tracker.update_app_list()
        except Exception as e:
            logger.error(f"앱 목록 업데이트 실패: {e}")

    def tick_(self, timer):
        """1초마다 호출 — 현재 앱 감지 및 시간 업데이트"""
        try:
            # 현재 활성 앱 조회 (NSWorkspace)
            workspace = NSWorkspace.sharedWorkspace()
            active_app = workspace.activeApplication()

            if not active_app:
                return

            app_name = active_app.get('NSApplicationName', 'Unknown')

            # 시스템 앱 제외
            skip_apps = {'Finder', 'SystemUIServer', 'loginwindow', 'Dock',
                         'Control Center', 'Notification Center'}
            app_is_trackable = app_name not in skip_apps

            # TimerManager에 현재 앱 알림
            if app_is_trackable:
                is_new_app = (self.timer_manager.timer_data.get('app_name') != app_name)
                if is_new_app:
                    self.timer_manager.select_app(app_name, is_active=True)
                else:
                    self.timer_manager.update_timer_status(
                        is_active_app=True
                    )

                # AppTracker에 통계 업데이트
                self.app_tracker.update_usage_stats(self.timer_manager.timer_data)

                # 상태바 시간 업데이트
                time_text = self.timer_manager.get_formatted_time()
                self.status_bar.update_time_display(time_text)
            else:
                # 시스템 앱이면 타이머 정지
                if self.timer_manager.timer_data.get('app_name'):
                    self.timer_manager.update_timer_status(is_active_app=False)
                    time_text = self.timer_manager.get_formatted_time()
                    self.status_bar.update_time_display(time_text)

            # 메뉴의 현재 앱 항목 업데이트
            tracked_app = self.timer_manager.timer_data.get('app_name')
            if tracked_app:
                time_text = self.timer_manager.get_formatted_time()
                self._current_app_item.setTitle_(f"🟢 {tracked_app} — {time_text}")
            else:
                self._current_app_item.setTitle_("⏸ 추적 중인 앱 없음")

            # 메뉴 통계 업데이트 (5초마다)
            if int(time.time()) % 5 == 0:
                self._update_menu_stats()

            # 메인 창 데이터 갱신 (열려 있을 때만)
            if self.main_window and self.main_window.window and \
               self.main_window.window.isVisible():
                self.main_window.refresh()

        except Exception as e:
            logger.error(f"tick 오류: {e}")
            import traceback
            traceback.print_exc()

    def _update_menu_stats(self):
        """메뉴에 오늘 통계를 업데이트합니다."""
        try:
            from datetime import datetime
            today = datetime.now().strftime('%Y-%m-%d')
            usage = self.app_tracker.app_usage.get('dates', {}).get(today, {})

            total_seconds = sum(
                data.get('total_time', 0) for data in usage.values()
                if isinstance(data, dict)
            )
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)

            # 앱별 통계 (상위 3개)
            sorted_apps = sorted(
                [(name, d.get('total_time', 0)) for name, d in usage.items()
                 if isinstance(d, dict) and name != APP_NAME],
                key=lambda x: x[1], reverse=True
            )[:3]

            stats_lines = [f"오늘 총 {hours}h {minutes}m"]
            for app_name, secs in sorted_apps:
                h = int(secs // 3600)
                m = int((secs % 3600) // 60)
                stats_lines.append(f"  {app_name}: {h}h {m}m")

            self._today_stat_item.setTitle_("  ".join(stats_lines))

        except Exception as e:
            logger.error(f"메뉴 통계 업데이트 실패: {e}")

    def autoSave_(self, timer):
        """30초마다 자동 저장"""
        try:
            # 타이머 데이터 저장
            self.app_tracker.update_usage_stats(self.timer_manager.timer_data)
            self.app_tracker.save_app_usage()
            self.timer_manager.save_timer_data()
            logger.debug("자동 저장 완료")
        except Exception as e:
            logger.error(f"자동 저장 실패: {e}")

    def applicationWillTerminate_(self, notification):
        """앱 종료 전 마지막 저장"""
        logger.info(f"{APP_NAME} 종료 중...")
        try:
            self.app_tracker.update_usage_stats(self.timer_manager.timer_data)
            self.app_tracker.save_app_usage()
            self.timer_manager.save_timer_data()
            logger.info("데이터 저장 완료")
        except Exception as e:
            logger.error(f"종료 저장 실패: {e}")

    def _quit_(self, sender):
        """종료 액션"""
        NSApp.terminate_(self)

    def _show_main_window_(self, sender):
        """메인 창 표시"""
        self.main_window.show()


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────

def main():
    """앱 진입점"""
    setup_logging()
    logger.info(f"{APP_NAME} v{APP_VERSION} 시작됨")

    # Dock 아이콘 숨기기 (순수 상태바 앱)
    NSBundle.mainBundle().infoDictionary()['LSUIElement'] = True

    # NSApplication 생성 및 실행
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)

    logger.info("앱 실행")
    app.run()


if __name__ == '__main__':
    main()
