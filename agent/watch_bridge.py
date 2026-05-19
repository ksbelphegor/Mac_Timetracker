#!/usr/bin/env python3
"""
Mac Time Tracker — macOS 기본 watcher (pyobjc only)

pip 필요: pyobjc-framework-Cocoa requests
설치: pip3 install pyobjc-framework-Cocoa requests
"""
import sys
import os
import json
import time
import signal
import argparse
import logging

# pyobjc
import objc
from AppKit import NSWorkspace, NSWorkspaceDidActivateApplicationNotification
from Foundation import NSNotificationCenter, NSObject, NSRunLoop, NSDate

SERVER_URL = "http://localhost:8000"


class WatcherDelegate(NSObject):
    """NSWorkspace 알림을 받아서 서버로 전송"""

    def initWithServer_(self, server_url):
        self = objc.super(WatcherDelegate, self).init()
        if self:
            self.server_url = server_url
            self.current_app = None
            self.last_send = 0
            self.session_start = time.time()
        return self

    def activeAppDidChange_(self, notification):
        """앱 전환 알림 처리"""
        workspace = notification.object()
        active_app = workspace.activeApplication()
        if not active_app:
            return

        app_name = active_app.get('NSApplicationName', 'Unknown')
        pid = active_app.get('NSApplicationProcessIdentifier', 0)
        now = time.time()

        # 이전 앱의 duration 계산
        duration = now - self.session_start

        # heartbeat 전송
        self._send_heartbeat(app_name, now, duration)

        self.current_app = app_name
        self.session_start = now

    def _send_heartbeat(self, app_name, timestamp, duration):
        """서버로 heartbeat 전송"""
        try:
            import requests
            resp = requests.post(
                f"{self.server_url}/api/heartbeat",
                json={
                    "timestamp": timestamp,
                    "duration": duration,
                    "data": {
                        "app": app_name,
                        "title": app_name
                    }
                },
                timeout=2
            )
            if resp.status_code == 200:
                logger.debug(f"→ {app_name} ({duration:.1f}s)")
            else:
                logger.warning(f"전송 실패: {resp.status_code}")
        except ImportError:
            logger.error("requests 모듈 필요: pip3 install requests")
            sys.exit(1)
        except Exception as e:
            logger.debug(f"전송 오류: {e}")


def main():
    parser = argparse.ArgumentParser(description="Mac Time Tracker Watcher")
    parser.add_argument("--server", default=SERVER_URL, help="서버 주소")
    parser.add_argument("--verbose", action="store_true", help="로그 출력")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    global logger
    logger = logging.getLogger("mtt-watcher")

    logger.info(f"🕐 Mac Time Tracker watcher 시작")
    logger.info(f"   서버: {args.server}")
    logger.info(f"   Ctrl+C로 종료")

    # AppKit 프레임워크 로드
    workspace = NSWorkspace.sharedWorkspace()

    # 델리게이트 설정
    delegate = WatcherDelegate.alloc().initWithServer_(args.server)

    # 알림 구독 (활성 앱 변경 시)
    NC = NSNotificationCenter.defaultCenter()
    NC.addObserver_selector_name_object_(
        delegate,
        objc.selector(delegate.activeAppDidChange_, signature=b'v@:@'),
        NSWorkspaceDidActivateApplicationNotification,
        None
    )

    # 첫 heartbeat 전송 (현재 앱)
    active = workspace.activeApplication()
    if active:
        delegate._send_heartbeat(
            active.get('NSApplicationName', 'Unknown'),
            time.time(), 1.0
        )

    logger.info("✅ 실행 중... (상태바 아이콘이 보이면 정상)")

    # 5초마다 heartbeat 유지 (앱 전환이 없어도)
    def periodic_heartbeat():
        while True:
            time.sleep(5)
            active = NSWorkspace.sharedWorkspace().activeApplication()
            if active:
                app_name = active.get('NSApplicationName', 'Unknown')
                now = time.time()
                duration = now - delegate.session_start
                delegate._send_heartbeat(app_name, now, duration)
                delegate.session_start = now

    import threading
    t = threading.Thread(target=periodic_heartbeat, daemon=True)
    t.start()

    # NSRunLoop 메인 루프
    try:
        NSRunLoop.currentRunLoop().run()
    except KeyboardInterrupt:
        logger.info("⏹ 종료")


if __name__ == "__main__":
    main()
