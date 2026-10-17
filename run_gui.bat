@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python not found. Install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

python -c "import numpy, PIL, lz4, zstandard, tkinter" >nul 2>nul
if errorlevel 1 (
    echo Missing dependencies.
    echo Run: pip install -r requirements.txt
    pause
    exit /b 1
)

if not exist "%~dp0assets\app_icon.ico" (
    echo Generating icon assets...
    python "%~dp0tools\make_icons.py"
)

where pythonw >nul 2>nul
if errorlevel 1 (
    python "%~dp0hsj2psd_gui.py" %*
) else (
    start "" pythonw "%~dp0hsj2psd_gui.py" %*
)
