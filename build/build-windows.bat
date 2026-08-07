@echo off
rem Build FrostFile.exe on a Windows machine.
rem Prereqs: Python 3.10+ from python.org (check "Add to PATH" during install).
rem Run this from the repo root:  build\build-windows.bat

python -m venv .venv-build || goto :error
call .venv-build\Scripts\activate.bat
python -m pip install --upgrade pip || goto :error
python -m pip install . pyinstaller || goto :error
python -m pytest tests -q || goto :error
pyinstaller build\frostfile.spec --noconfirm || goto :error

echo.
echo Built: dist\FrostFile.exe
echo Next: run it once on this machine, then compute the checksum:
echo   certutil -hashfile dist\FrostFile.exe SHA256
goto :eof

:error
echo BUILD FAILED (see output above).
exit /b 1
