@echo off
REM ENESAI SUPER MARKET - nisja me nje klik (Windows)
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
if not exist ".venv\Scripts\python.exe" (
  echo Po krijohet mjedisi Python...
  %PY% -m venv .venv || (echo Python 3.11+ nuk u gjet. Instalojeni nga python.org & pause & exit /b 1)
)
echo Po instalohen paketat...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || (echo Instalimi deshtoi. & pause & exit /b 1)
if not exist ".env" copy ".env.example" ".env" >nul
".venv\Scripts\python.exe" -c "from enesai import create_app;from enesai.services.auth import owner_exists;app=create_app();ctx=app.app_context();ctx.push();import sys;sys.exit(0 if owner_exists() else 3)"
if errorlevel 3 (
  echo.
  echo Krijoni llogarine e PRONARIT (vetem nje here^):
  ".venv\Scripts\python.exe" run.py create-owner
)
echo.
echo Faqja: http://127.0.0.1:5000   Paneli: http://127.0.0.1:5000/paneli
start "" http://127.0.0.1:5000
".venv\Scripts\python.exe" run.py
pause
