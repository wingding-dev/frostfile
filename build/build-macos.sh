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

# ditto, not zip: plain zip and Finder's Compress mangle symlinks and extended
# attributes, corrupting the .app's _CodeSignature. On Apple Silicon an invalid
# signature is worse than none — the app becomes "damaged" with no override
# available at all. This is Apple's own prescribed command.
cd dist
ditto -c -k --keepParent FrostFile.app FrostFile-mac.zip

# Verify the ROUND TRIP. v1.0.0 shipped broken because the bundle on disk was
# fine and only the zip was corrupt, so checking FrostFile.app proves nothing.
rm -rf _verify && mkdir _verify
ditto -x -k FrostFile-mac.zip _verify
links=$(find _verify/FrostFile.app -type l | wc -l | tr -d ' ')
if [ "$links" -eq 0 ]; then
    echo "FAILED: no symlinks survived packaging — the app would appear 'damaged'."
    exit 1
fi
codesign --verify --deep --strict --verbose=2 _verify/FrostFile.app
rm -rf _verify

echo
echo "Built and verified: dist/FrostFile-mac.zip ($links symlinks intact)"
echo "Next: run it once on this machine, then compute the checksum:"
echo "  shasum -a 256 FrostFile-mac.zip"
