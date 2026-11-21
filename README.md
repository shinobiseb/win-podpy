# PodPy

A local multicamera editing tool that creates activity-driven cuts from two videos. It can analyze separate audio tracks or use the audio embedded in each video.

## Desktop app

Launch the interface with:

```bash
python src/gui.py
```

Choose the audio source, then select an output workflow:

- **Render MP4** — analyze, cut, and encode the finished video.
- **Create Resolve XML only** — analyze the audio and write a Final Cut Pro XML timeline that references both original camera files; no MP4 render.
- **Both MP4 and Resolve XML** — produce both outputs.

The XML contains both camera assets and the cut segments in sequence. Import it in DaVinci Resolve using **File → Import Timeline → Import AAF, EDL, XML…** and relink the original video files if prompted. Save the imported timeline as a `.drp` project in Resolve.

PodPy defaults to whichever input video is longer during detected silence; equal-length clips default to Video 1. Camera 1 remains the synchronization reference and defines the output timeline duration.

## Requirements

- Python 3.9+
- FFmpeg and ffprobe installed and available on your PATH
- Dependencies installed in a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Command-line mode

Render an MP4 with configured defaults:

```bash
python src/main.py --videos-only --output-mode render --output Synced_video.mp4
```

Create only a Resolve XML (no MP4 render):

```bash
python src/main.py --videos-only --output-mode resolve \
  --video1 path/to/camera1.mp4 --video2 path/to/camera2.mp4 \
  --resolve-xml podpy_timeline.fcpxml
```

Create both outputs:

```bash
python src/main.py --videos-only --output-mode both \
  --video1 path/to/camera1.mp4 --video2 path/to/camera2.mp4 \
  --output Synced_video.mp4 --resolve-xml podpy_timeline.fcpxml
```

Use `--audio1` and `--audio2` instead of `--videos-only` to provide separate audio. Both videos need audio with at least 30 seconds of shared material for reliable sync estimation.

## Notes

The timeline XML uses both original camera files as source assets and references the cut segments in a single project timeline. This preserves the two-camera nature of the edit better than an EDL and is the appropriate import to use in Resolve for a native project workflow.

FFmpeg/ffprobe are still used for audio extraction and analysis in timeline-only mode, but no rendered video file is encoded.
