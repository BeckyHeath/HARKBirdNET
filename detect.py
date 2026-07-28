"""
detect.py
=========
Run BirdNET on each recording and attach a direction of arrival to every
detection by looking up the HARK MUSIC spectrum at the detection's timestamp.

Requires localise.py to have run first -- it needs spectrum.txt.

Outputs
-------
    birdnet_detections.csv   per recording, inside localized_<filename>/
    birdnet_<folder>.csv     per site-day folder, in DATA_DIR

Columns: folder, filename, species_latin, species_common, confidence,
         time_start, time_end, azimuth_peak, azimuth_mean

A note on the two azimuth columns
---------------------------------
azimuth_peak  argmax across the 72 azimuths at the detection's MIDPOINT frame.
azimuth_mean  argmax per frame across the whole detection, then averaged.

**Use azimuth_peak.** azimuth_mean averages angles arithmetically, which breaks
at the +/-180 wraparound (170 and -170 average to 0, not 180). It is kept only
for comparison.

argmax always returns a direction. There is no source-presence test, so a
detection in a frame dominated by wind or an echo still gets a confident-looking
azimuth.

Usage
-----
    python harkbirdnet/detect.py
"""

import logging
import os

# Silence TensorFlow and absl before birdnet imports them.
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
logging.getLogger("absl").setLevel(logging.ERROR)

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf

import birdnet

import config

# HARK's 72 fixed directions: -180 to 175 in 5-degree steps.
AZIMUTHS = np.linspace(-180, 175, 72)


def peak_azimuth(spectrum, time_mid, duration, n_frames):
    """Loudest direction at the frame nearest time_mid."""
    idx = int(round(time_mid / duration * (n_frames - 1)))
    idx = max(0, min(idx, n_frames - 1))
    return float(AZIMUTHS[np.argmax(spectrum[idx, :])])


def mean_azimuth(spectrum, time_start, time_end, duration, n_frames):
    """Arithmetic mean of per-frame peak directions. See docstring caveat."""
    i0 = max(0, min(int(round(time_start / duration * (n_frames - 1))), n_frames - 1))
    i1 = max(0, min(int(round(time_end / duration * (n_frames - 1))), n_frames - 1))
    if i0 == i1:
        i1 = min(i0 + 1, n_frames - 1)
    peaks = np.argmax(spectrum[i0:i1 + 1, :], axis=1)
    return float(np.mean(AZIMUTHS[peaks]))


def parse_species(s):
    """BirdNET returns 'Genus species_Common Name'."""
    latin, _, common = s.partition("_")
    return latin.strip(), common.strip()


def process_file(wav, species_filter, folder_name):
    localized = wav.parent / f"localized_{wav.name}"
    spectrum_path = localized / "spectrum.txt"

    if not spectrum_path.exists():
        print("  -> no spectrum.txt, skipping (run localise.py first)")
        return None

    spectrum = np.loadtxt(spectrum_path, delimiter="\t")
    n_frames = spectrum.shape[0]

    audio, rate = sf.read(wav)
    mono = np.mean(audio, axis=1) if audio.ndim > 1 else audio
    duration = len(audio) / rate

    # Named temp file so concurrent runs cannot clobber each other.
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        sf.write(tmp_path, mono, rate)
        try:
            results = list(birdnet.predict_species_within_audio_file(
                Path(tmp_path),
                min_confidence=config.MIN_CONFIDENCE,
                species_filter=species_filter,
                chunk_overlap_s=config.CHUNK_OVERLAP_S,
                silent=True,
            ))
        except Exception as e:
            print(f"  -> BirdNET error: {e}")
            return None
    finally:
        os.unlink(tmp_path)

    records = []
    for (t0, t1), predictions in results:
        az_peak = peak_azimuth(spectrum, (t0 + t1) / 2.0, duration, n_frames)
        az_mean = mean_azimuth(spectrum, t0, t1, duration, n_frames)
        for species, conf in predictions.items():
            latin, common = parse_species(species)
            records.append({
                "folder": folder_name,
                "filename": wav.name,
                "species_latin": latin,
                "species_common": common,
                "confidence": round(conf, 4),
                "time_start": t0,
                "time_end": t1,
                "azimuth_peak": round(az_peak, 2),
                "azimuth_mean": round(az_mean, 2),
            })

    if not records:
        print("  -> no detections above threshold")
        return None

    df = pd.DataFrame(records)
    df.to_csv(localized / "birdnet_detections.csv", index=False)
    print(f"  -> {len(records)} detections")
    return df


def main():
    config.check_paths()

    print(f"Species filter for lat={config.LAT}, lon={config.LON}, "
          f"week={config.WEEK} ...")
    species_filter = set(birdnet.predict_species_at_location_and_time(
        config.LAT, config.LON, week=config.WEEK).keys())
    print(f"  -> {len(species_filter)} species\n")

    folders = sorted(p for p in config.DATA_DIR.iterdir()
                     if p.is_dir() and not p.name.startswith("localized"))
    if not folders:
        sys.exit(f"No site folders found in {config.DATA_DIR}")

    total = 0
    for folder in folders:
        wavs = sorted(w for w in folder.glob("*.wav")
                      if w.is_file() and "localized" not in str(w))
        if not wavs:
            continue

        print(f"\n-- {folder.name} ({len(wavs)} recordings) --")
        frames = []
        for i, wav in enumerate(wavs, 1):
            print(f"  [{i}/{len(wavs)}] {wav.name}")
            df = process_file(wav, species_filter, folder.name)
            if df is not None:
                frames.append(df)
            total += 1

        if frames:
            combined = pd.concat(frames, ignore_index=True)
            out = config.DATA_DIR / f"birdnet_{folder.name}.csv"
            combined.to_csv(out, index=False)
            print(f"  -> {out.name}: {len(combined)} detections")

    print(f"\nDone. Processed {total} recordings.")


if __name__ == "__main__":
    main()
