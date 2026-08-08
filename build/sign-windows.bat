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
rem
rem Set CERTUM_THUMBPRINT once (System Properties -> Environment Variables) to
rem your certificate's SHA-1 thumbprint, spaces stripped. Find it in SimplySign
rem Desktop -> Manage certificates -> Details -> Thumbprint.
rem
rem Why thumbprint and not /n "subject name": Certum's own signing manual
rem documents /sha1 <thumbprint>. Subject-name selection appears only in
rem reseller and forum posts, never in Certum's documentation, and it breaks
rem the moment two certificates in the store share a subject.

if "%~1"=="" echo Usage: %0 path\to\FrostFile-windows.zip & exit /b 1
if "%CERTUM_THUMBPRINT%"=="" (
  echo ERROR: set CERTUM_THUMBPRINT to your cert's SHA-1 thumbprint first.
  echo   SimplySign Desktop -^> Manage certificates -^> Details -^> Thumbprint
  echo   then:  setx CERTUM_THUMBPRINT "abc123...".
  exit /b 1
)

set WORK=%TEMP%\frostfile-sign
rmdir /s /q "%WORK%" 2>nul
mkdir "%WORK%" || exit /b 1

tar -xf "%~1" -C "%WORK%" || exit /b 1

rem /tr timestamps it: the signature stays valid after the cert expires, which
rem matters because the Open Source cert is only valid for one year.
signtool sign /sha1 "%CERTUM_THUMBPRINT%" /tr http://time.certum.pl /td sha256 /fd sha256 /v "%WORK%\FrostFile\FrostFile.exe" || goto :error
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
echo SIGNING FAILED — check, in this order:
echo   1. SimplySign Desktop running and the cloud card ACTIVATED (tray icon)?
echo      The session expires after about 2 hours; re-authenticate and retry.
echo   2. CERTUM_THUMBPRINT matches a cert in the store: certutil -user -store My
echo   3. signtool on PATH? Install "Windows SDK Signing Tools".
exit /b 1
