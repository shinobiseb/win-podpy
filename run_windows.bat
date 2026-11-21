@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Python environment not found. Run setup_windows.bat first.
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

".venv\Scripts\python.exe" .\src\main.py
exit /b %errorlevel%
