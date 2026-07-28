"""
combine.py
==========
Bind the per-folder BirdNET tables written by detect.py into one file.

Input:  DATA_DIR/birdnet_<folder>.csv
Output: OUTPUT_DIR/birdnet_all.csv

Usage
-----
    python harkbirdnet/combine.py
"""

import sys

import pandas as pd

import config


def main():
    config.check_paths()

    files = sorted(config.DATA_DIR.glob("birdnet_*.csv"))
    if not files:
        sys.exit(
            f"No birdnet_*.csv files in {config.DATA_DIR}\n"
            f"  Run detect.py first."
        )

    frames = []
    for f in files:
        df = pd.read_csv(f)
        if df.empty:
            print(f"  {f.name}: empty, skipped")
            continue
        frames.append(df)
        print(f"  {f.name}: {len(df)} rows")

    if not frames:
        sys.exit("All input files were empty.")

    combined = pd.concat(frames, ignore_index=True)
    out = config.OUTPUT_DIR / "birdnet_all.csv"
    combined.to_csv(out, index=False)
    print(f"\nWrote {len(combined)} rows from {len(frames)} files to {out}")


if __name__ == "__main__":
    main()
