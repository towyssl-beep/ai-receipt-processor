@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" goto nosetup
call ".venv\Scripts\activate.bat"
echo 영수증 처리 중...
python run.py %*
goto end
:nosetup
echo.
echo [오류] 먼저 setup.bat 을 실행하세요.
:end
echo.
pause
