from pathlib import Path
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import numpy as np

import config
import media
import sync


def resolve_input(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def wav_duration(path):
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


def loud_peaks(path, seconds=15):
    rate, samples = media.read_pcm16_wav(path)
    samples = samples[: int(seconds * rate)]

    frame = max(1, rate // 100)  # 10 ms
    count = len(samples) // frame
    if count < 3:
        return []

    samples = samples[: count * frame].reshape(count, frame)
    rms = np.sqrt(np.mean(samples**2, axis=1))

    candidates = [
        i
        for i in range(1, len(rms) - 1)
        if rms[i] >= rms[i - 1] and rms[i] > rms[i + 1]
    ]
    candidates.sort(key=lambda i: rms[i], reverse=True)

    selected = []
    for i in candidates:
        if all(abs(i - previous) >= 30 for previous in selected):  # 300 ms
            selected.append(i)
        if len(selected) == 10:
            break

    return [
        (round(i * frame / rate, 2), round(float(rms[i]), 4))
        for i in sorted(selected)
    ]


print("Project root:", ROOT)
print("Config loaded from:", config.__file__)
print("Media module loaded from:", media.__file__)
print("Sync module loaded from:", sync.__file__)
print("ANALYSIS_SECONDS:", config.ANALYSIS_SECONDS)
print("MAX_SYNC_OFFSET_SECONDS (config):", config.MAX_SYNC_OFFSET_SECONDS)
print("MAX_SYNC_OFFSET_SECONDS (sync module):", sync.MAX_SYNC_OFFSET_SECONDS)

video1 = resolve_input(config.VIDEO)
video2 = resolve_input(config.VIDEO2)
print("Video 1:", video1)
print("Video 2:", video2)

with tempfile.TemporaryDirectory() as temp:
    temp = Path(temp)
    ref = temp / "video1.wav"
    target = temp / "video2.wav"

    media.extract_analysis_wav(video1, ref)
    media.extract_analysis_wav(video2, target)

    print("Extracted Video 1 audio duration:", wav_duration(ref))
    print("Extracted Video 2 audio duration:", wav_duration(target))

    shift, confidence = sync.estimate_shift_rms(ref, target)
    print(f"RMS offset: {shift:+.2f}s; correlation: {confidence:.3f}")

    if abs(shift) > config.MAX_SYNC_OFFSET_SECONDS:
        print("Warning: estimated offset exceeds the configured search limit.")

    print("Video 1 loud peaks (time, level):", loud_peaks(ref))
    print("Video 2 loud peaks (time, level):", loud_peaks(target))