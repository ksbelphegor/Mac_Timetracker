# Mac Time Tracker 🕐

macOS 메뉴바 앱 — 어떤 앱에서, 어떤 창(제목/URL)을 보고 있었는지 3초 간격으로 추적하고,
로컬 대시보드에서 일별·카테고리·태그 분석을 제공합니다. 의존성 0, Swift 단일 바이너리.

> **프라이버시**: 모든 데이터는 로컬 SQLite(`~/.mactimetracker/aw.db`)에만 저장됩니다.
> 네트워크 전송은 없으며, HTTP 대시보드는 **loopback(127.0.0.1) 전용**으로 제한되어
> LAN/스마트폰에서 접근할 수 없습니다.

## 빠른 시작

```bash
# 원클릭: 빌드(필요 시) → 실행 → 대시보드 열기
./start.command
```

또는 수동:

```bash
bash scripts/build-swift.sh        # 빌드 → ./Mac Time Tracker.app
open "Mac Time Tracker.app"        # 실행 (메뉴바 🕐)
# 대시보드: http://localhost:8000
```

## 구성

```
Mac Time Tracker.app   ← scripts/build-swift.sh 산출물 (repo 루트에 빌드됨)
├── Contents/MacOS/MacTT            # Swift 바이너리 (메뉴바 + HTTP 서버 + 수집)
└── Contents/Resources/dashboard/   # 대시보드 정적 파일 (index.html, categories.html)

watcher/               # Swift 소스
├── main.swift         # 진입점 (LSUIElement 앱)
├── app.swift          # 메뉴바 UI, 3s heartbeat, 권한 모니터/설정
├── server.swift       # HTTP 대시보드 서버 (loopback 전용, port 8000)
├── database.swift     # SQLite (WAL, 배치 쓰기, columnization, 백필)
├── Info.plist
└── icon.png

dashboard/static/      # 대시보드 (정적 파일 — 앱이 서빙)
scripts/               # 빌드/실행/launchd 스크립트
```

### 데이터 파이프라인

```
메인 스레드 3s heartbeat
  └─ 앞UIApplication(app/창) + CGWindow 타이틀 + (브라우저) osascript URL
       └─ SQLite events (버퍼 5s/20개 배치 commit, WAL)
            └─ HTTP /api/*  ←  대시보드 (10s 폴링)
```

- `events` 테이블: `app`/`title`/`url`은 컬럼으로 정규화되어 있고(legacy JSON `data`
  컬럼은 백필 완료 후 정화), 읽기는 `COALESCE(컬럼, json_extract(...))`로 백필 중에도 정확합니다.
- **전체 데이터 보존** (유지보수/삭제 정책 없음) — 파일만 경량화합니다.

## 대시보드

| 탭 | 내용 |
|---|---|
| 오늘 | 앱별 사용 시간, 현재 앱, 앱 아이콘 |
| 카테고리 | 규칙(정규식) 기반 스택드 바 + 매칭 미리보기 |
| 태그 | `app_tags` + 타이틀 regex 기반 집계 (범례: 이름 + %) |

설정(⚙️, 탭 행 오른쪽): 스크린 레코딩/액세스빌리티 상태 실시간 확인,
"다시 확인", "시스템 설정 열기" — **권한은 1회 부여하면 유지**되고,
앱은 60초마다 비정상(남김 없이) 재확인하여 자동으로 적용합니다.

## 권한 (1회만)

| 권한 | 용도 | 부여 |
|---|---|---|
| 스크린 레코딩 | 모든 앱의 창 목록 | 시스템 설정 → 개인정보 보호 → 스크린 레코딩 |
| 보조기(Accessibility) | 전단 창 제목, 앱 전환 | 시스템 설정 → 개인정보 보호 → 보조 제어 |
| 자동화 | 브라우저 탭 제목/URL | 최초 요청 시 시스템 프롬프트 |

👉 **더 이상 매 재시작마다 프롬프트가 나오지 않습니다.**
권한은 macOS TCC에 1회 저장되고, 대시보드 ⚙️에서 상태를 확인할 수 있습니다.

## 자동 시작 / 크래시 복구 (선택)

```bash
# plist 템플릿에 홈/앱 경로 채워서 설치
sed -e "s|__HOME__|$HOME|" \
    -e "s|__APP_PATH__|$(pwd)|" \
    scripts/com.jsk.mactimetracker.plist > ~/Library/LaunchAgents/com.jsk.mactimetracker.plist
launchctl load ~/Library/LaunchAgents/com.jsk.mactimetracker.plist   # 로그인 시 자동 실행
```

- `KeepAlive.SuccessfulExit=true`: **크래시 시에만** 자동 재시작 (수동 quit은 존중)
- 로그: `~/.mactimetracker/launchd.log`, `launchd-err.log`

## 코드 서명 (TCC 안정화)

- `scripts/build-swift.sh`는 자체 서명 인증서(`JSK Mac Time Tracker Signing`)로 서명합니다.
  ad-hoc 서명은 CDHash 기준으로 TCC가 매칭해서 **매 rebuild마다 권한이 초기화**되는 문제를
  certificate-leaf 고정 designated requirement로 해결했습니다.
- 인증서는 `~/.code-signing/mactimetracker/`에 원본(pem/p12)이 있고 로그인 키체인에
  import되어 있습니다. (25년 유효, codeSigning EKU)
- 키체인에 identity가 없는 환경에서는 ad-hoc으로 fallback합니다.

## API (localhost:8000)

| Endpoint | 설명 |
|---|---|
| `GET /api/ping` | 연결 확인 |
| `GET /api/today` | 앱별 일별 집계 + 현재 앱 |
| `GET /api/categories` | 카테고리·규칙 트리 |
| `GET /api/category-all-matches` | 카테고리별 매칭 미리보기 |
| `GET /api/tag-stats` | 태그 집계 (regex) |
| `GET /api/browser-sessions` | 브라우저 세션 (탭 이동 병합) |
| `GET /api/sessions/{app}` | 앱별 세션 |
| `GET/POST /api/permissions` | 권한 상태 / 재확인·프롬프트 |
| `POST /api/heartbeat` | 외부 이벤트 등록 (레거시) |

## troubleshooting

- **권한 박스/데이터가 비어 있음** → 대시보드 ⚙️에서 상태 확인 후 "시스템 설정 열기"
- **port 충돌** → 8000 포트를 다른 프로그램이 쓰고 있으면 서버 시작 실패 (메뉴바 상태 표시)
- **로그** → `~/.mactimetracker/app.log`, `launchd-err.log`

## 라이선스

[MIT](LICENSE)
