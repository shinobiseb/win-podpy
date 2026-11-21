# Audio-Driven Multicam Switcher

## Goal

Build a local tool that takes:

- Two video files, each synced to its corresponding audio source
- Two audio files that determine which video should be shown

When audio source 1 is active, show video 1. When audio source 2 is active, show video 2. Render a finished video, with the option to add an editor-friendly timeline later.

## Recommended approach

- **Python** for the application and switching logic.
- **FFmpeg and ffprobe** for inspecting, processing, and rendering media.
- Start with a **command-line prototype**. Add a desktop interface only after the workflow works.
- Keep audio analysis, switching decisions, and rendering as separate parts so they can be changed independently.
- Process media locally for privacy and to avoid browser limits with long videos.

## Activity detection

There are two possible meanings of “audio activity”:

- **Any sound activity:** detect the audio level in short windows. This is simpler, but background noise can trigger a camera switch.
- **Speech activity:** use a voice activity detector (VAD). This is more appropriate for interviews and conversations, but may miss non-speech sounds.

Start with simple audio-level detection or VAD, then test on real recordings. Add switching rules to avoid choppy results:

- Ignore very brief activity.
- Hold shots for a minimum duration.
- Smooth short gaps in activity.
- Define what to show when neither source is active.
- Define what to show when both sources are active.

## Production workflow

1. **Validate the inputs**
   - Check that all four files exist and can be read.
   - Use `ffprobe` to inspect durations, frame rates, audio sample rates, and stream layouts.
   - Confirm each video is synced with its corresponding audio. Record any sync offsets.

2. **Analyze the audio**
   - Divide each audio track into short time windows.
   - Mark which source is active in each window.
   - Store the result as timed activity intervals.

3. **Build the switching timeline**
   - Convert activity intervals into camera choices and cut timestamps.
   - Apply the minimum-shot, gap-smoothing, silence, and overlap rules.
   - Keep this timeline separate from the video rendering code.

4. **Render the video**
   - Use FFmpeg to select the appropriate video at each cut.
   - Decide whether the final video should keep one audio track, mix both tracks, or use another audio mix.
   - Check output duration, sync, transitions, and sound before considering the render complete.

5. **Review and iterate**
   - Test first on short clips with clear activity.
   - Then test on longer recordings with pauses, interruptions, background noise, and overlapping speech.
   - Adjust the activity threshold and switching rules based on the results.

## Setup

FFmpeg is already installed on this Mac; `ffmpeg -version` succeeded. The `ffprobe` tool is normally installed with FFmpeg.

A Python virtual environment is recommended so project dependencies stay separate from system Python:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

For a basic audio-analysis prototype:

```bash
pip install numpy soundfile
```

The current shell showed Python 3.9.4. If a library requires a newer version, install a newer Python and recreate the virtual environment with it.

## First milestone

Create a small command-line prototype that:

1. Accepts two videos and two audio files.
2. Checks their durations and stream information.
3. Detects activity in the audio tracks.
4. Prints the resulting camera choices and cut timestamps.

Once those timestamps look right, add FFmpeg rendering. Avoid building a GUI or a full editing engine until this basic workflow is reliable.

## Open decisions

- Should “activity” mean any sound or speech only?
- What should happen during silence?
- What should happen when both audio sources are active?
- Should brief turns trigger an immediate cut, or should the current shot be held?
- Should the final audio be mixed from both sources, or should one source be preferred?
- Is a finished video enough, or should the tool eventually export an editable timeline?