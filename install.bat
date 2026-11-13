@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "SRC=%~dp0dist\TrafikSaveurs.exe"
if not exist "%SRC%" set "SRC=%~dp0TrafikSaveurs.exe"
if not exist "%SRC%" (echo TrafikSaveurs.exe introuvable. Lancez build.bat d'abord. & pause & exit /b 1)
set "DEST=%LOCALAPPDATA%\Programs\TrafikSaveurs"
mkdir "%DEST%" 2>nul
copy /y "%SRC%" "%DEST%\TrafikSaveurs.exe" >nul
if exist app.ico copy /y app.ico "%DEST%\app.ico" >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$w=New-Object -ComObject WScript.Shell;" ^
 "foreach($d in @([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('Programs'))){" ^
 "$s=$w.CreateShortcut((Join-Path $d 'Trafik Saveurs.lnk'));" ^
 "$s.TargetPath='%DEST%\TrafikSaveurs.exe';$s.WorkingDirectory='%DEST%';" ^
 "$s.IconLocation='%DEST%\TrafikSaveurs.exe,0';$s.Save()}"
echo Installe. Raccourci cree sur le Bureau et dans le menu Demarrer.
pause
