#!/bin/bash
# Mac Time Tracker — Swift 빌드 스크립트
# 모든 .swift 파일을 컴파일 -> .app 번들

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

APP_NAME="Mac Time Tracker"
APP_BUNDLE="$APP_NAME.app"
CONTENTS="$APP_BUNDLE/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"

echo "🔨 Mac Time Tracker Swift 빌드"
echo ""

# 1. 컴파일
echo "1/3: Swift 컴파일 중..."
mkdir -p "$MACOS" "$RESOURCES"
swiftc watcher/*.swift \
    -o "$MACOS/MacTT" \
    -framework Cocoa \
    -framework Foundation \
    -framework ApplicationServices \
    -framework Network \
    -O 2>&1

echo "   ✅ 컴파일 완료"

# 2. Info.plist
echo "2/3: Info.plist 복사..."
cp watcher/Info.plist "$CONTENTS/"

# 3. 아이콘
if [ -f watcher/icon.png ]; then
    cp watcher/icon.png "$RESOURCES/"
fi

# 4. 대시보드 정적 파일 복사
if [ -d dashboard/static ]; then
    mkdir -p "$RESOURCES/dashboard"
    cp -r dashboard/static "$RESOURCES/dashboard/"
    echo "   ✅ 대시보드 복사 완료"
fi

echo "   ✅ 번들 구성 완료"

# 5. 실행 권한 + codesign
chmod +x "$MACOS/MacTT"
codesign --force --deep --sign - "$APP_BUNDLE" 2>/dev/null

echo ""
echo "✅ 빌드 완료: $APP_BUNDLE"
echo "   실행: open \"$APP_BUNDLE\""
echo "   또는: $MACOS/MacTT"
