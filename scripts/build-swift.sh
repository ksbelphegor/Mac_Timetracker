#!/bin/bash
# Mac Time Tracker — Swift 빌드 스크립트
# watcher/tray.swift → Mac Time Tracker.app

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
swiftc watcher/tray.swift \
    -o "$MACOS/MacTT" \
    -framework Cocoa \
    -framework Foundation \
    -parse-as-library \
    -O \
    -whole-module-optimization 2>&1

echo "   ✅ 컴파일 완료"

# 2. Info.plist
echo "2/3: Info.plist 복사..."
cp watcher/Info.plist "$CONTENTS/"

# 3. 아이콘 (PNG를 그대로 사용, .icns는 없으니 skip)
if [ -f watcher/icon.png ]; then
    cp watcher/icon.png "$RESOURCES/"
fi

echo "   ✅ 번들 구성 완료"

# 4. 실행 권한
chmod +x "$MACOS/MacTT"

echo ""
echo "✅ 빌드 완료: $APP_BUNDLE"
echo "   실행: open \"$APP_BUNDLE\""
echo "   또는: ./$APP_BUNDLE/Contents/MacOS/MacTT"
