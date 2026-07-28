"""
flac_to_wav.py
==============
Convert FLAC recordings to WAV, preserving all channels.

HARK reads WAV, not FLAC. This walks DATA_DIR recursively, converts every
.flac to a .wav alongside it, and skips any that already exist so the script
can be re-run safely.

Source FLAC files are never deleted.

Usage
-----
    python harkbirdnet/flac_to_wav.py
"""

import subprocess
import sys

import config


def main():
    config.check_paths()

    flacs = sorted(config.DATA_DIR.rglob("*.flac"))
    if not flacs:
        print(f"No .flac files found under {config.DATA_DIR}")
        return

    print(f"Found {len(flacs)} FLAC files.\n")
    converted = skipped = failed = 0

    for i, flac in enumerate(flacs, 1):
        wav = flac.with_suffix(".wav")
        if wav.exists():
            skipped += 1
            continue

        print(f"[{i}/{len(flacs)}] {flac.name}")
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(flac), "-c:a", "pcm_s16le", str(wav)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  -> FAILED: {result.stderr.strip().splitlines()[-1:]}")
            wav.unlink(missing_ok=True)   # don't leave a truncated file behind
            failed += 1
        else:
            converted += 1

    print(f"\nConverted {converted}, skipped {skipped} (already present), "
          f"failed {failed}.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
