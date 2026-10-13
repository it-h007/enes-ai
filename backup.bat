@echo off
REM ENESAI - krijo nje kopje rezerve tani (krijohet edhe automatikisht cdo dite kur faqja eshte e ndezur)
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Hapni fillimisht nis.bat. & pause & exit /b 1)
".venv\Scripts\python.exe" run.py backup
echo Kopjet ruhen te dosja instance\backups - kopjojini edhe ne nje USB ose Google Drive.
pause
