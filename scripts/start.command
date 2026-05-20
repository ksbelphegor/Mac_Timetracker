#!/bin/bash
# =============================================================================
# Mac Time Tracker — 올인원 실행 스크립트
# 더블클릭 한 번으로 설치 + 실행 + 대시보드 오픈까지 전부 처리
# =============================================================================

echo "=========================================="
echo "  🕐 Mac Time Tracker"
echo "=========================================="

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR" || { echo "❌ 경로 이동 실패"; exit 1; }

mkdir -p logs

# ── 0. 패키지 확인 및 자동 설치 ──

NEEDED=("rumps" "requests" "fastapi" "uvicorn")
MISSING=()

for pkg in "${NEEDED[@]}"; do
    python3 -c "import $pkg" 2>/dev/null || MISSING+=("$pkg")
done

# pyobjc-framework-Cocoa → import objc로 체크 (하이픈 있는 패키지명)
python3 -c "import objc" 2>/dev/null || MISSING+=("pyobjc-framework-Cocoa")

if [ ${#MISSING[@]} -gt 0 ]; then
    echo ""
    echo "📦 필요한 패키지 설치 중: ${MISSING[*]}"
    pip3 install --user "${MISSING[@]}" 2>&1 | tail -1
    if [ $? -ne 0 ]; then
        echo "❌ 패키지 설치 실패. pip3 install --user rumps pyobjc-framework-Cocoa requests fastapi uvicorn[standard]"
        read -p "엔터를 누르면 종료합니다..."
        exit 1
    fi
    echo "✅ 패키지 설치 완료"
fi

# ── 1. API 서버 실행 ──

echo ""
echo "🚀 1. API 서버 시작 중..."

# 기존 API 서버 종료
if [ -f logs/api.pid ]; then
    kill "$(cat logs/api.pid)" 2>/dev/null
    sleep 1
fi

nohup python3 dashboard/api.py > logs/api.log 2>&1 &
API_PID=$!
echo $API_PID > logs/api.pid

# 서버 준비 대기 (최대 10초)
echo "   대기 중..."
for i in {1..10}; do
    curl -s -o /dev/null http://localhost:8000/ 2>/dev/null && break
    sleep 1
done

if curl -s -o /dev/null http://localhost:8000/ 2>/dev/null; then
    echo "✅ API 서버 시작 완료 (http://localhost:8000)"
else
    echo "⚠️  API 서버 시작 실패. 로그: logs/api.log"
fi

# ── 2. 메뉴바 앱 실행 ──

echo ""
echo "⏱ 2. 메뉴바 트레이 앱 실행 중..."

if [ -f logs/tray.pid ]; then
    kill "$(cat logs/tray.pid)" 2>/dev/null
    sleep 1
fi

nohup python3 watcher/tray.py > logs/tray.log 2>&1 &
TRAY_PID=$!
echo $TRAY_PID > logs/tray.pid

sleep 2
if kill -0 $TRAY_PID 2>/dev/null; then
    echo "✅ 메뉴바 앱 실행됨"
else
    echo "⚠️  메뉴바 앱 실행 실패. 로그: logs/tray.log"
fi

# ── 3. 대시보드 열기 ──

echo ""
echo "📊 3. 대시보드 열기..."
open http://localhost:8000

echo ""
echo "=========================================="
echo "  ✅ 완료! 메뉴바에서 ⏱ 아이콘 확인"
echo "=========================================="
echo ""
echo "  종료: 메뉴바 ⏱ → ✕ 종료"
echo "        또는 scripts/stop.command"
echo ""
echo "  개발: python3 dashboard/api.py --reload  (핫리로드)"
echo ""

read -p "엔터를 누르면 창이 닫힙니다..."
