#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import traceback
import logging
import subprocess
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
            logging.debug(f"플러그인 경로 설정: {platforms_dir}")
    except Exception as e:
        logging.error(f"플러그인 경로 설정 중 오류 발생: {e}")

from src.ui.timer_king import TimerKing
from src.core.data_manager import DataManager
from src.core.config import APP_NAME, BUNDLE_ID, setup_logging, APP_VERSION
import objc
from Foundation import NSBundle

logger = logging.getLogger(__name__)


def check_accessibility_permission():
    """macOS Accessibility 권한이 있는지 확인하고, 없으면 사용자에게 안내합니다.

    Returns:
        bool: Accessibility 권한이 있는 경우 True
    """
    try:
        result = subprocess.run(
            ['osascript', '-e',
             'tell application "System Events" to get name of every process'],
            capture_output=True, text=True, timeout=3.0
        )
        if result.returncode != 0:
            QMessageBox.warning(
                None, "권한 필요",
                "Mac Time Tracker가 앱 사용 시간을 추적하려면 "
                "Accessibility 접근 권한이 필요합니다.\n\n"
                "설정 방법:\n"
                "1. 시스템 환경설정 → 개인정보 보호 및 보안 → 손쉬운 사용\n"
                "2. Mac Time Tracker (또는 터미널) 추가\n"
                "3. 체크박스 활성화\n\n"
                "권한이 없으면 앱 사용 시간 데이터가 수집되지 않습니다."
            )
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.warning("Accessibility 권한 확인 시간 초과")
        return False
    except Exception as e:
        logger.warning(f"Accessibility 권한 확인 실패: {e}")
        return False


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

        # Accessibility 권한 확인 (비차단, 실패해도 앱은 실행)
        has_access = check_accessibility_permission()
        if not has_access:
            logger.warning("Accessibility 권한 없음 - 창 제목 추적이 제한됩니다.")

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
