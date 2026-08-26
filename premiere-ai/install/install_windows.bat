@echo off
chcp 65001 >nul
setlocal
echo ============================================
echo   تثبيت لوحة مساعد بريمير الذكي (ويندوز)
echo ============================================

rem 1) السماح بتشغيل الإضافات غير الموقّعة (PlayerDebugMode)
for %%V in (9 10 11 12) do (
    reg add "HKCU\Software\Adobe\CSXS.%%V" /v PlayerDebugMode /t REG_SZ /d 1 /f >nul 2>&1
)
echo [1/2] تم تفعيل PlayerDebugMode لإصدارات CEP 9-12

rem 2) نسخ اللوحة إلى مجلد إضافات CEP
set "SRC=%~dp0..\extension"
set "DST=%APPDATA%\Adobe\CEP\extensions\com.alamani.premiereai"

if not exist "%APPDATA%\Adobe\CEP\extensions" mkdir "%APPDATA%\Adobe\CEP\extensions"
if exist "%DST%" rmdir /s /q "%DST%"
mkdir "%DST%"
xcopy "%SRC%\*" "%DST%\" /E /I /Y >nul

echo [2/2] تم نسخ اللوحة إلى:
echo      %DST%
echo.
echo خلص التثبيت. الخطوات الباقية:
echo   1) شغّل السيرفر:  premiere-ai\install\start_server.bat
echo   2) افتح بريمير:   Window ^> Extensions ^> مساعد الذكاء الاصطناعي
echo.
pause
