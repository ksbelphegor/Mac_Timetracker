# ⏱ Mac Time Tracker

> macOS 앱/브라우저 사용 시간을 추적하여 웹 대시보드로 보여줍니다.
> 메뉴바 아이콘 + 창 제목 트래킹 + 세션별 기록

## 구조

```
macOS (터미널)                        Docker
┌──────────────────────────┐        ┌──────────────────────────────┐
│  tray_app.py (rumps)     │  HTTP  │  FastAPI + SQLite             │
│  ├─ ⏱ 메뉴바 아이콘       │ ──────▶│  ├─ /api/heartbeat           │
│  ├─ NSWorkspace 알림      │ 3초    │  ├─ /api/today               │
│  ├─ 브라우저 탭 제목      │        │  ├─ /api/sessions/{app}      │
│  └─ Accessibility 창 제목 │        │  └─ index.html (Chart.js)    │
└──────────────────────────┘        └──────────────────────────────┘
```

## 시작하기

### 1. 받기

```bash
git clone https://github.com/ksbelphegor/Mac_Timetracker.git
cd Mac_Timetracker
```

### 2. 1회 설정

**`bin/setup.command`** 더블클릭 (또는 터미널에서 실행)

- Python 패키지 설치: `rumps`, `pyobjc-framework-Cocoa`, `requests`
- Docker Desktop 설치 확인
- 접근성 권한 설정 안내

### 3. 실행

**`bin/start.command`** 더블클릭 → 자동으로:

1. 🐳 Docker 서버 시작 (`docker compose up -d`)
2. ⏱ 메뉴바 트레이 앱 실행
3. 📊 대시보드 브라우저 열기

### 4. 종료

메뉴바 **⏱ 아이콘 → ✕ 종료** 클릭

- Docker 서버도 함께 종료

---

## 기능

### 메뉴바 트레이 (tray_app.py)

| 항목 | 설명 |
|---|---|
| ⏱ 시계 아이콘 | 메뉴바에 표시 (텍스트 없음) |
| 📌 현재 앱 | 실시간 실행 중인 앱 이름 |
| ⏱ 오늘 | 오늘 총 트래킹 시간 |
| ⏸ 일시정지 | 트래킹 일시 중지/재개 |
| 📊 대시보드 열기 | 브라우저 열기 |
| ✕ 종료 | Docker + 앱 종료 |

### 창 제목 트래킹

앱마다 최적의 방법으로 창 제목 수집:

| 앱 | 방식 | 예시 |
|---|---|---|
| Brave / Chrome / Edge / Arc / Opera | 브라우저 AppleScript | `유튜브 - YouTube` |
| Safari | Safari AppleScript | `개인 — 시작 페이지` |
| DaVinci Resolve / Finder / 일반 앱 | Accessibility API | `I와 E` |
| 그 외 | 앱명 fallback | `카카오톡` |

### 대시보드

```
┌──────────────────────────────┬──────────────────┐
│  📌 Brave Browser            │  앱 목록           │
│                              │                   │
│  📄 에펨코리아                │  Brave Browser    │ ← 클릭
│     21:00:00 ~ 21:05:00     │     01:23:45      │
│      5분                     │  DaVinci Resolve  │
│                              │     00:45:12      │
│  📄 유튜브 - YouTube          │  Finder            │
│     20:55:00 ~ 21:00:00     │     00:12:34       │
│      5분                     │  ...               │
│                              │                   │
│  📄 I와 E                    │                   │
│     20:45:00 ~ 20:55:00     │                   │
│      10분                    │                   │
└──────────────────────────────┴──────────────────┘
```

- **오른쪽**: 앱 목록 (클릭 가능)
- **왼쪽**: 선택한 앱의 창 제목별 세션 (시작~종료, 지속시간)

## API

| 경로 | 설명 |
|---|---|
| `GET /` | 대시보드 |
| `GET /api/today` | 오늘 앱별 통계 + 마지막 창 제목 |
| `GET /api/now` | 현재 실행 중인 앱 |
| `GET /api/hourly` | 시간대별 사용 내역 |
| `GET /api/sessions/{app}` | 앱의 창 제목별 세션 목록 |
| `GET /api/recent` | 최근 heartbeat 내역 |
| `GET /api/summary` | 기간별 요약 |
| `POST /api/heartbeat` | heartbeat 수신 |

## 요구사항

- macOS (Apple Silicon / Intel)
- Docker Desktop
- Python 3.10+
- macOS 접근성 권한 (System Settings → Privacy → Accessibility)

---

## 변경 이력

### 2026-05-21 — 사이트 분류 정밀화 + 캐시 오염 수정

**사이트 분류 (`extractGroupName` in `dashboard/static/index.html`)**

- URL 도메인 기반 그룹핑으로 변경 (가장 정확)
- `siteNames` 맵: 도메인 → 한글 사이트명 (뉴토끼, 에펨코리아, 네이버, YouTube 등 20+)
- `extractDomain`: 서브도메인 정리 강화 (`page-1.`, `cafe.`, `series.` 등 제거)
- title fallback: 첫 번째 세그먼트를 사이트명으로 사용 (한국 커뮤니티 사이트 패턴 대응)
- URL 없는 세션 진단 로그 (F12 Console 확인)

**캐시 오염 수정 (`watcher/app.swift`)**

- `cachedAppName` 추가 → 같은 앱에서만 캐시 유효, 앱 전환 시 무효화
- `sendHeartbeat`: URL은 브라우저 앱에서만 attach
  → DaVinci Resolve 등 비브라우저 앱에 브라우저 URL이 잘못 붙는 문제 해결

**브라우저 지원 추가**

- 네이버 웨일 (Whale), 시크릿 모드 AppleScript 추가
  (`Config.browserScripts` + `Database.browserApps`)

**새로고침 주기**

- 대시보드 `setInterval`: 5s → 3s (Swift heartbeat 3s와 일치)

---

## 라이선스

MIT
