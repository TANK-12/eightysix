@echo off
rem Installs Eighty Six for this user: the game into %LOCALAPPDATA%\Programs\EightySix, with shortcuts
rem in the Start menu and on the desktop. Unzip the whole folder first, then double-click install.bat.
set "DEST=%LOCALAPPDATA%\Programs\EightySix"
if not exist "%DEST%" mkdir "%DEST%"
copy /Y "%~dp0eightysix.exe" "%DEST%\eightysix.exe" >nul || goto :fail
powershell -NoProfile -ExecutionPolicy Bypass -Command "Unblock-File -Path %DEST%\eightysix.exe; $s = New-Object -ComObject WScript.Shell; foreach ($d in @([Environment]::GetFolderPath(Programs), [Environment]::GetFolderPath(Desktop))) { $l = $s.CreateShortcut((Join-Path $d Eighty Six.lnk)); $l.TargetPath = %DEST%\eightysix.exe; $l.WorkingDirectory = %DEST%; $l.Save() }"
echo Installed to %DEST%
echo Start it from the Start menu or the desktop shortcut "Eighty Six".
pause
exit /b 0
:fail
echo Could not copy the game. Unzip the whole zip first (right-click it, Extract All), then run install.bat from that folder.
pause
exit /b 1
