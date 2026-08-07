@echo off
rem Sign the Windows build with the Certum Open Source certificate, then
rem re-zip. Run on a Windows PC where SimplySign Desktop is INSTALLED,
rem RUNNING, and connected (cloud smart card active — check the tray icon).
rem
rem Usage:  build\sign-windows.bat path\to\FrostFile-windows.zip
rem Produces FrostFile-windows-signed.zip next to the input, plus its hash.
rem
rem signtool comes with the Windows SDK ("App Installer"/SDK signing tools);
rem if not found, install "Windows SDK Signing Tools" from the SDK installer.

if "%~1"=="" echo Usage: %0 path\to\FrostFile-windows.zip & exit /b 1

set WORK=%TEMP%\frostfile-sign
rmdir /s /q "%WORK%" 2>nul
mkdir "%WORK%" || exit /b 1

tar -xf "%~1" -C "%WORK%" || exit /b 1

rem /n picks the Certum cert by subject name — adjust if your cert's CN
rem differs (Certum OSS certs are issued as "Open Source Developer, NAME").
rem /tr timestamps it: the signature stays valid after the cert expires.
signtool sign /n "Open Source Developer" /tr http://time.certum.pl /td sha256 /fd sha256 "%WORK%\FrostFile\FrostFile.exe" || goto :error
signtool verify /pa "%WORK%\FrostFile\FrostFile.exe" || goto :error

set OUT=%~dp1FrostFile-windows-signed.zip
del "%OUT%" 2>nul
tar -a -cf "%OUT%" -C "%WORK%" FrostFile || goto :error

echo.
echo Signed and packed: %OUT%
certutil -hashfile "%OUT%" SHA256
echo Rename to FrostFile-windows.zip, upload to R2, update SHA256SUMS.txt.
goto :eof

:error
echo SIGNING FAILED — is SimplySign Desktop running and the card activated?
exit /b 1
