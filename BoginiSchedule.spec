# Run on Windows to produce a Windows EXE.
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/fonts', 'assets/fonts')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtPdf'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='BoginiSchedule', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False,
)
