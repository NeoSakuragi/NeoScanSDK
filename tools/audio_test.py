#!/usr/bin/env python3
"""Audio test harness for NeoSynth driver validation.

Captures audio from the emulator via PipeWire, analyzes it with DSP,
reports pass/fail for each test case.

Usage:
  # Capture and analyze:
  python3 audio_test.py capture 2        # capture 2 seconds
  python3 audio_test.py analyze test.wav  # analyze a WAV file

  # Quick checks:
  python3 audio_test.py has_sound test.wav
  python3 audio_test.py is_clean test.wav
  python3 audio_test.py has_freq test.wav 440
"""

import subprocess, time, signal, sys, os, json
import numpy as np

def capture_audio(duration_sec=2, output="/tmp/neo_audio_test.wav"):
    """Capture system audio output via PipeWire."""
    proc = subprocess.Popen([
        "pw-record",
        "-P", "{ stream.capture.sink=true }",
        "--channels", "1",
        "--format", "s16",
        "--rate", "55555",
        output
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(duration_sec)
    proc.send_signal(signal.SIGINT)
    proc.wait(timeout=5)
    return output


def load_wav(path):
    """Load a WAV file as float32 mono."""
    from scipy.io import wavfile
    sr, data = wavfile.read(path)
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float32) / 2147483648.0
    if data.ndim > 1:
        data = data.mean(axis=1)
    return sr, data


def check_has_sound(data, threshold_db=-40):
    """Check if audio contains sound above threshold."""
    rms = np.sqrt(np.mean(data ** 2))
    rms_db = 20 * np.log10(rms + 1e-10)
    return rms_db > threshold_db, {"rms_db": round(float(rms_db), 1)}


def check_is_clean(data):
    """Check if audio is a clean sample (not noise/garbage).
    Uses spectral flatness: low = tonal/clean, high = noise."""
    from scipy.fft import rfft
    spectrum = np.abs(rfft(data))
    spectrum = spectrum[1:]  # skip DC
    log_spec = np.log(spectrum + 1e-10)
    geo_mean = np.exp(np.mean(log_spec))
    arith_mean = np.mean(spectrum)
    flatness = geo_mean / (arith_mean + 1e-10)

    crest = float(np.max(spectrum)) / (np.sqrt(np.mean(spectrum ** 2)) + 1e-10)

    is_clean = flatness < 0.3 and crest > 3.0
    return is_clean, {"flatness": round(float(flatness), 4), "crest": round(crest, 1)}


def check_has_frequency(data, sr, target_hz, tolerance_hz=30):
    """Check if a specific frequency is present."""
    from scipy.fft import rfft, rfftfreq
    N = len(data)
    spectrum = np.abs(rfft(data))
    freqs = rfftfreq(N, 1.0 / sr)

    mask = (freqs >= target_hz - tolerance_hz) & (freqs <= target_hz + tolerance_hz)
    band_energy = np.mean(spectrum[mask] ** 2) if mask.any() else 0
    total_energy = np.mean(spectrum ** 2)
    ratio = band_energy / (total_energy + 1e-10)

    return ratio > 0.05, {"ratio": round(float(ratio), 4), "target_hz": target_hz}


def check_is_silence(data, threshold_db=-50):
    """Check if audio is effectively silent."""
    has_sound, info = check_has_sound(data, threshold_db)
    return not has_sound, info


def check_has_onset(data, sr, threshold=0.02):
    """Check if there's a sound onset (attack) in the audio."""
    # Simple onset detection: find where RMS jumps above threshold
    frame_size = int(sr * 0.01)  # 10ms frames
    n_frames = len(data) // frame_size
    rms = np.array([
        np.sqrt(np.mean(data[i*frame_size:(i+1)*frame_size] ** 2))
        for i in range(n_frames)
    ])
    # Look for a jump
    diff = np.diff(rms)
    has_onset = np.any(diff > threshold)
    onset_frame = int(np.argmax(diff > threshold)) if has_onset else -1
    onset_time = onset_frame * 0.01 if has_onset else -1
    return bool(has_onset), {"onset_time_sec": round(onset_time, 3)}


def full_analysis(wav_path):
    """Run all checks on a WAV file."""
    sr, data = load_wav(wav_path)
    duration = len(data) / sr

    results = {"file": wav_path, "duration_sec": round(duration, 2), "sample_rate": int(sr)}

    has_sound, info = check_has_sound(data)
    results["has_sound"] = bool(has_sound)
    results["rms_db"] = info["rms_db"]

    if has_sound:
        is_clean, info = check_is_clean(data)
        results["is_clean"] = bool(is_clean)
        results["spectral_flatness"] = info["flatness"]
        results["crest_factor"] = info["crest"]

        has_onset, info = check_has_onset(data, sr)
        results["has_onset"] = bool(has_onset)
        results["onset_time"] = info["onset_time_sec"]

        # Find dominant frequency
        from scipy.fft import rfft, rfftfreq
        spectrum = np.abs(rfft(data))
        freqs = rfftfreq(len(data), 1.0 / sr)
        # Only look at audible range (50Hz - 15kHz)
        mask = (freqs >= 50) & (freqs <= 15000)
        if mask.any():
            peak_idx = np.argmax(spectrum[mask])
            peak_freq = freqs[mask][peak_idx]
            results["dominant_freq_hz"] = round(float(peak_freq), 1)
    else:
        results["is_clean"] = False
        results["dominant_freq_hz"] = 0

    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: audio_test.py <command> [args]")
        print("Commands: capture, analyze, has_sound, is_clean, has_freq, silence")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "capture":
        duration = float(sys.argv[2]) if len(sys.argv) > 2 else 2
        output = sys.argv[3] if len(sys.argv) > 3 else "/tmp/neo_audio_test.wav"
        print(f"Capturing {duration}s of audio to {output}...")
        capture_audio(duration, output)
        print(f"Done. Analyzing...")
        results = full_analysis(output)
        print(json.dumps(results, indent=2))

    elif cmd == "analyze":
        wav_path = sys.argv[2]
        results = full_analysis(wav_path)
        print(json.dumps(results, indent=2))

    elif cmd == "has_sound":
        wav_path = sys.argv[2]
        sr, data = load_wav(wav_path)
        ok, info = check_has_sound(data)
        print(f"{'PASS' if ok else 'FAIL'} — has_sound={ok} rms={info['rms_db']}dB")

    elif cmd == "is_clean":
        wav_path = sys.argv[2]
        sr, data = load_wav(wav_path)
        ok, info = check_is_clean(data)
        print(f"{'PASS' if ok else 'FAIL'} — is_clean={ok} flatness={info['flatness']} crest={info['crest']}")

    elif cmd == "has_freq":
        wav_path = sys.argv[2]
        target = float(sys.argv[3])
        sr, data = load_wav(wav_path)
        ok, info = check_has_frequency(data, sr, target)
        print(f"{'PASS' if ok else 'FAIL'} — {target}Hz present={ok} ratio={info['ratio']}")

    elif cmd == "silence":
        wav_path = sys.argv[2]
        sr, data = load_wav(wav_path)
        ok, info = check_is_silence(data)
        print(f"{'PASS' if ok else 'FAIL'} — silence={ok} rms={info['rms_db']}dB")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == '__main__':
    main()
