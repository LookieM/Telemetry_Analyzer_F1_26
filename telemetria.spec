# PyInstaller spec for Telemetria.exe (onedir, windowed). Build with build_exe.bat, not by hand.
# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hiddenimports = (
    collect_submodules("uvicorn")  # protocols / loops are picked at runtime by name
    + collect_submodules("websockets")  # /ws/live
)  # our own packages have no dynamic imports: static analysis finds them

a = Analysis(
    ["desktop.py"],
    pathex=["."],
    binaries=[],
    datas=[("frontend/dist", "frontend/dist")],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # The old Streamlit UI is not part of the desktop app (ticket desktop-app/10 removes it for good).
    excludes=["streamlit", "plotly", "gui_app", "telemetry.ui", "tkinter", "matplotlib", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Telemetria",
    icon="desktop/telemetria.ico",
    console=False,
    debug=False,
    strip=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Telemetria")
