"""
tidy.py
=======
Parse site and timestamp out of recording filenames.

Port of tidy_birdnet_outputs.R. Reads OUTPUT_DIR/birdnet_all.csv and writes
OUTPUT_DIR/birdnet_all_tidy.csv, adding the columns everything downstream
needs to build timestamps and time blocks.

Input columns:  folder, filename, species_latin, species_common, confidence,
                time_start, time_end, azimuth_peak, azimuth_mean
Added columns:  file_path, location, year, month, day, hour, minute, second,
                duration.s
Removed:        folder, filename (folded into file_path)

This is the only recorder-specific step in the pipeline. If your filenames
differ, edit FILENAME_REGEX in config.py -- nothing else needs to change.

Usage
-----
    python harkbirdnet/tidy.py
"""

import re
import sys

import pandas as pd

import config


def parse_filename(name, pattern):
    """
    Extract fields from one filename, extension already removed.
    Returns a dict, or None if the name doesn't match.
    """
    m = pattern.match(name)
    return m.groupdict() if m else None


def main():
    in_path = config.OUTPUT_DIR / "birdnet_all.csv"
    out_path = config.OUTPUT_DIR / "birdnet_all_tidy.csv"

    if not in_path.exists():
        sys.exit(f"Not found: {in_path}\n  Run combine.py first.")

    data = pd.read_csv(in_path)
    for col in ("folder", "filename"):
        if col not in data.columns:
            sys.exit(f"ERROR: {in_path} has no '{col}' column.")

    pattern = re.compile(config.FILENAME_REGEX)

    # Strip the extension, then parse. Matches the R script's
    # str_remove(filename, "\\..*$").
    stems = data["filename"].astype(str).str.replace(r"\..*$", "", regex=True)
    parsed = [parse_filename(s, pattern) for s in stems]

    bad = [s for s, p in zip(stems, parsed) if p is None]
    if bad:
        unique_bad = sorted(set(bad))
        print(f"ERROR: {len(bad)} filenames did not match FILENAME_REGEX.",
              file=sys.stderr)
        print(f"  Pattern: {config.FILENAME_REGEX}", file=sys.stderr)
        print("  Examples that failed:", file=sys.stderr)
        for s in unique_bad[:5]:
            print(f"    {s}", file=sys.stderr)
        print("\n  Edit FILENAME_REGEX in config.py to match your recorder.",
              file=sys.stderr)
        sys.exit(1)

    fields = pd.DataFrame(parsed, index=data.index)

    out = data.copy()
    out["file_path"] = (out["folder"].astype(str) + "/" +
                        out["filename"].astype(str))
    out["location"] = fields["location"]
    for col in ("year", "month", "day", "hour", "minute", "second"):
        out[col] = fields[col].astype(int)
    # Column named duration.s to match the R output exactly.
    out["duration.s"] = pd.to_numeric(fields.get("duration_s"), errors="coerce")

    # Column order follows the R script's final select().
    lead = ["file_path", "location", "year", "month", "day", "hour", "minute",
            "second", "duration.s"]
    rest = [c for c in data.columns if c not in ("folder", "filename")]
    out = out[lead + rest]

    out.to_csv(out_path, index=False)
    print(f"Parsed {len(out)} detections from "
          f"{out['file_path'].nunique()} recordings")
    print(f"Sites: {', '.join(sorted(out['location'].unique()))}")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
