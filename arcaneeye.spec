# arcaneeye.spec
import os, sys
from pathlib import Path
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT
from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_submodules

APP_NAME = "ArcaneEye"
ENTRY = "arcaneeye/main.py"   # runs main() via if __name__ == "__main__"

hiddenimports = collect_submodules("arcaneeye")

# Optional icon (.ico) for the EXE (keep .png in resources for runtime)
ico_path = Path("arcaneeye/resources/icon.ico")
icon_arg = str(ico_path) if ico_path.exists() else None

# macOS code signing (single source of truth = the CI secrets). When
# MACOS_SIGN_IDENTITY is set (only in the signed CI path), PyInstaller signs
# every collected binary with a hardened runtime + our entitlements during the
# build. Empty/unset (local dev, unsigned CI) → an ordinary unsigned build.
# Non-darwin always None (codesign is macOS-only). See CLAUDE.md → Release automation.
_is_mac = sys.platform == "darwin"
codesign_identity = (os.environ.get("MACOS_SIGN_IDENTITY") or None) if _is_mac else None
entitlements_file = "packaging/entitlements.mac.plist" if codesign_identity else None
# Universal2 (arm64 + x86_64) macOS binary so the app runs on both Apple Silicon
# and Intel Macs. CI provides a universal2 Python + universal2 wheels. None
# elsewhere (Windows/Linux are single-arch). See CLAUDE.md → Release automation.
target_arch = "universal2" if _is_mac else None

a = Analysis(
    [ENTRY],
    pathex=[],
    binaries=[],
    datas=[],                       # <-- IMPORTANT: leave datas empty here
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=icon_arg,                  # remove this line if you don't have an .ico
    codesign_identity=codesign_identity,   # macOS signing; None elsewhere
    entitlements_file=entitlements_file,
    target_arch=target_arch,               # 'universal2' on macOS, None elsewhere
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    Tree("arcaneeye/resources", prefix="arcaneeye/resources"),  # <-- Tree goes here
    strip=False,
    upx=True,
    name=APP_NAME,
)

# macOS: wrap the collected app in a .app bundle so it can be shipped in a .dmg.
# Platform-guarded, so Windows/Linux builds are unaffected.
if _is_mac:
    from PyInstaller.building.osx import BUNDLE
    icns_path = Path("arcaneeye/resources/icon.icns")
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=str(icns_path) if icns_path.exists() else None,
        bundle_identifier="org.arcanetools.arcaneeye",
    )
