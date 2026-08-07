"""PyInstaller entry point.

frostfile/__main__.py can't be the bundle's entry script — PyInstaller runs
it as a top-level module, where its relative import has no parent package.

In a windowed (console=False) Windows build, sys.stdout and sys.stderr are
None, and uvicorn's logging setup calls .isatty() on them — an immediate
crash at launch. Give the process real (null) streams before anything else
imports. Nothing sensitive is lost: server logs stay on this machine either
way, and the app's own UI is the browser window, not the console.
"""

import io
import os
import sys

if sys.stdout is None:
    sys.stdout = io.TextIOWrapper(open(os.devnull, "wb"), encoding="utf-8")
if sys.stderr is None:
    sys.stderr = io.TextIOWrapper(open(os.devnull, "wb"), encoding="utf-8")

from frostfile.cli import main

if __name__ == "__main__":
    sys.exit(main())
