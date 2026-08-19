#!/bin/bash
# 매 build 후 실행: /Applications에 copy + TCC reset (SHA mismatch 정리)
# user는 system setting에서 'Allow' 한 번만 (매 build마다 필요)
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP="$DIR/Mac Time Tracker.app"
DEST="/Applications/Mac Time Tracker.app"

echo ""
echo "=========================================="
echo "📦 Mac Time Tracker 배포 (/Applications)"
echo "=========================================="
echo ""

if [ ! -d "$APP" ]; then
    echo "❌ $APP 없음"
    echo "   먼저 bash scripts/build-swift.sh 실행"
    exit 1
fi

echo "→ 종료 (실행 중이면)..."
"$DIR/scripts/stop.command" > /dev/null 2>&1 || true
sleep 1

echo "→ /Applications에 copy..."
rm -rf "$DEST"
cp -R "$APP" "$DEST"
echo "   ✅ copy 완료"

echo "→ TCC 권한 초기화 (SHA mismatch 정리)..."
tccutil reset ScreenCapture com.ksbelphegor.mactimetracker 2>&1 || true
tccutil reset Accessibility com.ksbelphegor.mactimetracker 2>&1 || true
tccutil reset AppleEvents com.ksbelphegor.mactimetracker 2>&1 || true
echo "   ✅ 초기화 완료"

echo ""
echo "=========================================="
echo "⚠️  권한 재허용 (매 build마다 1회):"
echo "=========================================="
echo "   시스템 설정 → 개인정보 보호 및 보안:"
echo "     1. 스크린 레코딩: Mac Time Tracker + 추가/ON"
echo "     2. 손쉬운 사용: Mac Time Tracker + 추가/ON"
echo "=========================================="
echo ""

open "$DEST"
echo "✅ 실행 (/Applications)"
