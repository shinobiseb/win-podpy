# Audio-Driven Multicam Switcher

## Goal

Build a local tool that takes two videos (each synced to its corresponding audio source) and two audio files that determine which video should be shown. When audio source 1 is active, show video 1; when source 2 is active, show video 2. Render a finished video, with the option to add an editor-friendly timeline later.

## Recommended approach

- **Python** for the application and switching logic.
- **FFmpeg and ffprobe** for inspecting, processing, and rendering media.
- Keep audio analysis, switching decisions, and rendering as separate parts so they can be changed independently.
- Process media locally for privacy and to avoid browser limits with long videos.

## Activity detection

There are two possible meanings of “audio activity”:

- **Any sound activity:** detect the audio level in short windows. This is simpler, but background noise can trigger a camera switch.
- **Speech activity:** use a voice activity detector (VAD). This is more appropriate for interviews and conversations, but may miss non-speech sounds.

The current prototype uses audio-level detection. It ignores brief activity, smooths short gaps, holds the current camera during silence, and selects the camera whose activity starts when both sources are active.

## Workflow

1. Validate the four input files and inspect streams with `ffprobe`.
2. Extract short analysis WAV files and estimate synchronization.
3. Build camera selections from audio activity.
4. Render with FFmpeg and save the cut list as JSON.
5. Review the output and adjust switching thresholds as needed.

## Setup

See [README.md](README.md) for Windows, macOS, and Linux setup instructions. On Windows, use `setup_windows.bat` and `run_windows.bat`; on all platforms, FFmpeg and ffprobe must be installed and available on `PATH`.

Inputs are expected in `src/files/`:

- `pov_seb.mp4`
- `pov_gus.mp4`
- `pod1_seb.mp3`
- `pod1_gus.mp3`

Input media is deliberately not stored in the repository. Output files are written in the repository root.
