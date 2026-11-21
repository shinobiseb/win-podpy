# podpy — Audio-Driven Multicam Switcher

A local Python tool that uses audio activity to switch between two camera videos and renders an MP4 with FFmpeg. Media is processed locally and is not uploaded.

## Windows quick start

### 1. Install Python and FFmpeg

- Install Python 3 from [python.org](https://www.python.org/downloads/windows/). Enable the Python launcher (`py`) in the installer.
- Install FFmpeg with `ffmpeg` and `ffprobe`, and add them to `PATH`. With `winget`, you can try:

  ```powershell
  winget install --id Gyan.FFmpeg.Shared --exact
  ```

  Open a new terminal after installation and verify both commands work:

  ```powershell
  ffmpeg -version
  ffprobe -version
  ```

### 2. Add your input media

The media files are not included in this repository. In the project folder, create `src\files` and put these files there:

| File | Purpose |
| --- | --- |
| `pov_seb.mp4` | Camera 1 video (must contain its reference audio) |
| `pov_gus.mp4` | Camera 2 video (must contain audio used for synchronization) |
| `pod1_seb.mp3` | Camera 1 audio track |
| `pod1_gus.mp3` | Camera 2 audio track |

PowerShell command:

```powershell
New-Item -ItemType Directory -Force src\files
```

You can change the expected filenames in `src/main.py`. Do not commit private media files; media extensions in `src/files` are ignored by Git.

### 3. Set up Python

Double-click `setup_windows.bat`, or run it from PowerShell in the project directory:

```powershell
.\setup_windows.bat
```

The script creates a Windows-native `.venv` and installs the project dependencies into it. If `.venv` already exists from Linux, WSL, or macOS, delete it first in PowerShell:

```powershell
Remove-Item -Recurse -Force .venv
.\setup_windows.bat
```

The app does not require virtual-environment activation, so PowerShell execution policy is not an issue.

### 4. Run podpy

Double-click `run_windows.bat`, or run:

```powershell
.\run_windows.bat
```

The rendered video (`Synced_video.mp4`) and camera-cut JSON (`test_synced_merged_cuts.json`) are saved in the project directory. Rendering can take a while for long videos.

### Use the commands directly

Both commands explicitly use the project environment, rather than whichever `python` happens to be first on `PATH` (for example MSYS2 Python):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\src\main.py
```

The script resolves media and output paths relative to its own location, so it can also be started from a different working directory.

## macOS and Linux

Install Python 3 and FFmpeg (including ffprobe), then run these commands from the project directory:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python src/main.py
```

Create a separate virtual environment on each operating system; do not share `.venv` across Windows, WSL, macOS, or Linux.

## What the program does

1. Uses FFmpeg/ffprobe to inspect inputs and extract temporary analysis audio.
2. Estimates audio synchronization against the first video's embedded audio.
3. Detects audio activity and creates a camera switching timeline.
4. Renders a combined video and audio output.

The project currently expects the four fixed filenames listed above and requires at least 30 seconds of overlapping audio for sync analysis. If `ffmpeg` or `ffprobe` is missing, the program prints a setup hint.
