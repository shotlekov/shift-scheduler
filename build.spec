# PyInstaller spec file for Shift Scheduler
# Builds a standalone executable for Windows and Linux

block_cipher = None

a = Analysis(
    ['src/app.py'],
    pathex=['.', 'src', 'shiftcore'],
    binaries=[],
    datas=[
        ('data', 'data'),
    ],
    hiddenimports=[
        'shiftcore',
        'shiftcore.models',
        'shiftcore.constraints',
        'shiftcore.rotation',
        'shiftcore.fairness',
        'shiftcore.scheduler',
        'shiftcore.swaps',
        'shiftcore.notifications',
        'shiftcore.storage',
        'shiftcore.exceptions',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='shift-scheduler',
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
    icon='src/assets/icon.ico' if __import__('os').path.exists('src/assets/icon.ico') else None,
)
