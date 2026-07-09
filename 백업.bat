@echo off
cd /d "%~dp0"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set STAMP=%%i
set DEST=버전\%STAMP%
mkdir "%DEST%" 2>nul
copy /Y *.py "%DEST%\" >nul 2>nul
copy /Y *.json "%DEST%\" >nul 2>nul
copy /Y *.txt "%DEST%\" >nul 2>nul
copy /Y *.md "%DEST%\" >nul 2>nul
copy /Y *.bat "%DEST%\" >nul 2>nul
echo [완료] 현재 코드 스냅샷을 %DEST% 에 저장했습니다.
echo.
pause
