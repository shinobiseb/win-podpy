import numpy as np

from config import (
    ENVELOPE_RATE,
    MAX_SYNC_OFFSET_SECONDS,
    MIN_OVERLAP_SECONDS,
)
from media import read_pcm16_wav


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


def estimate_and_check(reference_wav, target_wav, label, min_correlation):
    try:
        shift, confidence = estimate_shift(reference_wav, target_wav)
    except ValueError as exc:
        raise SystemExit(f"Could not sync {label}: {exc}") from exc

    print(
        f"{label} shift relative to VIDEO: {shift:+.2f}s "
        f"(correlation {confidence:.2f})"
    )

    if confidence < min_correlation:
        raise SystemExit(
            f"Stopped: no reliable match found between VIDEO's embedded "
            f"audio and {label}. No output was written."
        )

    return shift
