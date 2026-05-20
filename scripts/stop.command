#!/bin/bash
# Mac Time Tracker — 종료 스크립트
# Swift 단일 바이너리 kill

echo "=========================================="
echo "  Mac Time Tracker 종료"
echo "=========================================="

PID=$(ps aux | grep "MacTT$" | grep -v grep | awk '{print $2}')
if [ -n "$PID" ]; then
    echo ""
    echo "⏱ MacTT 종료 중... (PID: $PID)"
    kill $PID 2>/dev/null
    sleep 1
    PID=$(ps aux | grep "MacTT$" | grep -v grep | awk '{print $2}')
    [ -n "$PID" ] && kill -9 $PID 2>/dev/null
    echo "✅ 종료됨"
else
    echo "ℹ️  실행 중인 MacTT 없음"
fi

echo ""
echo "=========================================="
echo "  ✅ 종료 완료"
echo "=========================================="
echo ""
read -p "엔터를 누르면 종료합니다..."
