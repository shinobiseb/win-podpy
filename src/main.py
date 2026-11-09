import json
import math
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np


# Resolve paths from this file so the app works regardless of the current directory.
ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "src" / "files"
VIDEO = FILES / "pov_seb.mp4"
VIDEO2 = FILES / "pov_gus.mp4"
AUDIO1 = FILES / "pod1_seb.mp3"
AUDIO2 = FILES / "pod1_gus.mp3"
OUTPUT = ROOT / "Synced_video.mp4"
CUTS_JSON = ROOT / "test_synced_merged_cuts.json"

# Sync analysis
ANALYSIS_SECONDS = 300
ANALYSIS_SAMPLE_RATE = 8000
ENVELOPE_RATE = 100
MAX_SYNC_OFFSET_SECONDS = 120
MIN_OVERLAP_SECONDS = 30
MIN_CORRELATION = 0.20

# Output
OUTPUT_AUDIO_RATE = 48000
OUTPUT_FPS = 30

# Activity-driven camera selection
ACTIVITY_FLOOR_DBFS = -42.0
ACTIVITY_ABOVE_NOISE_DB = 10.0
MIN_ACTIVITY_SECONDS = 0.25
MAX_SILENCE_GAP_SECONDS = 0.20


def run(args):
    subprocess.run(args, check=True)


def require_media_tools():
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        names = " and ".join(missing)
        raise SystemExit(
            f"Required media tool(s) not found on PATH: {names}. "
            "Install FFmpeg (including ffprobe), add it to PATH, then reopen your terminal. "
            "See README.md for setup instructions."
        )


def probe_duration(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def probe_video_size(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    streams = json.loads(result.stdout)["streams"]
    if not streams:
        raise ValueError(f"No video stream found in {path}")

    stream = streams[0]
    width = int(stream["width"]) // 2 * 2
    height = int(stream["height"]) // 2 * 2
    return width, height


def extract_analysis_wav(source, output):
    run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(source),
        "-map", "0:a:0",
        "-t", str(ANALYSIS_SECONDS),
        "-ac", "1",
        "-ar", str(ANALYSIS_SAMPLE_RATE),
        "-c:a", "pcm_s16le",
        str(output),
    ])


def read_pcm16_wav(path):
    with wave.open(str(path), "rb") as wav:
        if wav.getsampwidth() != 2 or wav.getnchannels() != 1:
            raise ValueError(f"{path} must be mono 16-bit PCM")

        rate = wav.getframerate()
        samples = np.frombuffer(
            wav.readframes(wav.getnframes()),
            dtype="<i2",
        ).astype(np.float32) / 32768.0

    return rate, samples


def rms_envelope(path):
    rate, samples = read_pcm16_wav(path)
    frame_size = rate // ENVELOPE_RATE

    if frame_size <= 0:
        raise ValueError(f"Invalid analysis rate in {path}")

    count = len(samples) // frame_size
    if count < MIN_OVERLAP_SECONDS * ENVELOPE_RATE:
        raise ValueError(
            f"Not enough audio to estimate sync in {path}; "
            f"need at least {MIN_OVERLAP_SECONDS} seconds"
        )

    frames = samples[:count * frame_size].reshape(count, frame_size)
    envelope = np.sqrt(np.mean(frames ** 2, axis=1))

    std = float(envelope.std())
    if std < 1e-8:
        raise ValueError(f"Audio is silent or too constant to sync: {path}")

    return (envelope - envelope.mean()) / std


def estimate_shift(reference_wav, target_wav):
    """
    Return (shift_seconds, correlation).

    Positive shift means matching content occurs later in the target.
    Negative shift means matching content occurs earlier in the target.
    """
    ref = rms_envelope(reference_wav)
    target = rms_envelope(target_wav)

    n_ref = len(ref)
    n_target = len(target)
    full_len = n_ref + n_target - 1
    fft_size = 1 << (full_len - 1).bit_length()

    corr_sum = np.fft.irfft(
        np.fft.rfft(target, fft_size)
        * np.fft.rfft(ref[::-1], fft_size),
        fft_size,
    )[:full_len]
    lags = np.arange(full_len) - (n_ref - 1)

    prefix_ref = np.concatenate(([0.0], np.cumsum(ref, dtype=np.float64)))
    prefix_target = np.concatenate(
        ([0.0], np.cumsum(target, dtype=np.float64))
    )
    prefix_ref_sq = np.concatenate(
        ([0.0], np.cumsum(ref ** 2, dtype=np.float64))
    )
    prefix_target_sq = np.concatenate(
        ([0.0], np.cumsum(target ** 2, dtype=np.float64))
    )

    ref_start = np.maximum(0, -lags)
    ref_end = np.minimum(n_ref, n_target - lags)
    overlap = ref_end - ref_start

    target_start = ref_start + lags
    target_end = ref_end + lags

    sum_ref = prefix_ref[ref_end] - prefix_ref[ref_start]
    sum_target = prefix_target[target_end] - prefix_target[target_start]
    sum_ref_sq = prefix_ref_sq[ref_end] - prefix_ref_sq[ref_start]
    sum_target_sq = (
        prefix_target_sq[target_end] - prefix_target_sq[target_start]
    )

    safe_overlap = np.maximum(overlap, 1)
    covariance = corr_sum - (sum_ref * sum_target / safe_overlap)
    variance_ref = sum_ref_sq - (sum_ref ** 2 / safe_overlap)
    variance_target = sum_target_sq - (sum_target ** 2 / safe_overlap)
    denominator = np.sqrt(
        np.maximum(variance_ref * variance_target, 0.0)
    )

    scores = np.full(full_len, -np.inf, dtype=np.float64)
    valid = (
        (overlap >= MIN_OVERLAP_SECONDS * ENVELOPE_RATE)
        & (denominator > 1e-12)
        & (np.abs(lags) <= MAX_SYNC_OFFSET_SECONDS * ENVELOPE_RATE)
    )
    scores[valid] = covariance[valid] / denominator[valid]

    if not np.any(valid):
        raise ValueError("No offset had enough overlapping audio to compare")

    best_index = int(np.argmax(scores))
    return (
        float(lags[best_index] / ENVELOPE_RATE),
        float(scores[best_index]),
    )


def aligned_audio_filter(input_index, shift, duration):
    """Align one external audio track to VIDEO's timeline."""
    filters = ["asetpts=PTS-STARTPTS"]

    if shift >= 0:
        filters.extend([
            f"atrim=start={shift:.6f}",
            "asetpts=PTS-STARTPTS",
        ])
    else:
        delay_ms = round(abs(shift) * 1000)
        filters.append(f"adelay={delay_ms}:all=1")

    filters.extend([
        f"aresample={OUTPUT_AUDIO_RATE}",
        "aformat=sample_fmts=fltp:channel_layouts=stereo",
        f"apad=pad_dur={duration:.6f}",
        f"atrim=duration={duration:.6f}",
        "asetpts=PTS-STARTPTS",
    ])

    return f"[{input_index}:a]{','.join(filters)}"


def aligned_video_filter(input_index, shift, duration, width, height, label):
    """Align one camera's picture to VIDEO's timeline."""
    filters = ["setpts=PTS-STARTPTS"]

    if shift >= 0:
        filters.append(f"trim=start={shift:.6f}")
    else:
        filters.append(
            f"tpad=start_mode=clone:start_duration={abs(shift):.6f}"
        )

    filters.extend([
        "setpts=PTS-STARTPTS",
        f"tpad=stop_mode=clone:stop_duration={duration:.6f}",
        f"trim=duration={duration:.6f}",
        (
            f"scale={width}:{height}:"
            "force_original_aspect_ratio=decrease"
        ),
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        "setsar=1",
        f"fps={OUTPUT_FPS}",
        "format=yuv420p",
    ])

    return f"[{input_index}:v:0]{','.join(filters)}[{label}]"


def _filter_short_runs(mask, value, max_length, replacement):
    """
    Replace runs of `value` shorter than or equal to max_length with `replacement`.
    """
    result = mask.copy()
    changes = np.diff(np.r_[False, result == value, False].astype(np.int8))
    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1)

    for start, end in zip(starts, ends):
        if end - start <= max_length:
            result[start:end] = replacement

    return result


def audio_activity_on_timeline(path, shift, duration):
    """
    Compute a boolean activity mask for 1/ENVELOPE_RATE-second frames aligned to VIDEO.
    """
    rate, samples = read_pcm16_wav(path)
    frame_size = rate // ENVELOPE_RATE
    if frame_size <= 0:
        raise ValueError(f"Invalid analysis rate in {path}")

    frame_count = len(samples) // frame_size
    if frame_count == 0:
        raise ValueError(f"No audio available for activity analysis in {path}")

    frames = samples[:frame_count * frame_size].reshape(frame_count, frame_size)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    dbfs = 20.0 * np.log10(np.maximum(rms, 1e-8))

    noise_floor = float(np.percentile(dbfs, 20))
    threshold = max(
        ACTIVITY_FLOOR_DBFS,
        noise_floor + ACTIVITY_ABOVE_NOISE_DB,
    )
    source_active = dbfs >= threshold

    gap_frames = round(MAX_SILENCE_GAP_SECONDS * ENVELOPE_RATE)
    min_active_frames = round(MIN_ACTIVITY_SECONDS * ENVELOPE_RATE)

    source_active = _filter_short_runs(
        source_active, False, gap_frames, True
    )
    source_active = _filter_short_runs(
        source_active, True, min_active_frames, False
    )

    timeline_count = math.ceil(duration * ENVELOPE_RATE)
    timeline_active = np.zeros(timeline_count, dtype=bool)

    source_times = np.arange(frame_count) / ENVELOPE_RATE
    timeline_indices = np.rint(
        (source_times - shift) * ENVELOPE_RATE
    ).astype(np.int64)

    valid = (
        (timeline_indices >= 0)
        & (timeline_indices < timeline_count)
        & source_active
    )
    timeline_active[timeline_indices[valid]] = True
    return timeline_active


def choose_camera_by_activity(audio1_wav, audio2_wav, shift1, shift2, duration):
    """
    Pick the camera based on mic activity.

    Priority:
    - if only one mic is active, show that person
    - if both are active, show the one whose activity just started
    - if neither is active, keep the current camera
    """
    active1 = audio_activity_on_timeline(audio1_wav, shift1, duration)
    active2 = audio_activity_on_timeline(audio2_wav, shift2, duration)

    camera = np.ones(len(active1), dtype=np.int8)
    current_camera = 1
    was_active1 = False
    was_active2 = False

    for i, (is_active1, is_active2) in enumerate(zip(active1, active2)):
        onset1 = is_active1 and not was_active1
        onset2 = is_active2 and not was_active2

        if is_active1 and not is_active2:
            current_camera = 1
        elif is_active2 and not is_active1:
            current_camera = 2
        elif is_active1 and is_active2:
            if onset1 and not onset2:
                current_camera = 1
            elif onset2 and not onset1:
                current_camera = 2

        camera[i] = current_camera
        was_active1 = is_active1
        was_active2 = is_active2

    return camera


def camera_cut_filters(duration, camera_by_frame):
    """
    Build a concat filter that switches cameras according to the per-frame camera choice.
    """
    frame_count = len(camera_by_frame)
    if frame_count == 0:
        raise ValueError("No camera-selection frames were generated")

    boundaries = np.flatnonzero(
        camera_by_frame[1:] != camera_by_frame[:-1]
    ) + 1
    starts = np.r_[0, boundaries]
    ends = np.r_[boundaries, frame_count]

    count_by_camera = {
        1: int(np.count_nonzero(camera_by_frame[starts] == 1)),
        2: int(np.count_nonzero(camera_by_frame[starts] == 2)),
    }

    filters = []

    if count_by_camera[1]:
        filters.append(
            f"[v1]split={count_by_camera[1]}"
            + "".join(f"[v1s{i}]" for i in range(count_by_camera[1]))
        )
    if count_by_camera[2]:
        filters.append(
            f"[v2]split={count_by_camera[2]}"
            + "".join(f"[v2s{i}]" for i in range(count_by_camera[2]))
        )

    camera1_index = 0
    camera2_index = 0
    segment_labels = []

    for segment_number, (start_frame, end_frame) in enumerate(zip(starts, ends)):
        start = start_frame / ENVELOPE_RATE
        end = min(end_frame / ENVELOPE_RATE, duration)
        segment_duration = end - start
        label = f"segment{segment_number}"

        if camera_by_frame[start_frame] == 1:
            source = f"[v1s{camera1_index}]"
            camera1_index += 1
        else:
            source = f"[v2s{camera2_index}]"
            camera2_index += 1

        filters.append(
            f"{source}trim=start={start:.6f}:"
            f"duration={segment_duration:.6f},"
            f"setpts=PTS-STARTPTS[{label}]"
        )
        segment_labels.append(f"[{label}]")

    filters.append(
        f"{''.join(segment_labels)}concat=n={len(segment_labels)}:v=1:a=0[vout]"
    )
    return ";".join(filters)


def estimate_and_check(reference_wav, target_wav, label):
    try:
        shift, confidence = estimate_shift(reference_wav, target_wav)
    except ValueError as exc:
        raise SystemExit(f"Could not sync {label}: {exc}") from exc

    print(
        f"{label} shift relative to VIDEO: {shift:+.2f}s "
        f"(correlation {confidence:.2f})"
    )

    if confidence < MIN_CORRELATION:
        raise SystemExit(
            f"Stopped: no reliable match found between VIDEO's embedded "
            f"audio and {label}. No output was written."
        )

    return shift


def export_camera_cuts(path, camera_by_frame, duration):
    """Save contiguous camera selections as an inspectable JSON cut list."""
    if len(camera_by_frame) == 0:
        raise ValueError("No camera-selection frames were generated")

    boundaries = np.flatnonzero(
        camera_by_frame[1:] != camera_by_frame[:-1]
    ) + 1
    starts = np.r_[0, boundaries]
    ends = np.r_[boundaries, len(camera_by_frame)]

    cuts = []
    for start_frame, end_frame in zip(starts, ends):
        start = start_frame / ENVELOPE_RATE
        end = min(end_frame / ENVELOPE_RATE, duration)
        camera_number = int(camera_by_frame[start_frame])

        cuts.append({
            "start_seconds": round(start, 3),
            "end_seconds": round(end, 3),
            "duration_seconds": round(end - start, 3),
            "camera": f"VIDEO{camera_number}",
        })

    data = {
        "video_duration_seconds": round(duration, 3),
        "envelope_rate": ENVELOPE_RATE,
        "camera_sources": {
            "VIDEO1": VIDEO.relative_to(ROOT).as_posix(),
            "VIDEO2": VIDEO2.relative_to(ROOT).as_posix(),
        },
        "cuts": cuts,
    }

    with open(path, "w", encoding="utf-8") as json_file:
        json.dump(data, json_file, indent=2)
        json_file.write("\n")

    print(f"Saved {len(cuts)} camera cuts to {path}")


def main():
    require_media_tools()
    for path in (VIDEO, VIDEO2, AUDIO1, AUDIO2):
        if not path.is_file():
            raise SystemExit(
                f"Required input file not found: {path}\n"
                "Put the four input files in src/files. See README.md for filenames."
            )

    video_duration = probe_duration(VIDEO)
    width, height = probe_video_size(VIDEO)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        video_wav = temp_dir / "video_audio.wav"
        video2_wav = temp_dir / "video2_audio.wav"
        audio1_wav = temp_dir / "audio1.wav"
        audio2_wav = temp_dir / "audio2.wav"

        print("Extracting analysis audio...")
        try:
            extract_analysis_wav(VIDEO, video_wav)
        except subprocess.CalledProcessError as exc:
            raise SystemExit(
                "Could not extract audio from VIDEO. This test needs "
                "VIDEO's embedded audio as its sync reference."
            ) from exc

        try:
            extract_analysis_wav(VIDEO2, video2_wav)
        except subprocess.CalledProcessError as exc:
            raise SystemExit(
                "Could not extract audio from VIDEO2. This test uses "
                "VIDEO2's embedded audio to sync its picture to VIDEO."
            ) from exc

        extract_analysis_wav(AUDIO1, audio1_wav)
        extract_analysis_wav(AUDIO2, audio2_wav)

        # Estimate each source independently against VIDEO's embedded audio.
        video2_shift = estimate_and_check(
            video_wav, video2_wav, "VIDEO2"
        )
        shift1 = estimate_and_check(video_wav, audio1_wav, "AUDIO1")
        shift2 = estimate_and_check(video_wav, audio2_wav, "AUDIO2")

        # Use the mic activity to decide which camera to show.
        camera_by_frame = choose_camera_by_activity(
            audio1_wav, audio2_wav, shift1, shift2, video_duration
        )
        export_camera_cuts(CUTS_JSON, camera_by_frame, video_duration)

        audio1_filter = aligned_audio_filter(1, shift1, video_duration)
        audio2_filter = aligned_audio_filter(2, shift2, video_duration)

        video1_filter = aligned_video_filter(
            0, 0.0, video_duration, width, height, "v1"
        )
        video2_filter = aligned_video_filter(
            3, video2_shift, video_duration, width, height, "v2"
        )

        filter_complex = (
            f"{audio1_filter}[a1];"
            f"{audio2_filter}[a2];"
            "[a1][a2]"
            "amix=inputs=2:duration=longest:dropout_transition=0:"
            "weights='1 1':normalize=0,"
            "alimiter=limit=0.95"
            "[merged];"
            f"{video1_filter};"
            f"{video2_filter};"
            f"{camera_cut_filters(video_duration, camera_by_frame)}"
        )

        print(f"Writing {OUTPUT.name} with activity-driven camera switching...")
        run([
            "ffmpeg", "-y",
            "-i", str(VIDEO),
            "-i", str(AUDIO1),
            "-i", str(AUDIO2),
            "-i", str(VIDEO2),
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[merged]",
            "-t", str(video_duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(OUTPUT),
        ])

    print(f"Done: {OUTPUT}")


if __name__ == "__main__":
    main()
