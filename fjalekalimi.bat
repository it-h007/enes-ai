@echo off
REM ENESAI - rivendos fjalekalimin e nje llogarie (vetem ne kompjuterin e serverit)
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Hapni fillimisht nis.bat. & pause & exit /b 1)
".venv\Scripts\python.exe" run.py reset-password
pause
