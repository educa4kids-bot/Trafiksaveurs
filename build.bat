@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Trafik Saveurs : build exe ===
if not exist web\index.html (
  echo ERREUR: le dossier web\ ne contient pas index.html. Copiez-y les fichiers du systeme puis relancez.
  pause & exit /b 1
)
if not exist app.ico (
  echo ERREUR: app.ico introuvable.
  pause & exit /b 1
)
py -m pip install --upgrade pip
py -m pip install -r requirements.txt pyinstaller
py -m PyInstaller --noconfirm --clean --onefile --windowed --name TrafikSaveurs --icon app.ico --add-data "web;web" --add-data "app.ico;." --hidden-import expiration app.py
if errorlevel 1 (echo Echec du build. & pause & exit /b 1)
echo.
echo Termine : dist\TrafikSaveurs.exe
echo Lancez install.bat pour creer les raccourcis Bureau + Menu Demarrer.
pause
