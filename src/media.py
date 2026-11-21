import json
import subprocess
import wave

import numpy as np

from config import ANALYSIS_SAMPLE_RATE, ANALYSIS_SECONDS, OUTPUT_AUDIO_RATE


def run(args):
    subprocess.run(args, check=True)


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


def extract_audio_track(source, output):
    """Extract a full-length stereo audio track for processing and rendering."""
    run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(source),
        "-map", "0:a:0",
        "-vn",
        "-ac", "2",
        "-ar", str(OUTPUT_AUDIO_RATE),
        "-c:a", "pcm_s24le",
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
