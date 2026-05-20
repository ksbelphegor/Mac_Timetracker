#!/bin/bash
# =============================================================================
# Mac Time Tracker — 종료 스크립트
# =============================================================================

echo "=========================================="
echo "  Mac Time Tracker 종료"
echo "=========================================="

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

# ── 1. 메뉴바 앱 종료 ──

echo ""
echo "⏱ 1. 메뉴바 앱 종료 중..."

if [ -f logs/tray.pid ]; then
    kill $(cat logs/tray.pid) 2>/dev/null && echo "✅ 메뉴바 앱 종료됨" || echo "ℹ️  이미 종료됨"
    rm -f logs/tray.pid
else
    # PID 파일 없으면 ps로 찾기
    PIDS=$(ps aux | grep "watcher/tray.py" | grep -v grep | awk '{print $2}')
    if [ -n "$PIDS" ]; then
        kill $PIDS 2>/dev/null
        echo "✅ 메뉴바 앱 종료됨"
    else
        echo "ℹ️  실행 중인 메뉴바 앱이 없음"
    fi
fi

# ── 2. API 서버 종료 ──

echo ""
echo "🚀 2. API 서버 종료 중..."

if [ -f logs/api.pid ]; then
    kill $(cat logs/api.pid) 2>/dev/null && echo "✅ API 서버 종료됨" || echo "ℹ️  이미 종료됨"
    rm -f logs/api.pid
else
    # PID 파일 없으면 ps로 찾기
    PIDS=$(ps aux | grep "api.py" | grep -v grep | awk '{print $2}')
    if [ -n "$PIDS" ]; then
        kill $PIDS 2>/dev/null
        echo "✅ API 서버 종료됨"
    else
        echo "ℹ️  실행 중인 API 서버가 없음"
    fi
fi

echo ""
echo "=========================================="
echo "  ✅ 모든 트래커가 종료되었습니다"
echo "=========================================="

read -p "엔터를 누르면 종료합니다..."
