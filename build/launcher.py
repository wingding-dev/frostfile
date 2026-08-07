"""PyInstaller entry point.

frostfile/__main__.py can't be the bundle's entry script — PyInstaller runs
it as a top-level module, where its relative import has no parent package.
"""

import sys

from frostfile.cli import main

if __name__ == "__main__":
    sys.exit(main())
