#!/bin/bash
# =============================================================================
# Mac Time Tracker — 실행 스크립트
# 더블클릭: Docker 서버 + 메뉴바 앱 한번에 실행
# =============================================================================

echo "=========================================="
echo "  🕐 Mac Time Tracker 실행"
echo "=========================================="

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

# ── 1. Docker 확인 ──

echo ""
echo "🐳 1. Docker 서버 확인 중..."

if ! command -v docker &> /dev/null; then
    echo "❌ Docker를 찾을 수 없습니다."
    echo "   https://www.docker.com/products/docker-desktop/"
    read -p "엔터를 누르면 종료합니다..."
    exit 1
fi

# Docker Desktop이 실행 중인지 확인
docker info &> /dev/null
if [ $? -ne 0 ]; then
    echo "⚡ Docker Desktop 실행 중입니다... 잠시만 기다려주세요."
    open -a Docker
    # Docker 준비될 때까지 대기 (최대 30초)
    for i in {1..30}; do
        sleep 1
        docker info &> /dev/null && break
    done
    if [ $? -ne 0 ]; then
        echo "❌ Docker Desktop이 시작되지 않았습니다."
        echo "   수동으로 Docker Desktop을 실행한 후 다시 시도하세요."
        read -p "엔터를 누르면 종료합니다..."
        exit 1
    fi
fi

# Docker 서버 시작
echo "✅ Docker Desktop 실행 중"
docker compose up -d 2>&1
if [ $? -ne 0 ]; then
    echo "❌ Docker 서버 시작 실패"
    read -p "엔터를 누르면 종료합니다..."
    exit 1
fi
echo "✅ Docker 서버 시작 완료 (http://localhost:8000)"

# ── 2. 메뉴바 앱 실행 ──

echo ""
echo "⏱ 2. 메뉴바 트레이 앱 실행 중..."

# tray_app.py 백그라운드 실행 (stdout/stderr 로그 파일로)
mkdir -p "$SCRIPT_DIR/logs"
nohup python3 agent/tray_app.py > "$SCRIPT_DIR/logs/tray.log" 2>&1 &
PID=$!

# 실행 확인
sleep 2
if kill -0 $PID 2>/dev/null; then
    echo "✅ 메뉴바 앱 실행됨 (PID: $PID)"
else
    echo "⚠️  메뉴바 앱 실행 실패. 로그 확인: logs/tray.log"
fi

# ── 3. 대시보드 열기 ──

echo ""
echo "📊 3. 대시보드 열기..."

# 잠시 기다렸다가 서버 준비 확인
for i in {1..10}; do
    curl -s -o /dev/null http://localhost:8000/ 2>/dev/null && break
    sleep 1
done

open http://localhost:8000
echo "✅ 브라우저에서 대시보드 열림"

echo ""
echo "=========================================="
echo "  ✅ 실행 완료!"
echo "=========================================="
echo ""
echo "  - 메뉴바 아이콘: ⏱ (시계 모양)"
echo "  - 대시보드: http://localhost:8000"
echo "  - 로그: logs/tray.log"
echo ""
echo "  종료하려면 bin/stop.command 실행"
echo ""

read -p "엔터를 누르면 이 창이 닫힙니다..."
