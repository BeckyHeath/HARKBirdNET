"""
config.py
=========
Central configuration for the HARKBirdNET pipeline.

**This is the only file you need to edit.** Every script imports its settings
from here.

Work through the four sections below before your first run. The defaults are
those used to develop the pipeline (a woodland site in southeast England, a
6-microphone MAARU array, September recordings) and most of them will be wrong
for you.

See docs/CONFIGURATION.md for what each setting does and how to choose a value.
"""

from pathlib import Path

# =============================================================================
# 1. PATHS
# =============================================================================

# Repository root, resolved automatically. Don't edit.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Where your recordings live. One subfolder per site-day, each containing WAVs:
#
#     Data/
#     ├── SITE-2021-09-05/
#     │   └── SITE-2021-09-05_08-00-00_dur=600secs.wav
#     └── SITE-2021-09-06/
#
# This can point anywhere -- audio does not need to sit inside the repository,
# and generally shouldn't. Use an absolute path if it lives elsewhere, e.g.
#     DATA_DIR = Path("/media/external/recordings")
DATA_DIR = PROJECT_ROOT / "Data"

# Where combined tables and clustering results are written.
OUTPUT_DIR = PROJECT_ROOT / "Output"

# Your unzipped HARKBird 4.5 installation, with the GHDSS patch applied.
# Must contain hb_pyhark.py, parameter/ and transfer_function/.
HARKBIRD_DIR = PROJECT_ROOT / "HARKBird_4.5"

# Transfer function and parameter file, relative to HARKBIRD_DIR.
#
# TRANSFER_FN MUST MATCH YOUR ARRAY. It encodes the microphone geometry.
# A mismatched transfer function produces confident, wrong directions with no
# warning. HARKBird ships 4-, 6- and 8-microphone circular array functions.
TRANSFER_FN = "transfer_function/tf_circular_6ch.zip"
PARAM_FILE = "parameter/default.json"


# =============================================================================
# 2. BIRDNET
# =============================================================================

# Recording location, decimal degrees. Used to build a species filter so only
# plausible species for your location and season are eligible.
LAT = 51.4175
LON = 0.1462

# BirdNET week index: 1-48, FOUR WEEKS PER MONTH. Not an ISO week number.
#
#     week = (month - 1) * 4 + min(4, ceil(day / 7))
#
# So 5 September -> 33, and 25 September -> 36.
# Set to -1 for a year-round species list if recordings span a long period.
WEEK = 33

# Minimum BirdNET confidence to retain. This is a FLOOR, not the final
# threshold -- per-species ground-truthed cutoffs are applied later, during
# clustering. Keeping this permissive preserves the marginal detections needed
# to derive those cutoffs.
MIN_CONFIDENCE = 0.5

# Overlap between BirdNET's 3 s analysis windows, in seconds. The redundancy
# gives several independent azimuth estimates per call, which is what makes
# clustering work. Reducing to 0 roughly halves runtime and measurably degrades
# clustering.
CHUNK_OVERLAP_S = 1.5


# =============================================================================
# 3. CLUSTERING
# =============================================================================

# Block length in seconds. Detections are grouped into fixed blocks and
# clustering RESETS at every boundary -- birds are only ever compared within a
# block. Set this to your recording length.
TEMPORAL_WINDOW = 600

# Cluster tolerance in degrees. THIS IS ARRAY-SPECIFIC AND SHOULD BE
# RE-DERIVED FOR YOUR HARDWARE.
#
# It is a RADIUS from the cluster seed, not a diameter, so cluster width can
# approach twice this value.
#
# Playback trials with the MAARU array (n=52, 1-8 m) gave a median error of
# 0 degrees and 92.3% of estimates within 10 degrees. The remaining 7.7% were
# off by 100 degrees or more, with nothing in between -- the error
# distribution is bimodal. 25 degrees covers the well-behaved mode with
# margin, and leaves room for the bird to move within a block. It cannot help
# with the catastrophic mode, which seeds a spurious individual regardless.
#
# Too small overcounts (one wandering bird splits); too large undercounts
# (separate birds merge). See docs/CONFIGURATION.md for how to measure yours.
AZIMUTH_WINDOW = 25

# Which azimuth estimate to cluster on. Leave as "azimuth_peak".
# "azimuth_mean" averages angles arithmetically and is wrong at the +/-180
# wraparound; it is retained only for comparison.
AZIMUTH_COL = "azimuth_peak"

# Per-species confidence thresholds from manual validation. CSV with columns
# species_common and cutoff_prec. Species absent from this file are DROPPED
# ENTIRELY. See the notes in generate-pseudoindividuals.py, or run that script
# with --global-cutoff to use one flat threshold instead.
CUTOFF_PATH = OUTPUT_DIR / "species_confidence_cutoffs_precision.csv"


# =============================================================================
# 4. FILENAMES
# =============================================================================

# How to read site and timestamp out of a recording filename. This is the only
# genuinely recorder-specific part of the pipeline.
#
# The default matches MAARU's convention:
#     ASNW-2021-09-05_12-09-30_dur=600secs.wav
#      |    |          |          |
#      site date       time       duration
#
# If your recorder names files differently, rewrite this regex. It must
# produce these named groups: location, year, month, day, hour, minute,
# second. The duration_s group is optional.
#
# Everything downstream needs year/month/day/hour/minute/second to build
# timestamps and time blocks, so those seven are required.
FILENAME_REGEX = (
    r"^(?P<location>[^-]+)"
    r"-(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})"
    r"_(?P<hour>\d{2})-(?P<minute>\d{2})-(?P<second>\d{2})"
    r"(?:_dur=(?P<duration_s>\d+)secs)?$"
)


# =============================================================================
# Internal
# =============================================================================

# Suffix appended to clustering outputs so runs at different tolerances don't
# overwrite each other, e.g. individuals_top_call_az25.csv
AZ_SUFFIX = f"_az{AZIMUTH_WINDOW:g}"


def check_paths(need_data=True, need_harkbird=False):
    """Fail early and clearly if a configured path doesn't exist."""
    import sys

    problems = []
    if need_data and not DATA_DIR.is_dir():
        problems.append(f"DATA_DIR does not exist: {DATA_DIR}")
    if need_harkbird:
        if not HARKBIRD_DIR.is_dir():
            problems.append(f"HARKBIRD_DIR does not exist: {HARKBIRD_DIR}")
        else:
            for rel in (TRANSFER_FN, PARAM_FILE, "hb_pyhark.py"):
                if not (HARKBIRD_DIR / rel).exists():
                    problems.append(f"missing from HARKBIRD_DIR: {rel}")
    if problems:
        print("Configuration problem:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("\nEdit harkbirdnet/config.py.", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
