#!/bin/bash
# =============================================================================
# Mac Time Tracker — 실행 스크립트 (원클릭)
# 더블클릭: API 서버 + 메뉴바 앱 한번에 실행
# =============================================================================

echo "=========================================="
echo "  🕐 Mac Time Tracker 실행"
echo "=========================================="

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

mkdir -p logs

# ── 1. API 서버 실행 ──

echo ""
echo "🚀 1. API 서버 시작 중..."

# 기존 API 서버가 있으면 종료
if [ -f logs/api.pid ]; then
    kill $(cat logs/api.pid) 2>/dev/null
    sleep 1
fi

nohup python3 dashboard/api.py > logs/api.log 2>&1 &
API_PID=$!
echo $API_PID > logs/api.pid

# 서버 준비될 때까지 대기 (최대 10초)
for i in {1..10}; do
    curl -s -o /dev/null http://localhost:8000/ 2>/dev/null && break
    sleep 1
done

if curl -s -o /dev/null http://localhost:8000/ 2>/dev/null; then
    echo "✅ API 서버 시작 완료 (http://localhost:8000)"
else
    echo "⚠️  API 서버 시작 실패. 로그 확인: logs/api.log"
fi

# ── 2. 메뉴바 앱 실행 ──

echo ""
echo "⏱ 2. 메뉴바 트레이 앱 실행 중..."

# 기존 트레이 앱이 있으면 종료
if [ -f logs/tray.pid ]; then
    kill $(cat logs/tray.pid) 2>/dev/null
    sleep 1
fi

nohup python3 watcher/tray.py > logs/tray.log 2>&1 &
TRAY_PID=$!
echo $TRAY_PID > logs/tray.pid

sleep 2
if kill -0 $TRAY_PID 2>/dev/null; then
    echo "✅ 메뉴바 앱 실행됨 (PID: $TRAY_PID)"
else
    echo "⚠️  메뉴바 앱 실행 실패. 로그 확인: logs/tray.log"
fi

# ── 3. 대시보드 열기 ──

echo ""
echo "📊 3. 대시보드 열기..."
open http://localhost:8000
echo "✅ 브라우저에서 대시보드 열림"

echo ""
echo "=========================================="
echo "  ✅ 실행 완료!"
echo "=========================================="
echo ""
echo "  - 메뉴바 아이콘: ⏱ (시계 모양)"
echo "  - 대시보드: http://localhost:8000"
echo "  - 로그: logs/api.log / logs/tray.log"
echo ""
echo "  종료하려면 scripts/stop.command 실행"
echo ""

read -p "엔터를 누르면 이 창이 닫힙니다..."
