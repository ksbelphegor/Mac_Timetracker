#!/bin/bash
# Mac Time Tracker — 원클릭 실행
# Swift 단일 바이너리, 의존성 0

echo "=========================================="
echo "  🕐 Mac Time Tracker"
echo "=========================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP_BUNDLE="$SCRIPT_DIR/Mac Time Tracker.app"
APP_BINARY="$APP_BUNDLE/Contents/MacOS/MacTT"

# ── 빌드 (소스 변경 시) ──

NEED_BUILD=false
if [ ! -f "$APP_BINARY" ]; then
    NEED_BUILD=true
elif [ "watcher/app.swift" -nt "$APP_BINARY" ] || \
     [ "watcher/server.swift" -nt "$APP_BINARY" ] || \
     [ "watcher/database.swift" -nt "$APP_BINARY" ] || \
     [ "watcher/main.swift" -nt "$APP_BINARY" ] || \
     [ "watcher/Info.plist" -nt "$APP_BINARY" ] || \
     [ "dashboard/static/index.html" -nt "$APP_BINARY" ]; then
    NEED_BUILD=true
fi

if [ "$NEED_BUILD" = true ]; then
    echo "🔨 빌드 중..."
    bash scripts/build-swift.sh 2>&1 | tail -3
    echo ""
fi

# ── 실행 ──

echo "🚀 Mac Time Tracker 실행 중..."
open "$APP_BUNDLE"
sleep 2

echo "✅ 실행 완료! (메뉴바 🕐 아이콘 확인)"
echo "   대시보드: http://localhost:8000"
echo ""

read -p "엔터를 누르면 창이 닫힙니다..."
