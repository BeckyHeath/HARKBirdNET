"""
localise.py
===========
HARK MUSIC sound source localisation over a directory of multichannel WAVs.

For each recording, writes into localized_<filename>/ alongside the input:

    spectrum.txt       MUSIC spectrum, time x 72 azimuths -- the only output
                       the rest of the pipeline consumes
    remixed.wav        mono mixdown
    df_separated.csv   HARK source tracks (not used downstream)
    visualisation.png  spectrogram + aziogram

Memory
------
Each recording runs in an ISOLATED SUBPROCESS rather than a direct function
call. This is not a stylistic choice. PyHARK holds C++-side state that Python's
garbage collector cannot release, so calling localize_separate() in a loop
leaks memory until the kernel kills the process -- observed at 12.7 GB after
roughly 18 ten-minute 6-channel files. A fresh interpreter per file returns
memory to baseline.

**Keep the subprocess isolation if you adapt this script.**

You must also apply patches/disable_ghdss.patch to HARKBird first; see the
README. Without it, source separation spikes memory on every file.

Resuming
--------
Recordings whose spectrum.txt already exists are skipped, so an interrupted
batch can be restarted safely.

Usage
-----
    python harkbirdnet/localise.py
"""

import subprocess
import sys
from pathlib import Path

import config

SCRIPT_DIR = Path(__file__).resolve().parent

# Worker executed as a subprocess, one per recording.
WORKER = """
import os, sys
sys.path.insert(0, {harkbird_dir!r})
sys.path.insert(0, {script_dir!r})
os.chdir({harkbird_dir!r})

import hb_pyhark
import visualise

workingdir    = {workingdir!r}
filename      = {filename!r}
localized_dir = os.path.join(workingdir, "localized_" + filename)

hb_pyhark.localize_separate(
    workingdir=workingdir,
    filename=filename,
    filename_tf={transfer_fn!r},
    paramfilename={param_file!r},
)
print("LOCALISATION_DONE")

visualise.plot_harkbird(
    localized_dir, output_path=os.path.join(localized_dir, "visualisation.png"))
print("VISUALISATION_DONE")
"""


def find_wavs():
    """
    All WAVs in immediate subfolders of DATA_DIR.

    Excludes HARKBird's own output: directories named localized_*.wav would
    otherwise be matched by a glob, and remixed.wav sits inside them.
    """
    wavs = []
    for folder in sorted(p for p in config.DATA_DIR.iterdir() if p.is_dir()):
        if folder.name.startswith("localized"):
            continue
        for wav in sorted(folder.glob("*.wav")):
            if wav.is_file() and "localized" not in str(wav):
                wavs.append(wav)
    return wavs


def already_done(wav):
    """
    True if this recording has a usable spectrum.

    Checks for spectrum.txt rather than merely the output directory: a run
    interrupted mid-file leaves the directory present but empty, and a
    directory-only check would skip it forever.
    """
    return (wav.parent / f"localized_{wav.name}" / "spectrum.txt").exists()


def process(wav):
    script = WORKER.format(
        harkbird_dir=str(config.HARKBIRD_DIR),
        script_dir=str(SCRIPT_DIR),
        workingdir=str(wav.parent) + "/",
        filename=wav.name,
        transfer_fn=config.TRANSFER_FN,
        param_file=config.PARAM_FILE,
    )
    return subprocess.run([sys.executable, "-c", script]).returncode == 0


def main():
    config.check_paths(need_harkbird=True)

    wavs = find_wavs()
    if not wavs:
        sys.exit(f"No WAV files found in subfolders of {config.DATA_DIR}")

    print(f"Found {len(wavs)} recordings.\n")
    done = errors = 0

    for i, wav in enumerate(wavs, 1):
        print(f"[{i}/{len(wavs)}] {wav.name}")
        if already_done(wav):
            print("  -> already localised, skipping\n")
            continue
        if process(wav):
            done += 1
            print("  -> done\n")
        else:
            errors += 1
            print("  -> ERROR (see output above)\n")

    print(f"Localised {done}, {errors} errors.")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
