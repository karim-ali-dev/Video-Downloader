# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['video_downloader.py'],
    pathex=['.build_deps'],
    binaries=[('C:/Users/karim/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/DLLs/_tkinter.pyd', '.'), ('_internal/tcl86t.dll', '.'), ('_internal/tk86t.dll', '.')],
    datas=[('tools', 'tools'), ('app_icon.ico', '.'), ('app_icon.png', '.'), ('C:/Users/karim/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/Lib/tkinter', 'tkinter'), ('_internal/_tcl_data', '_tcl_data'), ('_internal/_tk_data', '_tk_data')],
    hiddenimports=['tkinter', '_tkinter'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'pandas', 'cryptography', 'lxml', 'docx', 'pptx', 'openpyxl',
              'xlsxwriter', 'reportlab', 'pdfminer', 'pdfplumber', 'pypdf', 'pydantic',
              'pydantic_core', 'pdf2image', 'pypdfium2', 'scipy', 'matplotlib', 'Crypto',
              'Cryptodome', 'tensorflow', 'torch', 'sklearn', 'cv2'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VideoDownloader_Final',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='app_icon.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VideoDownloader_Final',
)
