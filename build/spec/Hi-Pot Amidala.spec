# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['..\\_amidala_staging\\main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['tkinter', 'tkinter.ttk', 'tkinter.messagebox', 'tkinter.filedialog', 'serial', 'serial.tools.list_ports', 'serial.tools.list_ports_windows', 'config', 'gui', 'admin_panel', 'test_screen', 'hipot_device', 'interlock', 'logger', 'settings_manager', 'hwid_map'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['C:\\Users\\kacper.urbanowicz\\PycharmProjects\\hipot_amidala\\build\\_amidala_staging\\runtime_hook_amidala.py'],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Hi-Pot Amidala',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='C:\\Users\\kacper.urbanowicz\\PycharmProjects\\hipot_amidala\\build\\_amidala_staging\\version_info.txt',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Hi-Pot Amidala',
)
