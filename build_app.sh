#!/bin/bash

# 스크립트 실행 디렉토리로 이동
cd "$(dirname "$0")"

# 가상 환경 활성화
source venv/bin/activate

# 이전 빌드 파일 제거
rm -rf build dist

# 애플리케이션 빌드
python setup.py py2app --verbose

echo "빌드가 완료되었습니다. dist 폴더에서 .app 파일을 확인하세요."

# 가상 환경 비활성화
deactivate