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

### 2026-06-11 — 성능/정합성 일괄 리팩터링

**타임존 버그 수정** (`watcher/database.swift`)
- `getHourlyBreakdown`이 UTC 기준으로 floor → 1~8시가 `00:00`에 모두 몰리는 문제.
  `Calendar.current.component(.hour)`로 로컬 시간대로 교정.
- `parseDate`/`todayISO`/`getWeeklyTagStats`가 `ISO8601DateFormatter +09:00` 하드코딩 →
  `DateFormatter` + `Locale en_US_POSIX` + local calendar로 대체. 해외 출장 등 TZ 변경에 안전.

**스레드 안전성** (`watcher/*.swift`)
- `Database`: 단일 connection SQLite → `NSLock`으로 모든 접근 serial화. 읽기중 레코드 쓰기 race 방지.
- `quitApp()`: `Database.shared.close()` 명시적 호출 + `PRAGMA wal_checkpoint(TRUNCATE)`.
  `kill -9` 시 WAL 정합성 위험 감소.
- `HTTPServer.iconCache`: `NSCache.countLimit=200` + `NSLock` (server queue + main thread 동시 read/write)
- `runViaOSAAsync`: osascript 비동기 (브라우저 슬로우 시 UI 3s 블로킹 방지), 0.8s timeout.
  `getWindowTitle()`에서 브라우저 URL은 비동기 수집. Firefox/AX fallback은 sync (0.4s cap).
- 데드 샤스나 부가기타 on-shot timer 제거 (statsTimer 60s + separate 3s 중복 제거).

**HTTP 서버** (`watcher/server.swift`)
- 정적 자원 캐시: HTML `Cache-Control: no-cache` + `ETag`, JS/CSS/PNG `max-age=3600` + `ETag`
  (기존: 모두 `no-cache` → 매 3s poll마다 index.html 재전송).
- `parseRequest`가 `Content-Length`로 body 정확 추출 (기존 naive `\r\n\r\n` split은 한글 제목 etc 특수 문자로 깨질 수 있음).

** 기타 **
- `Info.plist`: `NSAppleEventsUsageDescription` + `NSAccessibilityUsageDescription` 추가.
  (OS가 권한 프롬프트를 요구할 때 설명이 없으면 거부될 수 있음)
- `scripts/stop.command`: `ps aux | grep MacTT$` (한/타일 오일) → `pgrep -x MacTT`
- `.gitignore`: `Mac Time Tracker.app/` 명시 (기존 `*.app`가 long-name 번들을 놓침)
- `Database`: skip app에 `시크릿 모드`/`(로딩 중)` 등 partial-match 스킵 추가 (title=app fallback으로 유입되는 앱 통각)

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
