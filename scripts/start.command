#!/bin/bash
# Mac Time Tracker — 올인원 실행 (scripts/start.command → start.command에서 호출)

echo "=========================================="
echo "  🕐 Mac Time Tracker"
echo "=========================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

APP_BUNDLE="$SCRIPT_DIR/Mac Time Tracker.app"
APP_BINARY="$APP_BUNDLE/Contents/MacOS/MacTT"
mkdir -p logs

# ── 0. Swift 빌드 (없거나 오래됐으면) ──

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
    echo "🔨 Swift 앱 빌드 중..."
    bash scripts/build-swift.sh 2>&1 | tail -3
    if [ ! -f "$APP_BINARY" ]; then
        echo "❌ 빌드 실패"
        read -p "엔터를 누르면 창이 닫힙니다..."
        exit 1
    fi
    echo "✅ 빌드 완료"
fi

# ── 1. Swift 앱 실행 (HTTP 서버 + 메뉴바 통합) ──

echo ""
echo "🚀 1. Mac Time Tracker 실행..."
open "$APP_BUNDLE"
echo "   (메뉴바 🕐 아이콘 확인)"

# ── 2. 서버 준비 대기 후 대시보드 열기 ──

echo ""
echo "📊 2. 대시보드 열기..."
for i in {1..10}; do
    curl -s -o /dev/null http://localhost:8000/ 2>/dev/null && break
    sleep 1
done
open http://localhost:8000

echo ""
echo "=========================================="
echo "  ✅ 완료!"
echo "=========================================="
echo ""
echo "  - 메뉴바: 🕐 아이콘"
echo "  - 대시보드: http://localhost:8000"
echo "  - 종료: 메뉴바 🕐 → ✕ 또는 stop.command"
echo "  - Dock 고정: Mac Time Tracker.app 을 Dock에 드래그"
echo ""

read -p "엔터를 누르면 창이 닫힙니다..."
