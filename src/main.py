import os
import sys
import PyQt5
import traceback

# src 디렉토리를 Python 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = current_dir
sys.path.append(src_dir)

# Add Qt platform plugin path
if sys.platform == "darwin":  # macOS
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = os.path.join(os.path.dirname(PyQt5.__file__), "Qt", "plugins", "platforms")

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
        print(f"치명적 오류 발생: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    main()