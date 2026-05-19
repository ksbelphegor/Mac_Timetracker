# Mac Time Tracker v2

> macOS 앱 사용 시간을 추적하여 웹 대시보드로 보여줍니다.
> **ActivityWatch**의 검증된 watcher(`aw-watcher-window`)를 macOS에서 실행하고,
> **FastAPI + Chart.js** 서버를 Docker로 띄워 대시보드를 제공합니다.

## 구조

```
맥북 (pip 2개 설치)              Docker (맥북에서 실행)
┌──────────────────┐           ┌──────────────────────────┐
│ aw-watcher-window │  HTTP    │ FastAPI + SQLite         │
│ (ActivityWatch)   │ ──────▶  │ 웹 대시보드 (:8000)      │
│                   │ 1초 간격  │ Chart.js 차트            │
│ watch_bridge.py   │          │                          │
└──────────────────┘           └──────────────────────────┘
```

## 설치 및 실행

### 1. macOS 에이전트 (맥북, 1회)

```bash
pip3 install aw-watcher-window requests
```

**Accessibility 권한** 설정:
- 시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용
- `터미널` 또는 `aw-watcher-window`에 체크

### 2. Docker 서버 (맥북)

```bash
docker compose up -d
```

### 3. 실행

```bash
# 터미널 1: watcher 실행
pip3 install aw-watcher-window requests
python3 agent/watch_bridge.py

# 터미널 2: 브라우저 열기
open http://localhost:8000
```

또는 launchd에 등록하면 로그인 시 자동 실행:
```bash
launchctl load ~/Library/LaunchAgents/com.mactimetracker.watcher.plist
```

## API

| 경로 | 설명 |
|---|---|
| `GET /` | 대시보드 |
| `GET /api/today` | 오늘 앱별 통계 |
| `GET /api/now` | 현재 실행 중인 앱 |
| `GET /api/hourly` | 시간대별 사용 내역 |
| `GET /api/summary?start=&end=` | 기간별 요약 |
| `POST /api/heartbeat` | ActivityWatch heartbeat 수신 |

## 라이선스

MIT
