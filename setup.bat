@echo off
cd /d "%~dp0"
echo ============================================
echo   AI 영수증 처리 - 최초 설치 (한 번만)
echo ============================================
where python >nul 2>nul
if errorlevel 1 goto nopython
echo.
echo 가상환경(.venv) 만드는 중...
python -m venv .venv
call ".venv\Scripts\activate.bat"
echo 패키지 설치 중... (몇 분 걸릴 수 있어요)
python -m pip install --upgrade pip
pip install -r requirements.txt
echo.
echo [완료] 설치가 끝났습니다. 이제 run.bat 을 더블클릭하세요.
goto end
:nopython
echo.
echo [오류] Python 이 설치되어 있지 않습니다.
echo python.org 에서 설치하고(설치 시 "Add Python to PATH" 체크) 다시 실행하세요.
:end
echo.
pause
