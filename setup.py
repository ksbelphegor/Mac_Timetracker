"""
setup.py for Mac Time Tracker
macOS 앱 번들 생성을 위한 설정 파일
"""

from setuptools import setup
import py2app
import sys
import os

# 앱 정보
APP_NAME = 'Mac Time Tracker'
MAIN_SCRIPT = 'src/main.py'
VERSION = '1.0.1'

# 아이콘 파일 (없으면 기본 아이콘 사용)
ICON_FILE = None

# py2app 옵션
OPTIONS = {
    'argv_emulation': False,  # sys.argv 에뮬레이션 비활성화
    'strip': True,           # 바이너리 스트립핑
    'iconfile': ICON_FILE,   # 아이콘 파일
    'plist': {
        'CFBundleName': APP_NAME,
        'CFBundleDisplayName': APP_NAME,
        'CFBundleGetInfoString': f'{APP_NAME} {VERSION}',
        'CFBundleIdentifier': 'com.ksbelphegor.mactimetracker',
        'CFBundleVersion': VERSION,
        'CFBundleShortVersionString': VERSION,
        'NSHighResolutionCapable': True,
        'LSUIElement': False,  # Dock에 표시
        'NSAppleEventsUsageDescription': 'Mac Time Tracker는 다른 앱의 창 정보를 수집하기 위해 Apple Events를 사용합니다.',
        'NSSystemAdministrationUsageDescription': 'Mac Time Tracker는 시스템 정보를 수집하기 위해 시스템 권한이 필요합니다.',
    },
    'packages': [],
    'includes': [
        'PyQt5.QtCore',
        'PyQt5.QtGui', 
        'PyQt5.QtWidgets',
        'Foundation',
        'AppKit',
        'objc',
        'subprocess',
        'json',
        'time',
        'datetime',
        'logging',
        'os',
        'traceback',
    ],
    'excludes': [
        'tkinter',
        'test',
        'tests',
        'unittest',
        'distutils',
        'setuptools',
        'numpy',
        'scipy',
        'matplotlib',
    ],
    'resources': [],
    'frameworks': [],
}

# 데이터 파일 (필요한 경우)
DATA_FILES = []

setup(
    app=[MAIN_SCRIPT],
    name=APP_NAME,
    version=VERSION,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
    install_requires=[
        'PyQt5>=5.15.0',
        'pyobjc-core>=9.0',
        'pyobjc-framework-Cocoa>=9.0',
    ],
)