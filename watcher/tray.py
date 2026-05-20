#!/usr/bin/env python3
"""
Mac Time Tracker — macOS 메뉴바 앱

rumps 기반 메뉴바 트레이 아이콘.
ActiveApp 알림 구독 → heartbeat 전송 → 창 제목 수집

pip 필요: pip3 install rumps pyobjc-framework-Cocoa requests
"""
import os
import time
import threading
import logging
import webbrowser

import rumps
import objc
import requests
from AppKit import NSWorkspace, NSWorkspaceDidActivateApplicationNotification
from Foundation import NSNotificationCenter, NSObject

SERVER_URL = "http://localhost:8000"
HEARTBEAT_INTERVAL = 5
STATS_REFRESH_INTERVAL = 60

logger = logging.getLogger("mtt-tray")


class WatcherDelegate(NSObject):
    """NSWorkspace 알림을 받아서 트레이 앱으로 전달"""

    def initWithTray_(self, tray_app):
        self = objc.super(WatcherDelegate, self).init()
        if self:
            self.tray_app = tray_app
        return self

    def activeAppDidChange_(self, notification):
        """앱 전환 알림 → 트레이에 전달"""
        workspace = notification.object()
        active_app = workspace.activeApplication()
        if not active_app:
            return
        app_name = active_app.get("NSApplicationName", "Unknown")
        pid = active_app.get("NSApplicationProcessIdentifier", 0)
        self.tray_app.on_app_changed(app_name, pid)


class TimeTrackerTray(rumps.App):
    """메뉴바 트레이 앱"""

    def __init__(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        super().__init__("MacTT", icon=icon_path if os.path.exists(icon_path) else None)
        self.title = ""

        self.server_url = SERVER_URL
        self.current_app = "—"
        self.current_pid = 0
        self.session_start = time.time()
        self.paused = False
        self.server_ok = False
        self.total_today_seconds = 0

        # 창 제목 캐시
        self._window_title = ""
        self._window_title_time = 0
        self._window_title_cache_ttl = 2

        # 메뉴 구성
        self.app_item = rumps.MenuItem(f"📌 현재 앱: {self.current_app}")
        self.app_item.set_callback(None)

        self.time_item = rumps.MenuItem("⏱ 오늘: 계산중...")
        self.time_item.set_callback(None)

        self.status_item = rumps.MenuItem("● 실행중")
        self.status_item.set_callback(None)

        self.pause_item = rumps.MenuItem("⏸ 일시정지", callback=self.toggle_pause)
        self.dashboard_item = rumps.MenuItem("📊 대시보드 열기", callback=self.open_dashboard)
        self.quit_item = rumps.MenuItem("✕ 종료", callback=self.quit_app, key="q")

        self.menu = [
            self.app_item,
            self.time_item,
            self.status_item,
            None,
            self.pause_item,
            self.dashboard_item,
            None,
            self.quit_item,
        ]

        # NSWorkspace 알림 구독
        self.nc = NSNotificationCenter.defaultCenter()
        self.delegate = WatcherDelegate.alloc().initWithTray_(self)
        self.nc.addObserver_selector_name_object_(
            self.delegate,
            objc.selector(self.delegate.activeAppDidChange_, signature=b"v@:@"),
            NSWorkspaceDidActivateApplicationNotification,
            None,
        )

        # 현재 앱 초기값
        try:
            ws = NSWorkspace.sharedWorkspace()
            active = ws.activeApplication()
            if active:
                self.current_app = active.get("NSApplicationName", "—")
                self.current_pid = active.get("NSApplicationProcessIdentifier", 0)
                self.app_item.title = f"📌 현재 앱: {self.current_app}"
        except Exception:
            pass

        self.check_server()

        self.heartbeat_timer = rumps.Timer(self.on_heartbeat, HEARTBEAT_INTERVAL)
        self.heartbeat_timer.start()

        self.stats_timer = rumps.Timer(self.refresh_stats, STATS_REFRESH_INTERVAL)
        self.stats_timer.start()

        threading.Timer(3.0, self.refresh_stats, args=[None]).start()

    # ── 알림 핸들러 ──

    def on_app_changed(self, app_name, pid):
        """앱 전환 시 호출"""
        if self.paused:
            return
        now = time.time()
        duration = now - self.session_start
        self._send_heartbeat(app_name, now, duration)
        self.current_app = app_name
        self.current_pid = pid
        self.session_start = now
        self.app_item.title = f"📌 현재 앱: {app_name}"
        self._update_tooltip()

    def on_heartbeat(self, _sender=None):
        """5초 주기 heartbeat"""
        if self.paused:
            return
        try:
            ws = NSWorkspace.sharedWorkspace()
            active = ws.activeApplication()
            if active:
                app_name = active.get("NSApplicationName", "Unknown")
                now = time.time()
                duration = now - self.session_start
                self._send_heartbeat(app_name, now, duration)
                self.session_start = now
                if app_name != self.current_app:
                    self.current_app = app_name
                    self.app_item.title = f"📌 현재 앱: {app_name}"
                    self._update_tooltip()
        except Exception as e:
            logger.debug(f"heartbeat 오류: {e}")

    # ── 창 제목 ──

    def _get_window_title(self):
        """현재 활성 창/탭 제목 가져오기 (브라우저 대응)"""
        now = time.time()
        if now - self._window_title_time < self._window_title_cache_ttl:
            return self._window_title

        app_name = self._get_frontmost_app()
        title = None
        if app_name in self.BROWSER_SCRIPTS:
            title = self._browser_tab_title(app_name)
        if not title:
            title = self._ax_window_title(app_name)

        self._window_title = title or ""
        self._window_title_time = now
        return self._window_title

    BROWSER_SCRIPTS = {
        "Brave Browser": 'tell application "Brave Browser" to get title of active tab of window 1',
        "Google Chrome": 'tell application "Google Chrome" to get title of active tab of window 1',
        "Safari": 'tell application "Safari" to get name of front document',
        "Firefox": 'tell application "System Events" to tell process "firefox" to get title of window 1',
        "Microsoft Edge": 'tell application "Microsoft Edge" to get title of active tab of window 1',
        "Arc": 'tell application "Arc" to get title of active tab of window 1',
        "Opera": 'tell application "Opera" to get title of active tab of window 1',
        "Opera GX": 'tell application "Opera GX" to get title of active tab of window 1',
        "Orion": 'tell application "Orion" to get title of active tab of window 1',
    }

    def _get_frontmost_app(self):
        """현재 포그라운드 앱 이름 반환"""
        try:
            import subprocess
            result = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to get name of first process whose frontmost is true'],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return ""

    def _browser_tab_title(self, app_name):
        """브라우저 AppleScript로 활성 탭 제목 가져오기"""
        script = self.BROWSER_SCRIPTS.get(app_name)
        if not script:
            return ""
        try:
            import subprocess
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return ""

    def _ax_window_title(self, app_name):
        """Accessibility API로 일반 앱의 window 1 제목 가져오기"""
        if not app_name:
            return ""
        try:
            import subprocess
            result = subprocess.run(
                ["osascript", "-e",
                 f'tell application "System Events" to tell process "{app_name}" to get title of window 1'],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return ""

    # ── 서버 통신 ──

    def _send_heartbeat(self, app_name, timestamp, duration):
        """서버로 heartbeat 전송 (앱명 + 창 제목)"""
        try:
            window_title = self._get_window_title()
            resp = requests.post(
                f"{self.server_url}/api/heartbeat",
                json={
                    "timestamp": timestamp,
                    "duration": max(duration, 1.0),
                    "data": {"app": app_name, "title": window_title or app_name},
                },
                timeout=2,
            )
            if resp.status_code == 200:
                self.server_ok = True
                self.status_item.title = "● 실행중"
            else:
                logger.warning(f"전송 실패: {resp.status_code}")
        except requests.ConnectionError:
            self.server_ok = False
            self.status_item.title = "○ 서버 연결 끊김"
        except Exception as e:
            logger.debug(f"전송 오류: {e}")

    def check_server(self):
        """서버 상태 확인"""
        try:
            resp = requests.get(f"{self.server_url}/api/today", timeout=3)
            if resp.status_code == 200:
                self.server_ok = True
                self.status_item.title = "● 실행중"
                data = resp.json()
                self.total_today_seconds = data.get("total_seconds", 0)
                self.time_item.title = f"⏱ 오늘: {self._format_time(self.total_today_seconds)}"
        except Exception:
            self.server_ok = False
            self.status_item.title = "○ 서버 연결 끊김"
            self.time_item.title = "⏱ 오늘: — (서버 꺼짐)"

    def refresh_stats(self, _sender=None):
        """서버에서 오늘 통계 갱신"""
        self.check_server()

    # ── 메뉴 액션 ──

    def toggle_pause(self, _sender):
        """일시정지 토글"""
        self.paused = not self.paused
        if self.paused:
            self.pause_item.title = "▶ 재개"
            self.status_item.title = "⏸ 일시정지"
            self.app_item.title = f"📌 현재 앱: {self.current_app} (일시정지)"
        else:
            self.pause_item.title = "⏸ 일시정지"
            self.status_item.title = "● 실행중"
            self.session_start = time.time()
            self.app_item.title = f"📌 현재 앱: {self.current_app}"
            self.on_heartbeat()

    def open_dashboard(self, _sender):
        """브라우저로 대시보드 열기"""
        webbrowser.open(f"{self.server_url}/")
        rumps.notification(
            "Mac Time Tracker",
            "대시보드 열기",
            f"{self.server_url}",
        )

    def quit_app(self, _sender):
        """앱 종료 (API 서버도 함께 종료 + observer 정리)"""
        # NSNotificationCenter observer 해제 (메모리 누수 방지)
        try:
            self.nc.removeObserver_(self.delegate)
        except Exception:
            pass

        # API 서버 종료
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pid_path = os.path.join(script_dir, "logs", "api.pid")
        try:
            with open(pid_path) as f:
                pid = int(f.read().strip())
                os.kill(pid, 15)
        except Exception:
            pass

        rumps.notification(
            "Mac Time Tracker",
            "트래커 종료",
            "트래킹 및 API 서버가 종료되었습니다.",
        )
        rumps.quit_application()

    # ── 유틸 ──

    @staticmethod
    def _format_time(seconds):
        """초 → hh:mm:ss 변환"""
        h, remainder = divmod(int(seconds), 3600)
        m, s = divmod(remainder, 60)
        if h > 0:
            return f"{h}h {m:02d}m"
        return f"{m}m {s:02d}s"

    def _update_tooltip(self):
        """메뉴바 — 텍스트 없이 아이콘만"""
        self.title = ""


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger.info("🕐 Mac Time Tracker 메뉴바 앱 시작")
    logger.info(f"   서버: {SERVER_URL}")
    logger.info("   메뉴바에서 ⏱ 아이콘을 찾아보세요")

    app = TimeTrackerTray()
    app.run()


if __name__ == "__main__":
    main()
