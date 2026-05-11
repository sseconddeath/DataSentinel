# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main_qt.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('icon.ico', '.'),
        ('fonts', 'fonts'),
    ],
    hiddenimports=[
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtSvg',
        'cryptography',
        'cryptography.fernet',
        'requests',
        'winotify',
        'PIL',
        'pystray',
        'sqlite3',
        'reportlab',
        'reportlab.lib',
        'reportlab.platypus',
        'reportlab.pdfbase',
        'reportlab.pdfbase.ttfonts',
        'matplotlib',
        'groq',
        'trafilatura',
        'justext',
        'htmldate',
        'lxml',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'customtkinter', 'unittest'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DataSentinel',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DataSentinel',
)
