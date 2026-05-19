"""
setup.py for Mac Time Tracker
macOS 앱 번들 생성을 위한 설정 파일
"""
from setuptools import setup
import py2app

# 앱 정보
APP_NAME = 'Mac Time Tracker'
MAIN_SCRIPT = 'src/main.py'
VERSION = '1.2.0'

# py2app 옵션
OPTIONS = {
    'argv_emulation': False,
    'strip': True,
    'iconfile': None,
    'plist': {
        'CFBundleName': APP_NAME,
        'CFBundleDisplayName': APP_NAME,
        'CFBundleGetInfoString': f'{APP_NAME} {VERSION}',
        'CFBundleIdentifier': 'com.ksbelphegor.mactimetracker',
        'CFBundleVersion': VERSION,
        'CFBundleShortVersionString': VERSION,
        'NSHighResolutionCapable': True,
        'LSUIElement': True,  # Dock에 표시 안 함 (순수 상태바 앱)
        'NSAppleEventsUsageDescription': 'Mac Time Tracker는 다른 앱의 사용 시간을 추적하기 위해 Apple Events를 사용합니다.',
        'NSSystemAdministrationUsageDescription': 'Mac Time Tracker는 시스템 정보를 수집하기 위해 시스템 권한이 필요합니다.',
    },
    'packages': [],
    'includes': [
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
        'threading',
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
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
    ],
    'resources': [],
    'frameworks': [],
}

setup(
    app=[MAIN_SCRIPT],
    name=APP_NAME,
    version=VERSION,
    data_files=[],
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
