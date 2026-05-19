# Mac Time Tracker (맥 타임좌)

> macOS 상태바에서 실행 중인 앱들의 사용 시간을 추적하는 경량 네이티브 앱입니다.
> **PyQt5 불필요** — 순수 macOS AppKit(pyobjc)으로 제작되어 가볍고 빠릅니다.

## 주요 기능

- 🔍 **실시간 앱 추적**: 현재 사용 중인 앱을 자동 감지 (1초 간격)
- 📊 **사용 시간 기록**: 앱별/일별 사용 통계 자동 저장
- 🖥️ **상태바 통합**: 메뉴바에서 현재 앱 사용 시간 확인
- 📈 **메뉴 통계**: 오늘 총 사용 시간 + 상위 앱별 통계
- 🚀 **초경량**: PyQt5 제거, `.app` 용량 80MB → ~15MB

## 시스템 요구사항

- macOS 12+ (Monterey 이상)
- Python 3.9+
- **설치 불필요**: `.app` 번들을 다운로드하여 실행만 하면 됩니다.

## 설치 방법

### 사용자용 (앱 번들)
1. [Releases](https://github.com/ksbelphegor/Mac_Timetracker/releases)에서 최신 `.app` 다운로드
2. `/Applications/` 폴더로 드래그
3. 더블클릭하여 실행!
4. 최초 실행시 Accessibility 권한 요청 → "시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용"에서 터미널(또는 앱)에 체크

### 개발자용
```bash
# 저장소 클론
git clone https://github.com/ksbelphegor/Mac_Timetracker.git
cd Mac_Timetracker

# 가상 환경 (선택)
python3 -m venv venv
source venv/bin/activate

# 의존성 설치 (pyobjc만 있음, PyQt5 불필요!)
pip install -r requirements.txt

# 실행
python3 src/main.py

# 앱 번들 생성 (배포용)
pip install py2app
python3 setup.py py2app
open "dist/Mac Time Tracker.app"
```

## 프로젝트 구조

```
Mac_Timetracker/
├── src/
│   ├── core/
│   │   ├── app_tracker.py    # NSWorkspace 기반 앱 추적
│   │   ├── config.py         # 설정 관리
│   │   ├── data_manager.py   # JSON 데이터 저장/로드
│   │   ├── status_bar.py     # AppKit 네이티브 상태바
│   │   └── timer_manager.py  # 타이머 관리
│   └── main.py               # NSApplication 진입점
├── setup.py                  # py2app 번들링
├── requirements.txt          # pyobjc만
└── README.md
```

## 파일 구조

### `~/.mactimetracker/`
- `app_usage.json` — 앱별 일별 사용 시간
- `timer_data.json` — 현재 세션 타이머 상태
- `config.json` — 사용자 설정
- `app.log` — 로그 파일

## 라이선스

MIT License
