#!/bin/bash
# Mac Time Tracker — 원클릭 실행 (엔트리포인트)
# 실제 로직은 scripts/start.command (올인원: 빌드 → 실행 → 대시보드)
exec bash "$(cd "$(dirname "$0")" && pwd)/scripts/start.command" "$@"
