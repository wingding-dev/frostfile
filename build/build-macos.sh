#!/bin/sh
# Build the FrostFile binary on a Mac. Run from the repo root:
#   sh build/build-macos.sh
# Prereq: Python 3.10+ (python.org installer or `brew install python`).
set -e

python3 -m venv .venv-build
. .venv-build/bin/activate
python -m pip install --upgrade pip
python -m pip install . pyinstaller
python -m pytest tests -q
pyinstaller build/frostfile.spec --noconfirm

echo
echo "Built: dist/FrostFile"
echo "Next: run it once on this machine, then compute the checksum:"
echo "  shasum -a 256 dist/FrostFile"
