# Mac Time Tracker (맥 타임좌)

M1 Mac용 앱 사용 시간 추적기입니다. Python과 PyQt5로 개발되었습니다.

## 주요 기능

- 실행 중인 앱들의 사용 시간 자동 추적
- 상태 표시줄에서 현재 앱 사용 시간 실시간 확인
- 일별 사용 통계 제공
- 앱별 사용 시간 그래프 시각화
- 창(윈도우)별 상세 사용 시간 기록

## 시스템 요구사항

- macOS (M1 Mac 최적화)
- Python 3.x
- PyQt5
- pyobjc-core
- pyobjc-framework-Cocoa

## 설치 방법

1. 저장소 클론:
```bash
git clone https://github.com/ksbelphegor/Mac_Timetracker.git
cd Mac_Timetracker
```

2. 가상 환경 생성 및 활성화:
```bash
python -m venv venv
source venv/bin/activate
```

3. 필요한 패키지 설치:
```bash
pip install -r requirements.txt
```

## 실행 방법

### 간편 실행 (권장)
1. **더블클릭으로 실행**: `Mac_Timetracker.command` 파일을 더블클릭
   - 처음 실행시 자동으로 가상환경 생성 및 패키지 설치
   - 이후부터는 바로 앱 실행

### 수동 실행
1. 가상 환경이 활성화된 상태에서:
```bash
python src/main.py
```

## 프로젝트 구조

```
Mac_Timetracker/
├── src/
│   ├── core/                # 핵심 기능
│   │   ├── app_tracker.py   # 앱 추적 로직
│   │   ├── config.py        # 설정 관리
│   │   ├── data_manager.py  # 데이터 관리
│   │   ├── status_bar.py    # 상태 표시줄
│   │   └── timer_manager.py # 타이머 관리
│   ├── ui/                  # 사용자 인터페이스
│   │   ├── widgets/         # UI 위젯 컴포넌트
│   │   │   ├── app_tracking.py    # 앱 추적 위젯
│   │   │   ├── home_widget.py     # 홈 화면 위젯
│   │   │   ├── time_graph_widget.py # 시간 그래프 위젯
│   │   │   └── timer_widget.py    # 타이머 위젯
│   │   ├── timer_king.py    # 메인 UI 컨트롤러
│   │   └── ui_controller.py # UI 컨트롤러
│   └── main.py              # 프로그램 진입점
├── requirements.txt         # 의존성 패키지 목록
└── README.md                # 프로젝트 설명서
```

## 기여 방법

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 버전 히스토리

### v1.0.1 (2025-08-16)
**버그 수정 및 UI 개선**
- 🐛 **버그 수정**: `timer_data`가 `None`인 경우 발생하는 AttributeError 해결
  - `ui_controller.py`에서 안전한 `None` 체크 추가
  - `timer_manager.py`에서 기본값 초기화 로직 강화
  - `app_tracker.py`에서 안전한 데이터 접근 구현
- 🎨 **UI 개선**: 창 크기 자유 조절 가능
  - 메인 창 최소 크기 설정 (600x400)
  - 타이머 위젯 최소 크기 설정 (250x150)
  - 모든 창에서 크기 조절 가능하도록 변경
- ⚡ **편의성 개선**: 더블클릭 실행 파일 추가
  - `Mac_Timetracker.command` 파일로 간편 실행
  - 자동 가상환경 설정 및 패키지 설치

### v1.0.0
**초기 릴리스**
- 기본 앱 사용 시간 추적 기능
- 상태 표시줄 통합
- 일별 사용 통계 제공

## 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요. 