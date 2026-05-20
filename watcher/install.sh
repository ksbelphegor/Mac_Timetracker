#!/bin/bash
# Mac Time Tracker — macOS 에이전트 설치 스크립트
# pip 2줄로 끝!

set -e

echo "🕐 Mac Time Tracker — macOS 에이전트 설치"
echo "============================================"
echo ""

if ! command -v python3 &>/dev/null; then
    echo "❌ Python3이 필요합니다."
    exit 1
fi
echo "✅ Python3: $(python3 --version)"

echo ""
echo "📦 1/2: pyobjc-framework-Cocoa 설치 중..."
pip3 install pyobjc-framework-Cocoa 2>&1 | tail -1

echo ""
echo "📦 2/2: requests 설치 중..."
pip3 install requests 2>&1 | tail -1

echo ""
echo "============================================"
echo "✅ 설치 완료!"
echo ""
echo "실행:"
echo "  python3 $(dirname "$0")/tray.py"
echo ""
echo "Docker 서버 실행:"
echo "  docker compose up -d"
echo ""
echo "대시보드: http://localhost:8000"
