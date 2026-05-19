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

# tray_app.py 프로세스 찾아서 종료
PIDS=$(ps aux | grep "tray_app.py" | grep -v grep | awk '{print $2}')
if [ -n "$PIDS" ]; then
    kill $PIDS 2>/dev/null
    echo "✅ 메뉴바 앱 종료됨"
else
    echo "ℹ️  실행 중인 메뉴바 앱이 없음"
fi

# ── 2. Docker 서버 종료 ──

echo ""
echo "🐳 2. Docker 서버 종료 중..."

docker compose down 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Docker 서버 종료됨"
else
    echo "ℹ️  Docker 서버 종료 완료 (또는 실행 중이지 않음)"
fi

echo ""
echo "=========================================="
echo "  ✅ 모든 트래커가 종료되었습니다"
echo "=========================================="

read -p "엔터를 누르면 종료합니다..."
