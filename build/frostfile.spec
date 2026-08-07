# PyInstaller spec — builds a single-file FrostFile executable.
#
# Must be run ON the OS you are building FOR (PyInstaller cannot cross-
# compile): build-windows.bat on Windows, build-macos.sh on a Mac, or let
# .github/workflows/build.yml do both. Run from the repo root:
#
#   pyinstaller build/frostfile.spec --noconfirm
#
# The app finds its templates/static relative to frostfile/__init__.py, so
# they must land inside a "frostfile/" folder in the bundle — keep the datas
# tuples' second elements exactly as written.

from pathlib import Path

repo = Path(SPECPATH).parent

datas = [
    (str(repo / "frostfile" / "templates"), "frostfile/templates"),
    (str(repo / "frostfile" / "static"), "frostfile/static"),
]

a = Analysis(
    [str(repo / "build" / "launcher.py")],
    pathex=[str(repo)],
    datas=datas,
    hiddenimports=[
        # uvicorn loads these by string name, so static analysis misses them
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
    ],
    excludes=[
        # dev/test-only; keeps the bundle honest as well as small — the
        # shipped app must not even CONTAIN an HTTP client
        "httpx",
        "pytest",
        "tkinter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

# One-DIR, not one-file: a one-file exe self-extracts to temp at launch —
# the single biggest antivirus false-positive trigger for unsigned software.
# The folder ships zipped; users unzip once and double-click FrostFile.exe.
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="FrostFile",
    icon=str(repo / "frostfile" / "static" / "frostfile-icon.ico")
    if (repo / "frostfile" / "static" / "frostfile-icon.ico").exists()
    else None,
    version=str(repo / "build" / "version_info.txt"),
    console=False,  # no terminal window; the app opens its own window/browser
    upx=False,  # UPX-packed exes trip antivirus heuristics — not worth the MB
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="FrostFile",
    upx=False,
)

# On a Mac, wrap it into a double-clickable .app bundle.
import sys

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="FrostFile.app",
        icon=None,
        bundle_identifier="org.frostfile.app",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": "1.0.0",
        },
    )
