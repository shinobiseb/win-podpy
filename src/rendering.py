import subprocess

from audio import aligned_audio_filter
from config import OUTPUT_FPS


def aligned_video_filter(input_index, shift, duration, width, height, label):
    """Build the filter that aligns a camera picture to VIDEO's timeline."""
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
        f"scale={width}:{height}:force_original_aspect_ratio=decrease",
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        "setsar=1",
        f"fps={OUTPUT_FPS}",
        "format=yuv420p",
    ])
    return f"[{input_index}:v:0]{','.join(filters)}[{label}]"


def camera_two_enable_expression(camera_by_frame, duration, envelope_rate):
    """Build an enable expression for camera-two intervals without splitting streams."""
    frame_count = len(camera_by_frame)
    if frame_count == 0:
        raise ValueError("No camera-selection frames were generated")

    boundaries = [
        i for i in range(1, frame_count)
        if camera_by_frame[i] != camera_by_frame[i - 1]
    ]
    starts = [0, *boundaries]
    ends = [*boundaries, frame_count]
    intervals = []

    for start_frame, end_frame in zip(starts, ends):
        if int(camera_by_frame[start_frame]) != 2:
            continue
        start = start_frame / envelope_rate
        end = min(end_frame / envelope_rate, duration)
        if end > start:
            intervals.append(f"between(t\\,{start:.6f}\\,{end:.6f})")

    # An expression that is always false leaves the base (camera-one) video visible.
    return "+".join(intervals) if intervals else "0"


def render_video(
    video1,
    audio1,
    audio2,
    video2,
    output,
    duration,
    width,
    height,
    shift1,
    shift2,
    video2_shift,
    camera_by_frame,
    envelope_rate,
):
    """Render the switched video using a low-memory overlay instead of stream splits."""
    audio1_filter = aligned_audio_filter(1, shift1, duration)
    audio2_filter = aligned_audio_filter(2, shift2, duration)
    video1_filter = aligned_video_filter(0, 0.0, duration, width, height, "v1")
    video2_filter = aligned_video_filter(
        3, video2_shift, duration, width, height, "v2"
    )
    camera_two_enable = camera_two_enable_expression(
        camera_by_frame, duration, envelope_rate
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
        f"[v1][v2]overlay=eof_action=pass:shortest=0:repeatlast=0:"
        f"enable='{camera_two_enable}',"
        f"fps={OUTPUT_FPS},settb=1/{OUTPUT_FPS},format=yuv420p[vout]"
    )

    print(f"Writing {output} with activity-driven camera switching...")
    subprocess.run([
        "ffmpeg", "-y",
        "-filter_complex_threads", "2",
        "-i", str(video1),
        "-i", str(audio1),
        "-i", str(audio2),
        "-i", str(video2),
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "[merged]",
        "-t", str(duration),
        "-r", str(OUTPUT_FPS),
        "-fps_mode", "cfr",
        "-c:v", "libx264",
        "-threads", "4",
        "-preset", "fast",
        "-crf", "18",
        "-level:v", "4.1",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(output),
    ], check=True)
