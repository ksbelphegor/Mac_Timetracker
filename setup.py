from setuptools import setup

APP = ['timer2.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': False,
    'packages': ['PyQt5', 'Cocoa'],
    'includes': ['PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets', 'objc', 'Foundation'],
    'plist': {
        'LSUIElement': False,
    },
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app', 'pyobjc-framework-Cocoa'],
)