@echo off
setlocal
cd /d "%~dp0"
python -m pip install --user pygame-ce pyinstaller
python -m PyInstaller --onefile --noconsole --name=dungeon_rogue dungeon_rogue.py
if exist dist\dungeon_rogue.exe copy /Y dist\dungeon_rogue.exe dungeon_rogue.exe
if errorlevel 1 exit /b %errorlevel%

echo Build complete. Executable is at dungeon_rogue.exe
