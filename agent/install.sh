#!/bin/bash
# Mac Time Tracker — macOS 에이전트 설치 스크립트
# pip 2줄로 끝!

set -e

echo "🕐 Mac Time Tracker — macOS 에이전트 설치"
echo "============================================"
echo ""

# 1. Python 확인
if ! command -v python3 &>/dev/null; then
    echo "❌ Python3이 필요합니다. https://www.python.org/downloads/"
    exit 1
fi
echo "✅ Python3: $(python3 --version)"

# 2. pip 설치
echo ""
echo "📦 1/2: aw-watcher-window 설치 중..."
pip3 install --user aw-watcher-window 2>&1 | tail -1

echo ""
echo "📦 2/2: requests 설치 중..."
pip3 install --user requests 2>&1 | tail -1

# 3. 서비스 등록 (launchd)
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$LAUNCH_AGENTS_DIR/com.mactimetracker.watcher.plist"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BRIDGE_PATH="$SCRIPT_DIR/watch_bridge.py"

mkdir -p "$LAUNCH_AGENTS_DIR"

# launchd plist 생성 (선택, ~/Library/LaunchAgents/에 등록)
cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.mactimetracker.watcher</string>
    <key>ProgramArguments</key>
    <array>
        <string>$(which python3)</string>
        <string>"$BRIDGE_PATH"</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$HOME/.mactimetracker/watcher.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.mactimetracker/watcher-error.log</string>
</dict>
</plist>
EOF

echo ""
echo "============================================"
echo "✅ 설치 완료!"
echo ""
echo "실행 방법:"
echo "  python3 $(dirname "$0")/watch_bridge.py"
echo ""
echo "또는 launchd 자동 실행 등록:"
echo "  launchctl load $PLIST_PATH"
echo ""
echo "Docker 서버 실행:"
echo "  docker compose up -d"
echo ""
echo "대시보드: http://localhost:8000"
