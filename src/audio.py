import json
import math
import re
import subprocess

from config import (
    COMPRESSOR_ATTACK_MS,
    COMPRESSOR_MAKEUP,
    COMPRESSOR_RATIO,
    COMPRESSOR_RELEASE_MS,
    COMPRESSOR_THRESHOLD,
    GATE_ATTACK_MS,
    GATE_RANGE,
    GATE_RATIO,
    GATE_RELEASE_MS,
    GATE_THRESHOLD,
    LOUDNESS_TOLERANCE_LU,
    OUTPUT_AUDIO_RATE,
    TARGET_LUFS,
    TARGET_TRUE_PEAK,
)
from media import run


def measure_loudness(path):
    """Return integrated loudness (LUFS) and true peak (dBTP)."""
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats",
            "-i", str(path),
            "-map", "0:a:0",
            "-af",
            (
                f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TRUE_PEAK}:"
                "LRA=11:print_format=json"
            ),
            "-f", "null", "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    matches = re.findall(
        r'\{\s*"input_i".*?\}', result.stderr, flags=re.DOTALL
    )
    if not matches:
        raise RuntimeError(f"Could not read loudness measurement for {path}")

    stats = json.loads(matches[-1])
    return float(stats["input_i"]), float(stats["input_tp"])


def process_audio(path, output_path):
    """Apply voice cleanup and loudness normalization to an audio track."""
    filters = (
        f"agate=threshold={GATE_THRESHOLD}:ratio={GATE_RATIO}:"
        f"attack={GATE_ATTACK_MS}:release={GATE_RELEASE_MS}:range={GATE_RANGE},"
        "highpass=f=80,"
        "equalizer=f=250:width_type=q:width=1:gain=-2,"
        "equalizer=f=3500:width_type=q:width=1:gain=2,"
        f"acompressor=threshold={COMPRESSOR_THRESHOLD}:"
        f"ratio={COMPRESSOR_RATIO}:attack={COMPRESSOR_ATTACK_MS}:"
        f"release={COMPRESSOR_RELEASE_MS}:makeup={COMPRESSOR_MAKEUP},"
        f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TRUE_PEAK}:LRA=11"
    )

    run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(path),
        "-map", "0:a:0",
        "-af", filters,
        "-c:a", "pcm_s24le",
        str(output_path),
    ])


def prepare_audio(path, processed_path):
    """Use a track as-is if loudness/peak targets pass; otherwise process it."""
    integrated_lufs, true_peak = measure_loudness(path)
    print(
        f"{path}: {integrated_lufs:.1f} LUFS integrated, "
        f"{true_peak:.1f} dBTP true peak"
    )

    loudness_ok = (
        math.isfinite(integrated_lufs)
        and abs(integrated_lufs - TARGET_LUFS) <= LOUDNESS_TOLERANCE_LU
    )
    peak_ok = math.isfinite(true_peak) and true_peak <= TARGET_TRUE_PEAK

    if loudness_ok and peak_ok:
        print(f"Using {path} as-is; it meets the loudness check.")
        return str(path)

    print(f"Processing {path}...")
    process_audio(path, processed_path)
    return str(processed_path)


def aligned_audio_filter(input_index, shift, duration):
    """Build the filter that aligns an external audio track to VIDEO's timeline."""
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
