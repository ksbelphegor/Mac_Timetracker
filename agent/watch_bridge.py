#!/usr/bin/env python3
"""
Mac Time Tracker — macOS Watcher Bridge

aw-watcher-window의 stdout heartbeat를 FastAPI 서버로 전달합니다.

사용법:
  python3 watch_bridge.py                    # http://localhost:8000 으로 전송
  python3 watch_bridge.py --server http://192.168.0.5:8000   # 원격 서버

pip 필요: aw-watcher-window requests
"""
import sys
import os
import json
import time
import subprocess
import argparse
import signal

SERVER_URL = "http://localhost:8000"


def main():
    parser = argparse.ArgumentParser(description="Mac Time Tracker Bridge")
    parser.add_argument("--server", default=SERVER_URL, help="FastAPI 서버 주소")
    args = parser.parse_args()

    server_url = args.server.rstrip("/")
    print(f"🕐 Mac Time Tracker 시작")
    print(f"   서버: {server_url}")
    print(f"   watcher: aw-watcher-window")

    # aw-watcher-window 실행
    try:
        proc = subprocess.Popen(
            ["aw-watcher-window"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1
        )
    except FileNotFoundError:
        print("❌ aw-watcher-window를 찾을 수 없습니다.")
        print("   pip3 install aw-watcher-window")
        sys.exit(1)

    print(f"✅ watcher 실행됨 (PID: {proc.pid})")
    print("   상태바 아이콘을 확인하세요 (시계 모양)")
    print("   Ctrl+C로 종료\n")

    def cleanup(sig, frame):
        print("\n⏹ 종료 중...")
        proc.terminate()
        proc.wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    import requests

    # stdout에서 heartbeat 읽어서 전송
    for line in iter(proc.stdout.readline, ''):
        line = line.strip()
        if not line:
            continue

        try:
            heartbeat = json.loads(line)
            # ActivityWatch heartbeat 포맷:
            # {"timestamp": 1234.56, "duration": 5.0, "data": {"app": "Safari", "title": "..."}}

            # 서버로 전송
            resp = requests.post(
                f"{server_url}/api/heartbeat",
                json={
                    "timestamp": heartbeat.get("timestamp", time.time()),
                    "duration": heartbeat.get("duration", 1.0),
                    "data": heartbeat.get("data", {})
                },
                timeout=2
            )
            if resp.status_code != 200:
                print(f"⚠️ 전송 실패: {resp.status_code}", file=sys.stderr)
        except json.JSONDecodeError:
            continue
        except requests.ConnectionError:
            print(f"⚠️ 서버 연결 실패: {server_url}")
            time.sleep(5)
        except Exception as e:
            print(f"⚠️ 오류: {e}", file=sys.stderr)
            time.sleep(1)


if __name__ == "__main__":
    main()
