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
echo "1/4: Swift 컴파일 중..."
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
echo "2/4: Info.plist 복사..."
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

# 5. 실행 권한 + codesign (자체 서명 인증서 — TCC 안정화)
# ad-hoc(-) 서명은 CDHash 기준으로 TCC 매칭 → rebuild마다 권한 재부여 필요
# 자체 서명 인증서 → designated requirement가 certificate leaf 고정 → rebuild 무관
echo "3/4: 버전 증가 + 서명..."
chmod +x "$MACOS/MacTT"
# build 번호는 .build-version state 파일로 유지 (bundle plist는 매 build에 소스로 복사되므로)
VER_FILE=".build-version"
if [ -f "$VER_FILE" ]; then
    CUR_VER=$(cat "$VER_FILE")
else
    CUR_VER=$(/usr/libexec/PlistBuddy -c "Print CFBundleVersion" "$CONTENTS/Info.plist" 2>/dev/null || echo 0)
fi
case "$CUR_VER" in
    ''|*[!0-9]*) CUR_VER=0 ;;
esac
NEW_VER=$((CUR_VER + 1))
echo "$NEW_VER" > "$VER_FILE"
/usr/libexec/PlistBuddy -c "Set CFBundleVersion $NEW_VER" "$CONTENTS/Info.plist" 2>/dev/null
echo "   build $CUR_VER → $NEW_VER"

SIGN_IDENTITY="JSK Mac Time Tracker Signing"
if security find-identity -v -p codesigning 2>/dev/null | grep -q "$SIGN_IDENTITY"; then
    if codesign --force --sign "$SIGN_IDENTITY" "$APP_BUNDLE" 2>/dev/null; then
        echo "   ✅ 서명 완료 (자체 인증서 — TCC: rebuild 무관)"
    else
        echo "   ⚠️ 서명 실패 — ad-hoc으로 대체"
        codesign --force --deep --sign - "$APP_BUNDLE" 2>/dev/null
    fi
else
    echo "   ⚠️ 서명 identity 없음 — ad-hoc 서명 (권한이 rebuild마다 초기화될 수 있음)"
    codesign --force --deep --sign - "$APP_BUNDLE" 2>/dev/null
fi

echo ""
echo "✅ 빌드 완료: $APP_BUNDLE"
echo "   실행: open \"$APP_BUNDLE\""
echo "   또는: $MACOS/MacTT"
