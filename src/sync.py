import numpy as np
import wave

from config import (
    ENVELOPE_RATE,
    MAX_SYNC_OFFSET_SECONDS,
    MIN_OVERLAP_SECONDS,
)


TRANSIENT_SEARCH_SECONDS = 30.0
TRANSIENT_FRAME_MS = 20
TRANSIENT_HOP_MS = 10
TRANSIENT_PEAK_THRESHOLD = 3.5
TRANSIENT_MIN_SEPARATION_SECONDS = 0.15
TRANSIENT_MATCH_TOLERANCE_SECONDS = 0.040
TRANSIENT_MIN_MATCHES = 2
TRANSIENT_WINDOW_SECONDS = 0.250

SPECTRAL_FFT_SIZE = 2048
SPECTRAL_MIN_HZ = 300.0
SPECTRAL_MAX_HZ = 8000.0


def read_pcm16_wav(path):
    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 1:
            raise ValueError(f"{path} must be mono PCM")
        if wav.getsampwidth() != 2:
            raise ValueError(f"{path} must be 16-bit PCM")

        rate = wav.getframerate()
        samples = np.frombuffer(
            wav.readframes(wav.getnframes()),
            dtype="<i2",
        ).astype(np.float32) / 32768.0

    return rate, samples


def transient_times(path, search_seconds=TRANSIENT_SEARCH_SECONDS):
    """Return strong, separated onset times near the beginning of a recording."""
    rate, samples = read_pcm16_wav(path)
    samples = samples[: int(search_seconds * rate)]

    frame_size = max(64, int(rate * TRANSIENT_FRAME_MS / 1000))
    hop = max(32, int(rate * TRANSIENT_HOP_MS / 1000))

    if len(samples) < frame_size * 2:
        raise ValueError(f"Not enough audio to find transients: {path}")

    frame_count = 1 + (len(samples) - frame_size) // hop
    onset = np.zeros(frame_count, dtype=np.float64)
    window = np.hanning(frame_size)

    previous_spectrum = None
    for i in range(frame_count):
        start = i * hop
        frame = samples[start:start + frame_size]

        if len(frame) < frame_size:
            break

        spectrum = np.abs(np.fft.rfft(frame * window))

        if previous_spectrum is not None:
            positive_flux = np.maximum(spectrum - previous_spectrum, 0.0)

            if i > 1:
                previous_frame = samples[start - hop:start - hop + frame_size]
                previous_rms = np.sqrt(np.mean(previous_frame ** 2) + 1e-12)
                current_rms = np.sqrt(np.mean(frame ** 2) + 1e-12)
                amplitude_rise = max(current_rms / previous_rms - 1.0, 0.0)
            else:
                amplitude_rise = 0.0

            onset[i] = (
                0.7 * float(np.mean(positive_flux))
                + 0.3 * amplitude_rise
            )

        previous_spectrum = spectrum

    onset_std = float(onset.std())
    if onset_std < 1e-12:
        raise ValueError(f"No detectable transients in {path}")

    onset = (onset - onset.mean()) / onset_std
    peaks = []

    for i in range(1, len(onset) - 1):
        if onset[i] < TRANSIENT_PEAK_THRESHOLD:
            continue
        if onset[i] <= onset[i - 1] or onset[i] < onset[i + 1]:
            continue

        peak_time = i * hop / rate
        if (
            not peaks
            or peak_time - peaks[-1][0] >= TRANSIENT_MIN_SEPARATION_SECONDS
        ):
            peaks.append((peak_time, float(onset[i])))
        elif onset[i] > peaks[-1][1]:
            peaks[-1] = (peak_time, float(onset[i]))

    if len(peaks) < TRANSIENT_MIN_MATCHES:
        raise ValueError(
            f"Could not find at least {TRANSIENT_MIN_MATCHES} strong "
            f"transients in {path}"
        )

    return peaks


def rms_envelope(path):
    """Return a normalized RMS amplitude envelope."""
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

def spectral_flux_envelope(path):
    """Return a normalized spectral-flux envelope and its frame rate."""
    rate, samples = read_pcm16_wav(path)

    if rate <= 0:
        raise ValueError(f"Invalid sample rate in {path}")

    hop_size = max(1, round(rate / ENVELOPE_RATE))
    frame_rate = rate / hop_size

    if len(samples) < SPECTRAL_FFT_SIZE:
        raise ValueError(f"Not enough audio for spectral analysis in {path}")

    window = np.hanning(SPECTRAL_FFT_SIZE).astype(np.float32)
    frequencies = np.fft.rfftfreq(SPECTRAL_FFT_SIZE, d=1.0 / rate)
    max_hz = min(SPECTRAL_MAX_HZ, rate / 2.0)
    band = (frequencies >= SPECTRAL_MIN_HZ) & (frequencies <= max_hz)

    if not np.any(band):
        raise ValueError(
            f"Sample rate in {path} does not cover the spectral analysis band"
        )

    last_start = len(samples) - SPECTRAL_FFT_SIZE
    flux = []
    previous_spectrum = None

    for start in range(0, last_start + 1, hop_size):
        frame = samples[start:start + SPECTRAL_FFT_SIZE] * window
        spectrum = np.log1p(np.abs(np.fft.rfft(frame))[band])

        norm = np.linalg.norm(spectrum)
        if norm > 1e-12:
            spectrum = spectrum / norm

        if previous_spectrum is not None:
            flux.append(
                float(np.maximum(spectrum - previous_spectrum, 0.0).sum())
            )

        previous_spectrum = spectrum

    flux = np.asarray(flux, dtype=np.float64)
    minimum_frames = int(np.ceil(MIN_OVERLAP_SECONDS * frame_rate))

    if len(flux) < minimum_frames:
        raise ValueError(
            f"Not enough audio to estimate sync in {path}; "
            f"need at least {MIN_OVERLAP_SECONDS} seconds"
        )

    std = float(flux.std())
    if std < 1e-12:
        raise ValueError(f"No detectable spectral transients in {path}")

    return (flux - flux.mean()) / std, frame_rate


def _estimate_envelope_shift(reference, target, frames_per_second):
    """Estimate normalized envelope offset by lagged correlation."""
    n_ref = len(reference)
    n_target = len(target)

    if n_ref == 0 or n_target == 0:
        raise ValueError("Cannot estimate sync from an empty envelope")

    full_len = n_ref + n_target - 1
    fft_size = 1 << (full_len - 1).bit_length()

    # With this ordering, a positive lag means the matching content is later
    # in the target.
    corr_sum = np.fft.irfft(
        np.fft.rfft(target, fft_size)
        * np.fft.rfft(reference[::-1], fft_size),
        fft_size,
    )[:full_len]

    lags = np.arange(full_len) - (n_ref - 1)

    prefix_ref = np.concatenate(
        ([0.0], np.cumsum(reference, dtype=np.float64))
    )
    prefix_target = np.concatenate(
        ([0.0], np.cumsum(target, dtype=np.float64))
    )
    prefix_ref_sq = np.concatenate(
        ([0.0], np.cumsum(reference ** 2, dtype=np.float64))
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

    minimum_overlap = int(np.ceil(MIN_OVERLAP_SECONDS * frames_per_second))
    maximum_lag = int(np.floor(MAX_SYNC_OFFSET_SECONDS * frames_per_second))

    scores = np.full(full_len, -np.inf, dtype=np.float64)
    valid = (
        (overlap >= minimum_overlap)
        & (denominator > 1e-12)
        & (np.abs(lags) <= maximum_lag)
    )
    scores[valid] = covariance[valid] / denominator[valid]

    if not np.any(valid):
        raise ValueError("No offset had enough overlapping audio to compare")

    best_index = int(np.argmax(scores))
    return (
        float(lags[best_index] / frames_per_second),
        float(scores[best_index]),
    )


def estimate_shift(reference_wav, target_wav):
    """
    Estimate the target offset using spectral-flux correlation.

    Positive shift means matching content occurs later in the target.
    Negative shift means matching content occurs earlier in the target.
    """
    reference, reference_rate = spectral_flux_envelope(reference_wav)
    target, target_rate = spectral_flux_envelope(target_wav)

    if not np.isclose(reference_rate, target_rate):
        raise ValueError(
            "Reference and target audio have different analysis frame rates"
        )

    return _estimate_envelope_shift(reference, target, reference_rate)


def refine_transient_offset(reference_wav, target_wav, approximate_offset):
    """Refine a transient offset using short raw waveform windows."""
    reference_rate, reference = read_pcm16_wav(reference_wav)
    target_rate, target = read_pcm16_wav(target_wav)

    if reference_rate != target_rate:
        raise ValueError("Transient analysis files have different sample rates")

    reference_peaks = transient_times(reference_wav)
    window = int(TRANSIENT_WINDOW_SECONDS * reference_rate)
    lag_estimates = []

    for reference_time, _ in reference_peaks:
        target_expected = reference_time + approximate_offset
        if target_expected < 0:
            continue

        reference_center = int(reference_time * reference_rate)
        target_center = int(target_expected * reference_rate)

        reference_start = max(0, reference_center - window)
        reference_end = min(len(reference), reference_center + window)
        target_start = max(0, target_center - window)
        target_end = min(len(target), target_center + window)

        reference_segment = reference[reference_start:reference_end]
        target_segment = target[target_start:target_end]

        if len(reference_segment) < reference_rate // 10:
            continue
        if len(target_segment) < reference_rate // 10:
            continue

        length = min(len(reference_segment), len(target_segment))
        reference_segment = reference_segment[:length]
        target_segment = target_segment[:length]

        if (
            np.std(reference_segment) < 1e-8
            or np.std(target_segment) < 1e-8
        ):
            continue

        reference_segment = reference_segment - reference_segment.mean()
        search_radius = int(0.020 * reference_rate)
        best_lag = 0
        best_score = -np.inf

        for lag in range(-search_radius, search_radius + 1):
            shifted_start = lag
            shifted_end = lag + length
            if shifted_start < 0 or shifted_end > len(target_segment):
                continue

            target_part = target_segment[shifted_start:shifted_end]
            target_part = target_part - target_part.mean()

            denominator = np.sqrt(
                np.dot(reference_segment, reference_segment)
                * np.dot(target_part, target_part)
            )
            if denominator <= 1e-12:
                continue

            score = np.dot(reference_segment, target_part) / denominator
            if score > best_score:
                best_score = score
                best_lag = lag

        if np.isfinite(best_score):
            lag_estimates.append((best_lag / reference_rate, best_score))

    if not lag_estimates:
        return approximate_offset

    lag_estimates.sort(key=lambda item: item[1], reverse=True)
    return approximate_offset + lag_estimates[0][0]


def estimate_shift_rms(reference_wav, target_wav):
    """Estimate offset using RMS envelopes instead of spectral flux."""
    reference = rms_envelope(reference_wav)
    target = rms_envelope(target_wav)

    return _estimate_envelope_shift(
        reference,
        target,
        float(ENVELOPE_RATE),
    )


def estimate_and_check(reference_wav, target_wav, label, min_correlation):
    try:
        shift, confidence = estimate_shift(reference_wav, target_wav)
    except ValueError as exc:
        raise SystemExit(f"Could not sync {label}: {exc}") from exc

    print(
        f"{label} shift relative to VIDEO: {shift:+.2f}s "
        f"(spectral-flux correlation {confidence:.2f})"
    )

    if confidence < min_correlation:
        raise SystemExit(
            f"Stopped: no reliable spectral match found between VIDEO's "
            f"embedded audio and {label}. No output was written."
        )

    return shift