@echo off
REM ENESAI SUPER MARKET - nisja me nje klik (Windows)
chcp 65001 >nul
cd /d "%~dp0"
if not exist "requirements.txt" goto :mungon
if not exist "run.py" goto :mungon
if not exist "enesai\__init__.py" goto :mungon
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
if not exist ".venv\Scripts\python.exe" (
  echo Po krijohet mjedisi Python...
  %PY% -m venv .venv || (echo Python 3.11+ nuk u gjet. Instalojeni nga python.org & pause & exit /b 1)
)
echo Po instalohen paketat...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || (echo Instalimi deshtoi. & pause & exit /b 1)
if not exist ".env" copy ".env.example" ".env" >nul
".venv\Scripts\python.exe" -c "from enesai import create_app;from enesai.services.auth import owner_exists;app=create_app();ctx=app.app_context();ctx.push();import sys;sys.exit(0 if owner_exists() else 3)"
if not errorlevel 3 goto :nisja
echo.
echo Krijoni llogarine e PRONARIT (vetem nje here^). Me kete emer dhe fjalekalim hyni te /paneli.
echo Fjalekalimi nuk shfaqet nderkohe qe shkruani - kjo eshte normale.
:pronari
".venv\Scripts\python.exe" run.py create-owner
if errorlevel 1 (echo Provoni perseri. & goto :pronari)
:nisja
echo.
echo Faqja: http://127.0.0.1:5000
".venv\Scripts\python.exe" run.py admin-url
start "" http://127.0.0.1:5000
".venv\Scripts\python.exe" run.py
pause
exit /b 0

:mungon
echo.
echo GABIM: skedaret e projektit nuk jane te plota ne kete dosje:
echo   %CD%
echo.
echo Ka shume mundesi qe nis.bat u hap direkt nga brenda ZIP-it.
echo Zgjidhja:
echo   1. Klikoni me te djathten mbi ENESAI_FLASK.zip ^> "Extract All..." (Shpaketo te gjitha).
echo   2. Hapni dosjen e shpaketuar "enesai-flask".
echo   3. Klikoni dy here nis.bat aty (prane tij duhet te jene requirements.txt, run.py dhe dosja enesai).
echo.
pause
exit /b 1
