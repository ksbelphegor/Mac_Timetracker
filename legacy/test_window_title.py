#!/usr/bin/env python3
"""단순 활성 창 제목 검사 스크립트."""
import subprocess
import time
from AppKit import NSWorkspace


def get_window_title(app_name: str) -> str:
    """AppleScript를 사용해 지정 앱의 전면 창 제목을 가져옵니다."""
    script = f'''
        tell application "System Events"
            tell process "{app_name}"
                try
                    set frontWindow to first window whose focused is true
                    set windowTitle to name of frontWindow
                    return windowTitle
                on error
                    try
                        set windowTitle to name of front window
                        return windowTitle
                    on error
                        return "{app_name}"
                    end try
                end try
            end tell
        end tell
    '''

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=1.0,
        )
        title = result.stdout.strip()
        if title:
            return title
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass
    return app_name


def main():
    print("=== 활성 창 제목 확인 ===")
    workspace = NSWorkspace.sharedWorkspace()

    for idx in range(10):
        print(f"\n[{idx + 1}] 체크")
        active_app = workspace.activeApplication()
        if not active_app:
            print("활성 앱을 찾을 수 없습니다.")
            time.sleep(1)
            continue

        app_name = active_app.get("NSApplicationName", "Unknown")
        app_pid = active_app.get("NSApplicationProcessIdentifier", "-")
        print(f"앱: {app_name} (PID: {app_pid})")

        window_title = get_window_title(app_name)
        print(f"창 제목: {window_title}")

        time.sleep(1)


if __name__ == "__main__":
    main()