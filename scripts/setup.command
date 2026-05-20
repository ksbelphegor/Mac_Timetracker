#!/bin/bash
# =============================================================================
# Mac Time Tracker — 1회 설정 스크립트
# 더블클릭으로 실행 (처음 한 번만)
# =============================================================================

echo "=========================================="
echo "  Mac Time Tracker 설정 시작"
echo "=========================================="

# 프로젝트 경로
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "📦 1. Python 패키지 설치 중..."
pip3 install --user rumps pyobjc-framework-Cocoa requests fastapi uvicorn[standard] 2>&1
if [ $? -ne 0 ]; then
    echo "⚠️  pip3 설치 실패. pip3가 설치되어 있는지 확인하세요."
    echo "   brew install python3"
    read -p "엔터를 누르면 종료합니다..."
    exit 1
fi

echo ""
echo "✅ Python 패키지 설치 완료"

echo ""
echo "🔒 2. macOS 접근성 권한"
echo "   앱이 창 제목을 읽으려면 접근성 권한이 필요합니다."
echo "   System Settings > Privacy & Security > Accessibility"
echo "   → Terminal (또는 iTerm2)에 체크"
echo ""
echo "=========================================="
echo "  ✅ 설정 완료!"
echo "=========================================="
echo ""
echo "이제 scripts/start.command 를 더블클릭하면 실행됩니다."
echo ""

read -p "엔터를 누르면 종료합니다..."
