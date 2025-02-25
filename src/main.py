#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import traceback
import logging
from pathlib import Path

# 현재 디렉토리의 상위 디렉토리를 Python 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)  # Mac_Timetracker 디렉토리
sys.path.append(parent_dir)

# PyQt5 가져오기 - 가상 환경에서만 실행되도록 확인
try:
    import PyQt5
    from PyQt5.QtWidgets import QApplication, QMessageBox
    from PyQt5.QtCore import Qt
except ImportError:
    print("PyQt5를 찾을 수 없습니다. 가상 환경을 활성화하고 실행했는지 확인하세요.")
    print("다음 명령어로 실행하세요:")
    print("  source venv/bin/activate")
    print("  python src/main.py")
    sys.exit(1)

# 플러그인 경로 설정 (최소화 버전)
if sys.platform == "darwin":  # macOS
    try:
        pyqt_dir = os.path.dirname(PyQt5.__file__)
        platforms_dir = os.path.join(pyqt_dir, "Qt", "plugins", "platforms")
        
        # Qt5 디렉토리 체크
        if not os.path.exists(platforms_dir):
            platforms_dir = os.path.join(pyqt_dir, "Qt5", "plugins", "platforms")
        
        # 플랫폼 플러그인 확인
        if os.path.exists(platforms_dir) and os.path.exists(os.path.join(platforms_dir, "libqcocoa.dylib")):
            os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = platforms_dir
            print(f"플러그인 경로 설정: {platforms_dir}")
    except Exception as e:
        print(f"플러그인 경로 설정 중 오류 발생: {e}")

from src.ui.timer_king import TimerKing
from src.core.data_manager import DataManager
from src.core.config import APP_NAME, BUNDLE_ID, setup_logging
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
        
        # 앱 종료 시 정리 작업 추가
        app.aboutToQuit.connect(lambda: main_window._save_all_data())
        
        sys.exit(app.exec_())
        
    except Exception as e:
        logger.error(f"치명적 오류 발생: {e}")
        logger.error(traceback.format_exc())
        
        # GUI 오류 메시지 표시 (앱 초기화가 완료된 경우)
        if 'app' in locals():
            QMessageBox.critical(None, "오류", f"앱 실행 중 오류가 발생했습니다:\n{str(e)}")

if __name__ == '__main__':
    main()