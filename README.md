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

1. 가상 환경이 활성화된 상태에서:
```bash
python src/main.py
```

## 프로젝트 구조

```
timer/
├── src/
│   ├── core/          # 핵심 기능
│   │   ├── config.py
│   │   ├── data_manager.py
│   │   └── status_bar.py
│   ├── ui/            # 사용자 인터페이스
│   │   ├── widgets/
│   │   │   ├── app_tracking.py
│   │   │   ├── home_widget.py
│   │   │   └── timer_widget.py
│   │   └── timer_setting.py
│   └── main.py
├── requirements.txt
└── README.md
```

## 기여 방법

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요. 