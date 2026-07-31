#!/usr/bin/env python3
"""
generate-pseudoindividuals.py
=============================
Group BirdNET detections into DOA-approximated individuals ("pseudo-individuals").

This is a direct port of the data-generation stage of
`cluster-calls-groundtruth_new.R` (lines 61-169). It reproduces the same three
output tables. Figures and statistical tests are deliberately not ported --
those belong in the downstream analysis repository.

Method
------
For each species within each fixed time block, detections are clustered by
direction of arrival:

  1. Sort detections by descending confidence.
  2. Walk the sorted list. A detection more than AZIMUTH_WINDOW degrees from
     every existing seed becomes a new seed.
  3. Assign every detection to its nearest seed (circular distance, no cap).

Each cluster is one pseudo-individual. See docs/TECHNICAL_NOTES.md for what
that does and does not mean.

Inputs
------
  birdnet_all_tidy.csv                        (from tidy.py)
  species_confidence_cutoffs_precision.csv    (from ground-truthing; see below)

Outputs
-------
  individuals_top_call_az<N>.csv    one row per individual (highest-confidence
                                    call), plus n_calls
  individuals_per_block_az<N>.csv   one row per individual, with call count
  individuals_at_once_az<N>.csv     individuals per species per block

Usage
-----
    python generate-pseudoindividuals.py
    python generate-pseudoindividuals.py --azimuth-window 30
    python generate-pseudoindividuals.py --global-cutoff 0.85
    python generate-pseudoindividuals.py --verify-against ../R_output/

Author
------
    Becky Heath, Imperial College London / Natural History Museum London
"""

import argparse
import os
import re
import sys

import numpy as np
import pandas as pd

import config

# All settings live in config.py. The command-line flags below override them
# for one run, which is useful for sensitivity checks.
ALL_PATH        = config.OUTPUT_DIR / "birdnet_all_tidy.csv"
CUTOFF_PATH     = config.CUTOFF_PATH
OUTPUT_DIR      = config.OUTPUT_DIR
TEMPORAL_WINDOW = config.TEMPORAL_WINDOW
AZIMUTH_WINDOW  = config.AZIMUTH_WINDOW
AZIMUTH_COL     = config.AZIMUTH_COL


# =============================================================================
# Ground-truth confidence thresholds
# =============================================================================
#
# BirdNET confidence is NOT comparable across species: a Wren at 0.7 and a
# Parakeet at 0.7 do not carry the same probability of being correct. Applying
# one global threshold therefore over-filters some species and under-filters
# others.
#
# This pipeline instead expects a per-species threshold derived from manual
# validation, supplied as a CSV with (at minimum) these two columns:
#
#     species_common,cutoff_prec
#     Eurasian Wren,0.6543
#     Great Tit,0.7211
#     ...
#
#   species_common  must match the BirdNET common name exactly, as it appears
#                   in birdnet_all_tidy.csv
#   cutoff_prec     minimum confidence to retain for that species
#
# HOW TO DERIVE THE CUTOFFS
# -------------------------
#   1. Sample detections per species spread across the confidence range
#      (select_subset.py does this).
#   2. Have a human score each as correct / incorrect by listening.
#   3. For each species, find the lowest confidence at which precision
#      (true positives / all detections above that confidence) meets your
#      target. That value is cutoff_prec.
#   4. Write one row per species.
#
# TWO IMPORTANT CONSEQUENCES
# --------------------------
#   * Species ABSENT from the cutoffs file are DROPPED ENTIRELY (inner join).
#     This is intentional -- a species with no validated threshold has no
#     defensible inclusion rule. If a species you expect is missing from the
#     output, check this file first. The script warns about dropped species.
#   * Rows with a blank cutoff_prec are ignored, which also drops that species.
#
# IF YOU HAVE NOT GROUND-TRUTHED YET
# ----------------------------------
# Run with --global-cutoff 0.85 to apply one flat threshold to every species.
# This lets the pipeline run end to end, but it is substantially weaker and
# should not be used for publication. Report which you used.

DEFAULT_GLOBAL_CUTOFF = 0.85


# =============================================================================
# Clustering
# =============================================================================

def circ_dist(a, b):
    """
    Circular angular distance in degrees, over the shorter arc.

    Mirrors circ_dist() in the R script:
        d <- abs(a - b) %% 360
        pmin(d, 360 - d)

    So 175 and -175 are 10 degrees apart, not 350.
    """
    d = np.abs(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)) % 360.0
    return np.minimum(d, 360.0 - d)


def assign_individuals(df, tol):
    """
    Greedy, confidence-ordered seeding on the circular DOA axis.

    Direct port of assign_individuals() in the R script. Returns df with an
    added 1-based `individual_idx` column.

    Two details are load-bearing for matching the R output exactly:

      * The confidence sort must be STABLE. R's order() uses a radix sort for
        doubles, so equal-confidence detections keep their original relative
        order and therefore seed in the same sequence. numpy's "stable" kind
        gives the same guarantee.
      * Nearest-seed assignment uses argmin, which returns the FIRST minimum on
        a tie -- matching R's which.min().
    """
    if len(df) == 0:
        out = df.copy()
        out["individual_idx"] = pd.Series([], dtype="int64")
        return out

    az_all = df["azimuth"].to_numpy(dtype=float)
    conf = df["confidence"].to_numpy(dtype=float)

    # order(-confidence) -> descending, stable
    order = np.argsort(-conf, kind="stable")

    seeds = []
    for i in order:
        az = az_all[i]
        if len(seeds) == 0 or np.all(circ_dist(np.array(seeds), az) > tol):
            seeds.append(az)

    seeds = np.array(seeds, dtype=float)

    # which.min(circ_dist(seeds, az)) for each detection, 1-based
    dists = circ_dist(seeds[None, :], az_all[:, None])   # (n_detections, n_seeds)
    idx = np.argmin(dists, axis=1) + 1

    out = df.copy()
    out["individual_idx"] = idx.astype("int64")
    return out


def species_tag(name):
    """Runs of non-alphanumeric characters become a single hyphen."""
    return re.sub(r"[^A-Za-z0-9]+", "-", str(name))


# =============================================================================
# Pipeline
# =============================================================================

GROUP_KEYS = ["site", "species_latin", "species_common", "block"]


def load_and_filter(all_path, cutoff_path, temporal_window,
                    global_cutoff=None):
    """Load detections and apply the confidence filter."""

    data = pd.read_csv(all_path)

    required = {"location", "species_latin", "species_common", "confidence",
                "year", "month", "day", "hour", "minute", "second",
                "time_start", "time_end", AZIMUTH_COL}
    missing = required - set(data.columns)
    if missing:
        sys.exit(f"ERROR: {all_path} is missing required columns: "
                 f"{', '.join(sorted(missing))}")

    # ---- Confidence filter ---------------------------------------------------
    n_before = len(data)
    species_before = set(data["species_common"].unique())

    if global_cutoff is not None:
        data = data[data["confidence"] >= global_cutoff].copy()
        print(f"Confidence filter  : global cutoff {global_cutoff} -> "
              f"{len(data)} detections")
        print("  WARNING: a single global cutoff ignores between-species "
              "differences in BirdNET calibration.")
    else:
        if not os.path.exists(cutoff_path):
            sys.exit(
                f"ERROR: cutoffs file not found: {cutoff_path}\n"
                f"  See the notes at the top of this script, or run with\n"
                f"    --global-cutoff {DEFAULT_GLOBAL_CUTOFF}\n"
                f"  to use one flat threshold instead (weaker; not for "
                f"publication)."
            )
        cutoffs = pd.read_csv(cutoff_path)
        for col in ("species_common", "cutoff_prec"):
            if col not in cutoffs.columns:
                sys.exit(f"ERROR: {cutoff_path} has no '{col}' column.")
        cutoffs = (cutoffs[["species_common", "cutoff_prec"]]
                   .dropna(subset=["cutoff_prec"]))

        # inner join: species absent from the cutoffs file are dropped
        data = data.merge(cutoffs, on="species_common", how="inner")
        data = data[data["confidence"] >= data["cutoff_prec"]]
        data = data.drop(columns=["cutoff_prec"]).copy()

        dropped = sorted(species_before - set(cutoffs["species_common"]))
        print(f"Confidence filter  : per-species cutoffs -> "
              f"{len(data)} detections (from {n_before})")
        if dropped:
            print(f"  {len(dropped)} species dropped (no cutoff supplied): "
                  f"{', '.join(dropped[:8])}"
                  f"{' ...' if len(dropped) > 8 else ''}")

    if len(data) == 0:
        sys.exit("ERROR: no detections survived filtering.")

    # ---- Time and azimuth ----------------------------------------------------
    # R builds a POSIXct in UTC then takes as.numeric() -> epoch seconds.
    rec_start = pd.to_datetime(
        data["year"].map("{:04d}".format) + "-" +
        data["month"].map("{:02d}".format) + "-" +
        data["day"].map("{:02d}".format) + " " +
        data["hour"].map("{:02d}".format) + ":" +
        data["minute"].map("{:02d}".format) + ":" +
        data["second"].map("{:02d}".format),
        format="%Y-%m-%d %H:%M:%S", utc=True,
    )
    # Epoch seconds. Do NOT use .astype("int64") // 10**9 -- that assumes
    # nanosecond resolution, and pandas >= 3.0 returns datetime64[us] here,
    # which silently gives a result 1000x too small.
    rec_start_epoch = ((rec_start - pd.Timestamp("1970-01-01", tz="UTC"))
                       // pd.Timedelta("1s"))
    mid_offset = (data["time_start"] + data["time_end"]) / 2.0
    data_time_epoch = rec_start_epoch + mid_offset

    data = data.assign(
        site=data["location"],
        rec_start=rec_start,
        data_time=pd.to_datetime(data_time_epoch, unit="s", utc=True),
        azimuth=data[AZIMUTH_COL],
        block=np.floor(data_time_epoch / temporal_window).astype("int64"),
    )
    return data


def build_individuals(raw_calls, azimuth_window):
    """Stage C: cluster into pseudo-individuals."""

    # dplyr's group_by() sorts groups; group_modify() puts group keys first.
    parts = []
    for _, grp in raw_calls.groupby(GROUP_KEYS, sort=True):
        parts.append(assign_individuals(grp, tol=azimuth_window))
    individuals = pd.concat(parts, ignore_index=True)

    tags = individuals["species_common"].map(species_tag)
    individuals = individuals.assign(
        species_tag=tags,
        individual_id=(tags + "_" + individuals["site"].astype(str) +
                       "_b" + individuals["block"].astype(str) +
                       "_i" + individuals["individual_idx"].astype(str)),
    )

    # Reorder to match group_modify(): group keys first, then the rest.
    rest = [c for c in individuals.columns if c not in GROUP_KEYS]
    individuals = individuals[GROUP_KEYS + rest]
    return individuals


def summarise(individuals):
    """The three output tables."""

    id_keys = GROUP_KEYS + ["individual_id"]

    # One row per individual, with call count
    individuals_summary = (individuals
                           .groupby(id_keys, sort=True, as_index=False)
                           .size()
                           .rename(columns={"size": "n_calls"}))

    # Individuals per species-block
    block_individuals = (individuals
                         .groupby(GROUP_KEYS, sort=True, as_index=False)
                         .agg(n_individuals=("individual_id", "nunique")))

    # Highest-confidence call per individual.
    # slice_max(n = 1, with_ties = FALSE) keeps the first row after a stable
    # descending sort, so ties resolve to whichever appeared first.
    ordered = individuals.sort_values("confidence", ascending=False,
                                      kind="stable")
    individuals_top = (ordered
                       .groupby(id_keys, sort=True, as_index=False)
                       .head(1))
    individuals_top = (individuals_top
                       .sort_values(id_keys, kind="stable")
                       .reset_index(drop=True))
    individuals_top = individuals_top.merge(individuals_summary, on=id_keys,
                                            how="left")

    return individuals_summary, block_individuals, individuals_top


def write_outputs(output_dir, az_suffix, individuals_summary,
                  block_individuals, individuals_top):
    os.makedirs(output_dir, exist_ok=True)

    def _write(df, name):
        path = os.path.join(output_dir, f"{name}{az_suffix}.csv")
        out = df.copy()
        # readr::write_csv renders POSIXct as ISO 8601 UTC
        for col in out.columns:
            if pd.api.types.is_datetime64_any_dtype(out[col]):
                out[col] = out[col].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        out.to_csv(path, index=False)
        print(f"  wrote {path}  ({len(out)} rows)")
        return path

    _write(individuals_top, "individuals_top_call")
    _write(individuals_summary, "individuals_per_block")
    _write(block_individuals, "individuals_at_once")


def print_summaries(raw_calls, individuals_summary, block_individuals):
    print("\n=====================  SUMMARY TABLES  =====================")

    summary_site = (raw_calls.groupby("site", as_index=False)
                    .size().rename(columns={"size": "detections"})
                    .merge(individuals_summary.groupby("site", as_index=False)
                           .size().rename(columns={"size": "individuals"}),
                           on="site", how="left")
                    .merge(block_individuals.groupby("site", as_index=False)
                           .size().rename(columns={"size": "species_blocks"}),
                           on="site", how="left"))
    print("\n--- Detections, individuals and species-blocks per site ---")
    print(summary_site.to_csv(index=False), end="")

    summary_species = (individuals_summary
                       .groupby(["species_common", "site"], as_index=False)
                       .agg(individuals=("individual_id", "size"),
                            calls=("n_calls", "sum")))
    summary_species = summary_species.pivot(index="species_common",
                                            columns="site",
                                            values=["individuals", "calls"])
    summary_species.columns = [f"{a}_{b}" for a, b in summary_species.columns]
    summary_species = summary_species.fillna(0).astype("int64").reset_index()
    ind_cols = [c for c in summary_species.columns
                if c.startswith("individuals_")]
    summary_species = (summary_species
                       .assign(_tot=summary_species[ind_cols].sum(axis=1))
                       .sort_values("_tot", ascending=False, kind="stable")
                       .drop(columns="_tot"))
    print("\n--- Per-species individuals and calls by site ---")
    print(summary_species.to_csv(index=False), end="")


# =============================================================================
# Verification against the R output
# =============================================================================

def verify_against(r_dir, output_dir, az_suffix):
    """
    Compare this script's output with the R script's, ignoring row order and
    column order. Reports the first differences found rather than just pass/fail.
    """
    print("\n=====================  VERIFICATION  =====================")
    names = ["individuals_top_call", "individuals_per_block",
             "individuals_at_once"]
    all_ok = True

    for name in names:
        r_path = os.path.join(r_dir, f"{name}{az_suffix}.csv")
        py_path = os.path.join(output_dir, f"{name}{az_suffix}.csv")
        if not os.path.exists(r_path):
            print(f"  {name}: SKIP (no R output at {r_path})")
            continue

        r = pd.read_csv(r_path)
        p = pd.read_csv(py_path)

        if len(r) != len(p):
            print(f"  {name}: ROW COUNT DIFFERS  R={len(r)}  py={len(p)}")
            all_ok = False
            continue

        only_r = sorted(set(r.columns) - set(p.columns))
        only_p = sorted(set(p.columns) - set(r.columns))
        if only_r or only_p:
            print(f"  {name}: COLUMN MISMATCH")
            if only_r:
                print(f"      only in R : {only_r}")
            if only_p:
                print(f"      only in py: {only_p}")
            all_ok = False

        shared = [c for c in r.columns if c in p.columns]
        key = [c for c in ("site", "species_common", "block", "individual_id")
               if c in shared]
        r_s = r[shared].sort_values(key, kind="stable").reset_index(drop=True)
        p_s = p[shared].sort_values(key, kind="stable").reset_index(drop=True)

        diffs = []
        for c in shared:
            a, b = r_s[c], p_s[c]
            if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
                same = np.isclose(a.astype(float), b.astype(float),
                                  rtol=0, atol=1e-9, equal_nan=True)
            else:
                same = a.astype(str).values == b.astype(str).values
            n_bad = int((~same).sum())
            if n_bad:
                diffs.append((c, n_bad))

        if diffs:
            all_ok = False
            print(f"  {name}: {len(diffs)} column(s) differ")
            for c, n_bad in diffs[:6]:
                print(f"      {c}: {n_bad} / {len(r_s)} rows differ")
        else:
            print(f"  {name}: MATCH ({len(r)} rows, {len(shared)} columns)")

    print("\n  " + ("ALL OUTPUTS MATCH" if all_ok else
                    "DIFFERENCES FOUND -- see above"))
    return all_ok


# =============================================================================
# Main
# =============================================================================

def main():
    ap = argparse.ArgumentParser(
        description="Cluster BirdNET detections into DOA pseudo-individuals.")
    ap.add_argument("--all-path", default=str(ALL_PATH))
    ap.add_argument("--cutoffs", default=str(CUTOFF_PATH))
    ap.add_argument("--global-cutoff", type=float, default=None,
                    help=f"Use one flat confidence threshold (e.g. "
                         f"{DEFAULT_GLOBAL_CUTOFF}) instead of per-species "
                         f"ground-truthed cutoffs. Weaker; not for publication.")
    ap.add_argument("--output-dir", default=str(OUTPUT_DIR))
    ap.add_argument("--azimuth-window", type=float, default=AZIMUTH_WINDOW)
    ap.add_argument("--temporal-window", type=float, default=TEMPORAL_WINDOW)
    ap.add_argument("--verify-against", default=None, metavar="DIR",
                    help="Directory holding the R script's CSVs, to compare.")
    args = ap.parse_args()

    az_window = args.azimuth_window
    temporal_window = args.temporal_window
    az_suffix = f"_az{az_window:g}"

    print(f"azimuth_window   : {az_window} deg")
    print(f"temporal_window  : {temporal_window} s")
    print(f"azimuth_col      : {AZIMUTH_COL}")
    print()

    raw_calls = load_and_filter(
        args.all_path, args.cutoffs,
        temporal_window=temporal_window,
        global_cutoff=args.global_cutoff,
    )

    individuals = build_individuals(raw_calls, az_window)
    individuals_summary, block_individuals, individuals_top = summarise(individuals)

    print(f"\nStage C: {len(individuals_summary)} individuals across "
          f"{len(block_individuals)} species-blocks")

    write_outputs(args.output_dir, az_suffix, individuals_summary,
                  block_individuals, individuals_top)

    print_summaries(raw_calls, individuals_summary, block_individuals)

    if args.verify_against:
        ok = verify_against(args.verify_against, args.output_dir, az_suffix)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
