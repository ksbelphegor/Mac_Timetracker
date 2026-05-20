#!/bin/bash
# =============================================================================
# Mac Time Tracker — 올인원 실행 스크립트
# Swift .app을 빌드해서 실행 (Dock 고정 가능!)
# =============================================================================

echo "=========================================="
echo "  🕐 Mac Time Tracker"
echo "=========================================="

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR" || { echo "❌ 경로 이동 실패"; exit 1; }

mkdir -p logs

APP_BUNDLE="$SCRIPT_DIR/Mac Time Tracker.app"
APP_BINARY="$APP_BUNDLE/Contents/MacOS/MacTT"

# ── 0. Swift 빌드 (없거나 오래됐으면) ──

NEED_BUILD=false
if [ ! -f "$APP_BINARY" ]; then
    NEED_BUILD=true
elif [ "watcher/tray.swift" -nt "$APP_BINARY" ] || [ "watcher/Info.plist" -nt "$APP_BINARY" ]; then
    NEED_BUILD=true
fi

if [ "$NEED_BUILD" = true ]; then
    echo ""
    echo "🔨 Swift 앱 빌드 중..."
    bash scripts/build-swift.sh 2>&1 | tail -3
    if [ ! -f "$APP_BINARY" ]; then
        echo "❌ 빌드 실패"
        exit 1
    fi
    echo "✅ 빌드 완료 (115KB)"
fi

# ── 1. API 서버 확인 (Swift .app이 내부적으로 실행하지만, 대시보드 빠른 오픈을 위해 선실행) ──

echo ""
echo "🚀 1. API 서버 확인 중..."
if curl -s -o /dev/null http://localhost:8000/ 2>/dev/null; then
    echo "✅ 이미 실행 중"
else
    # Swift .app이 서버를 실행할 때까지 잠시 대기
    echo "   Swift 앱이 서버를 시작합니다..."
fi

# ── 2. Swift 메뉴바 앱 실행 ──

echo ""
echo "⏱ 2. 메뉴바 트레이 앱 실행 중..."
open "$APP_BUNDLE"
echo "✅ Mac Time Tracker.app 실행됨"
echo "   (메뉴바 ⏱ 아이콘 확인)"

# ── 3. 서버 준비 대기 후 대시보드 열기 ──

echo ""
echo "📊 3. 대시보드 열기..."
for i in {1..15}; do
    curl -s -o /dev/null http://localhost:8000/ 2>/dev/null && break
    sleep 1
done
open http://localhost:8000

echo ""
echo "=========================================="
echo "  ✅ 완료!"
echo "=========================================="
echo ""
echo "  - 메뉴바: ⏱ 아이콘"
echo "  - 대시보드: http://localhost:8000"
echo "  - 종료: 메뉴바 ⏱ → ✕ 종료"
echo "  - Dock 고정: Mac Time Tracker.app 을 Dock에 드래그"
echo ""

read -p "엔터를 누르면 창이 닫힙니다..."
