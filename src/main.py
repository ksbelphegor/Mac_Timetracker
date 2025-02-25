import os
import sys
import PyQt5
import traceback
import logging
from pathlib import Path

# src 디렉토리를 Python 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# 플러그인 경로 설정
if sys.platform == "darwin":  # macOS
    # 여러 가능한 경로 시도 (일반적인 경로만 포함)
    qt_plugin_paths = [
        os.path.join(os.path.dirname(PyQt5.__file__), "Qt", "plugins"),
        os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins"),
        os.path.join(os.path.dirname(PyQt5.__file__), "plugins")
    ]
    
    # 사용자 홈 디렉토리 기반 경로 추가 (더 범용적)
    home = str(Path.home())
    qt_plugin_paths.extend([
        os.path.join(home, ".conda/lib/python3.9/site-packages/PyQt5/Qt/plugins"),
        os.path.join(home, ".conda/lib/python3.9/site-packages/PyQt5/Qt5/plugins"),
        os.path.join(home, "miniconda3/lib/python3.9/site-packages/PyQt5/Qt5/plugins"),
        os.path.join(home, "anaconda3/lib/python3.9/site-packages/PyQt5/Qt5/plugins")
    ])
    
    # 현재 PyQt5 설치 경로 기반 추가 탐색
    pyqt_dir = os.path.dirname(PyQt5.__file__)
    for root, dirs, files in os.walk(pyqt_dir):
        if "platforms" in dirs and os.path.exists(os.path.join(root, "platforms", "libqcocoa.dylib")):
            qt_plugin_paths.append(root)
    
    # 플러그인 경로 중 실제로 존재하는 경로 찾기
    for path in qt_plugin_paths:
        platform_path = os.path.join(path, "platforms")
        if os.path.exists(platform_path) and os.path.exists(os.path.join(platform_path, "libqcocoa.dylib")):
            os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = platform_path
            print(f"플러그인 경로 설정: {platform_path}")
            print("'cocoa' 플러그인 찾음!")
            break
    else:
        print("경고: 유효한 Qt 플러그인 경로를 찾을 수 없습니다.")
        # 마지막 시도: PyQt5 경로에서 'platforms' 디렉토리 검색
        for root, dirs, files in os.walk(os.path.dirname(PyQt5.__file__)):
            if "platforms" in dirs:
                platform_path = os.path.join(root, "platforms")
                if os.path.exists(os.path.join(platform_path, "libqcocoa.dylib")):
                    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = platform_path
                    print(f"플러그인 경로 설정: {platform_path}")
                    print("'cocoa' 플러그인 찾음!")
                    break

from PyQt5.QtWidgets import QApplication
from ui.timer_king import TimerKing
from core.data_manager import DataManager
from core.config import APP_NAME, BUNDLE_ID, setup_logging
import objc
from Foundation import NSBundle

def main():
    """앱의 메인 진입점입니다."""
    # 로깅 시스템 초기화
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # 데이터 매니저 초기화
        data_manager = DataManager.get_instance()
        data_manager.ensure_data_directory()
        
        # 앱 실행
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        app.setApplicationName(APP_NAME)
        
        # 스타일 설정
        style_file = os.path.join(os.path.dirname(__file__), 'ui', 'styles.qss')
        if os.path.exists(style_file):
            with open(style_file, 'r') as f:
                app.setStyleSheet(f.read())
        
        # macOS 앱 설정
        bundle = NSBundle.mainBundle()
        info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
        if info:
            info['CFBundleName'] = APP_NAME
            info['CFBundleIdentifier'] = BUNDLE_ID
            info['LSUIElement'] = True  # dock 아이콘 숨기기
        
        # 메인 윈도우 생성
        main_window = TimerKing()
        main_window.show()
        
        sys.exit(app.exec_())
        
    except Exception as e:
        logger.error(f"치명적 오류 발생: {e}")
        logger.error(traceback.format_exc())

if __name__ == '__main__':
    main()