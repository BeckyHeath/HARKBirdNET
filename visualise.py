"""
visualise.py
============
Two-panel figure for one HARKBird output directory: spectrogram on top,
aziogram (MUSIC spectrum) below, with HARK's own DOA tracks overlaid.

Called automatically by localise.py for every recording. Can also be run
standalone on a single localized_*/ directory.

Usage
-----
    python harkbirdnet/visualise.py path/to/localized_recording.wav/
    python harkbirdnet/visualise.py path/to/localized_recording.wav/ --save fig.png
"""

import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import soundfile as sf
import pandas as pd
import argparse

def plot_harkbird(localized_dir, output_path=None):
    """
    Plot spectrogram + aziogram for a HARKBird localised output directory.

    Args:
        localized_dir: path to localized_*.wav directory
        output_path: optional path to save figure (if None, displays interactively)
    """

    # ── Load files ────────────────────────────────────────────────────────────
    remixed_path  = os.path.join(localized_dir, "remixed.wav")
    spectrum_path = os.path.join(localized_dir, "spectrum.txt")
    csv_path      = os.path.join(localized_dir, "df_separated.csv")

    if not os.path.exists(remixed_path):
        print(f"Missing remixed.wav in {localized_dir}")
        return
    if not os.path.exists(spectrum_path):
        print(f"Missing spectrum.txt in {localized_dir}")
        return

    # Load audio
    audio, rate = sf.read(remixed_path)
    if audio.ndim > 1:
        audio = audio[:, 0]

    # Load MUSIC spectrum
    # spectrum.txt is (time_frames x 72_azimuths) — rows=time, cols=azimuth
    music_spec_raw = np.loadtxt(spectrum_path, delimiter="\t")
    # Transpose to (azimuth x time) for plotting
    music_spec = music_spec_raw.T

    # Load detections if available
    detections = None
    if os.path.exists(csv_path):
        try:
            detections = pd.read_csv(csv_path)
        except Exception as e:
            print(f"Could not load detections: {e}")

    # ── Compute spectrogram ───────────────────────────────────────────────────
    from numpy.fft import rfft
    from numpy.lib.stride_tricks import sliding_window_view

    frame_size = 512
    advance    = 160
    frames  = sliding_window_view(audio, frame_size)[::advance]
    window  = np.hanning(frame_size)
    spec    = np.abs(rfft(frames * window, axis=1)).T
    spec_db = 20 * np.log10(spec + 1e-10)

    # ── Time / frequency axes ─────────────────────────────────────────────────
    duration       = len(audio) / rate
    n_spec_frames  = spec.shape[1]
    n_music_frames = music_spec.shape[1]

    spec_times  = np.linspace(0, duration, n_spec_frames)
    music_times = np.linspace(0, duration, n_music_frames)
    freqs       = np.linspace(0, rate / 2, spec.shape[0])  # Hz

    # 72 HARK directions: 5 degree steps from -180 to 175
    n_az     = music_spec.shape[0]
    azimuths = np.linspace(-180, 175, n_az)

    # ── Plot ──────────────────────────────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 8), sharex=True)
    fig.suptitle(os.path.basename(localized_dir), fontsize=11, fontweight='bold')

    # --- Top: Spectrogram ---
    vmin = np.percentile(spec_db, 30)
    vmax = np.percentile(spec_db, 99.5)
    ax1.pcolormesh(spec_times, freqs, spec_db,
                   cmap='Blues_r', vmin=vmin, vmax=vmax, shading='auto')
    ax1.set_ylabel("Frequency (Hz)")
    ax1.set_ylim(0, rate / 2)
    ax1.set_title("Spectrogram")

    # --- Bottom: Aziogram ---
    # Use raw values not dB to match old HARKBird style
    vmin2 = np.percentile(music_spec, 50)
    vmax2 = np.percentile(music_spec, 99.5)
    ax2.pcolormesh(music_times, azimuths, music_spec,
                   cmap='Blues_r', vmin=vmin2, vmax=vmax2, shading='auto')
    ax2.set_ylabel("Azimuth (°)")
    ax2.set_xlabel("Time (s)")
    ax2.set_ylim(-180, 180)
    ax2.set_yticks(np.arange(-180, 181, 45))
    ax2.set_title("Aziogram (MUSIC spectrum)")

    # Overlay DOA detections as black lines
    if detections is not None and len(detections) > 0:
        try:
            for _, row in detections.iterrows():
                ax2.plot([row['begin'], row['end']],
                         [row['doa_begin'], row['doa_begin']],
                         color='black', linewidth=1.5, alpha=0.8)
        except Exception as e:
            print(f"Could not overlay detections: {e}")

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"Saved to {output_path}")
    else:
        plt.show()


def main():
    parser = argparse.ArgumentParser(description="Visualise HARKBird output")
    parser.add_argument("localized_dir", help="Path to localized_*.wav directory")
    parser.add_argument("--save", help="Save figure to this path instead of displaying", default=None)
    args = parser.parse_args()

    plot_harkbird(args.localized_dir, output_path=args.save)


if __name__ == "__main__":
    main()
