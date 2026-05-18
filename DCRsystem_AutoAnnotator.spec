# -*- mode: python ; coding: utf-8 -*-
"""DCRsystem 自動アノテーションツール の PyInstaller ビルド定義。

ビルド: uv run pyinstaller DCRsystem_AutoAnnotator.spec --noconfirm
出力  : dist/DCRsystem_AutoAnnotator/DCRsystem_AutoAnnotator.exe
"""

from PyInstaller.utils.hooks import collect_all, copy_metadata

datas = []
binaries = []
hiddenimports = []

# ultralytics 一式（cfg/*.yaml などのデータ・サブモジュールを収集）
_d, _b, _h = collect_all("ultralytics")
datas += _d
binaries += _b
hiddenimports += _h

# importlib.metadata でバージョン参照されるパッケージのメタデータを同梱
for _pkg in (
    "ultralytics",
    "torch",
    "torchvision",
    "numpy",
    "pillow",
    "opencv-python",
    "pyyaml",
    "tqdm",
    "matplotlib",
    "psutil",
    "polars",
    "requests",
    "scipy",
    "pandas",
):
    try:
        datas += copy_metadata(_pkg)
    except Exception:
        pass

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
    name="DCRsystem_AutoAnnotator",
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="DCRsystem_AutoAnnotator",
)
