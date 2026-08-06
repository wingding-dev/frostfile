#!/usr/bin/env bash
# Double-click to launch FrostFile. Runs entirely on this computer.
cd "$(dirname "$0")"
exec ./.venv/bin/python -m identilock
