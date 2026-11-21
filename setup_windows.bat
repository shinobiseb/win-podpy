@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install Python 3 from https://www.python.org/downloads/windows/ and enable the Python launcher.
    exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo FFmpeg was not found on PATH. Install FFmpeg and reopen this terminal. See README.md for setup details.
    exit /b 1
)

where ffprobe >nul 2>nul
if errorlevel 1 (
    echo ffprobe was not found on PATH. Install FFmpeg with ffprobe and reopen this terminal. See README.md for setup details.
    exit /b 1
)

if exist ".venv\Scripts\python.exe" goto install_dependencies
if exist ".venv" (
    echo The existing .venv is not a Windows virtual environment, likely because it was created on Linux, WSL, or macOS.
    echo Remove it with: rmdir /s /q .venv
    echo Then run this setup script again.
    exit /b 1
)

py -3 -m venv .venv
if errorlevel 1 (
    echo Could not create the virtual environment. Check that Python 3 is installed correctly.
    exit /b 1
)

:install_dependencies
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo.
echo Setup complete. Run run_windows.bat to start podpy.
