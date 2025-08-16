#!/bin/bash

# Mac Time Tracker 더블클릭 실행 파일

# 스크립트가 있는 디렉토리로 이동
cd "$(dirname "$0")"

# 터미널 창 제목 설정
echo -ne "\033]0;Mac Time Tracker\007"

echo "🕐 Mac Time Tracker 시작 중..."

# 가상환경이 없으면 생성
if [ ! -d "venv" ]; then
    echo "📦 처음 실행입니다. 환경 설정 중... (잠시만 기다려주세요)"
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    # 가상환경 활성화
    source venv/bin/activate
fi

# 앱 실행
echo "🚀 Mac Time Tracker 실행!"
python3 src/main.py

# 실행 완료 후 종료 대기
echo ""
echo "앱이 종료되었습니다. 아무 키나 누르면 창이 닫힙니다..."
read -n 1