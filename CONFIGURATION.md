# Configuration

How to adapt HARKBirdNET to your own site, array and species. The shipped
defaults are specific to a woodland site in southeast England recorded with a
6-microphone MAARU array in September 2021 — **most of them will be wrong for
you.**

**Everything below lives in `harkbirdnet/config.py`**, except the HARKBird
localisation parameters, which live in HARKBird's own `parameter/default.json`.

Work through this before your first real run.

## Quick reference

| Setting | Where | Default | Change it if… |
| --- | --- | --- | --- |
| `DATA_DIR` | `config.py` §1 | `PROJECT_ROOT/Data` | **always** |
| `HARKBIRD_DIR` | `config.py` §1 | `PROJECT_ROOT/HARKBird_4.5` | installed elsewhere |
| `TRANSFER_FN` | `config.py` §1 | `tf_circular_6ch.zip` | **different array** |
| `LAT`, `LON` | `config.py` §2 | 51.4175, 0.1462 | **always** |
| `WEEK` | `config.py` §2 | 33 | **always** |
| `MIN_CONFIDENCE` | `config.py` §2 | 0.5 | rarely |
| `CHUNK_OVERLAP_S` | `config.py` §2 | 1.5 | rarely |
| `TEMPORAL_WINDOW` | `config.py` §3 | 600 s | different recording length |
| `AZIMUTH_WINDOW` | `config.py` §3 | 25° | **always** — array-specific |
| `AZIMUTH_COL` | `config.py` §3 | `azimuth_peak` | no (see note) |
| `CUTOFF_PATH` | `config.py` §3 | `OUTPUT_DIR/...csv` | thresholds stored elsewhere |
| `FILENAME_REGEX` | `config.py` §4 | MAARU convention | **different recorder** |
| `LOWER/UPPER_BOUND_FREQUENCY` | `parameter/default.json` | 2000 / 8000 Hz | different taxa |
| `NUM_SOURCE`, `PERIOD` | `parameter/default.json` | 1, 20 | rarely |

---

## BirdNET

Section 2 of `config.py`.

### Location and season

```python
LAT   = 51.4175    # decimal degrees
LON   = 0.1462
WEEK  = 36
```

BirdNET uses latitude, longitude and week to build a species filter, so only
plausible species for that place and time are eligible. This is a substantial
false-positive reduction — set it correctly.

**`WEEK` uses BirdNET's own indexing: values 1–48, with exactly four weeks per
month.** It is *not* an ISO week number. To convert a calendar date:

```
week = (month − 1) × 4 + min(4, ceil(day / 7))
```

So 5 September → `(9−1) × 4 + 1` = **33**. 25 September → `32 + 4` = **36**.

Set `WEEK = -1` for a year-round species list if your recordings span a long
period. If your dataset covers several months, either run `detect.py` once per
period with the appropriate week, or use `-1` and accept a broader filter.

> ⚠️ **Check this against your own data.** `WEEK = 33` is the *first* week of
> September; `WEEK = 36` is the fourth. This affects which species are eligible
> for detection at all, so it is worth getting right and reporting explicitly.

### Detection threshold

```python
MIN_CONFIDENCE = 0.5
```

This is a **floor**, not the final threshold. Confidence filtering happens in
two stages:

1. `detect.py` discards anything below `MIN_CONFIDENCE` (0.5). Deliberately
   permissive — it keeps enough marginal detections for ground-truthing.
2. `generate-pseudoindividuals.py` applies **per-species** cutoffs from
   `species_confidence_cutoffs_precision.csv`, derived from manual validation.

Lowering `MIN_CONFIDENCE` below 0.5 gives more to validate and slows everything
down. Raising it discards detections you may want for threshold derivation.
Leave it at 0.5 unless you have a reason.

Species absent from the cutoffs file are **dropped entirely** at stage 2. If a
species you expect is missing from the final output, check there first.

### Window overlap

```python
CHUNK_OVERLAP_S = 1.5
```

BirdNET analyses 3 s windows. A 1.5 s overlap means each moment is covered
twice, so a single call typically produces several detections at slightly
different times — and therefore several independent azimuth estimates. That
redundancy is what makes the clustering step work.

Reducing the overlap to 0 roughly halves runtime but gives one azimuth per
call, which measurably degrades clustering. Increasing it further gives
diminishing returns for linearly increasing runtime.

**Note:** overlap inflates raw detection counts. Never report raw counts as
call counts.

---

## Clustering

Section 3 of `config.py`.

```python
TEMPORAL_WINDOW = 600     # block length (seconds)
AZIMUTH_WINDOW  = 25      # cluster tolerance (degrees)
AZIMUTH_COL     = "azimuth_peak"
```

Each can also be overridden for a single run without editing the file:

```bash
python harkbirdnet/generate-pseudoindividuals.py --azimuth-window 30
```

### How the algorithm works

Within each species × time block, detections are grouped by direction:

1. Sort detections by descending confidence.
2. Walk down the list. If a detection is **more than `AZIMUTH_WINDOW` degrees
   from every existing seed**, it becomes a new seed.
3. Once seeding is done, assign every detection to its **nearest** seed.

Distances are circular, so 175° and −175° are 10° apart, not 350°.

Each resulting cluster is one **pseudo-individual** — an approximation, not a
verified bird. See
[`TECHNICAL_NOTES.md`](TECHNICAL_NOTES.md#what-a-cluster-is-and-isnt).

### `AZIMUTH_WINDOW` — the one you must change

**This should be derived from your array's measured localisation error, not
copied.** It is a radius, not a diameter: a cluster is bounded by
`AZIMUTH_WINDOW` degrees from its seed, so total width can approach twice that.

The shipped 25° is the **upper quartile of direction-of-arrival error** measured
for the MAARU array in pre-deployment trials. The reasoning: if three quarters
of estimates land within 25° of truth, then detections more than 25° apart are
more likely to be different birds than the same bird mis-localised.

To derive your own:

1. Play or place a known source at known bearings, at realistic distances.
2. Run it through `localise.py` and `detect.py`.
3. Compute circular error between estimated and true bearing.
4. Take the upper quartile.

The trade-off is direct and worth understanding:

- **Too small** → one bird whose direction estimate wanders gets split into
  several individuals. Overcounts.
- **Too large** → genuinely separate birds in similar directions merge.
  Undercounts.

Because seeds must be at least `AZIMUTH_WINDOW` apart, the maximum possible
clusters per species-block is `floor(360 / AZIMUTH_WINDOW)` — 14 at 25° on a
full circle, fewer if your array only covers an arc.

Assignment in step 3 has **no distance cap**: every detection joins its nearest
seed however far away it is. So no detection is discarded, but an outlier can
be absorbed into a cluster it doesn't belong to.

Run the pipeline at two or three values and report sensitivity. Output files are
suffixed with the value used (`_az25`), so runs don't overwrite each other.

### `TEMPORAL_WINDOW`

```python
TEMPORAL_WINDOW = 600
```

Detections are grouped into fixed blocks of this length, and **clustering resets
at every block boundary**. Birds are only ever compared with others in the same
block.

Set this to your recording length (600 s = 10 minutes here). Two consequences:

- A bird calling across a boundary is counted as an individual in each block.
  Counts are per-block, never summed across blocks as unique birds.
- Longer blocks let birds move further within a block, which inflates apparent
  individuals; shorter blocks give fewer detections per cluster and noisier
  estimates.

### `AZIMUTH_COL`

```python
AZIMUTH_COL = "azimuth_peak"
```

**Leave this as `azimuth_peak`.** The alternative, `azimuth_mean`, averages
angles arithmetically and is wrong at the ±180° wraparound — 170° and −170°
average to 0° instead of 180°. It is retained only for comparison.

### Per-species confidence cutoffs

`generate-pseudoindividuals.py` reads the CSV at `CUTOFF_PATH`, which needs
columns `species_common` and `cutoff_prec`. These come from manual validation:
sample
detections across the confidence range for each species, score them true or
false, and take the confidence at which precision reaches your target.

> **[PLACEHOLDER]** Ground-truthing workflow and target precision.

To skip this and use a single global threshold:

```bash
python harkbirdnet/generate-pseudoindividuals.py --global-cutoff 0.85
```

Simpler, less defensible — BirdNET confidence is not comparable across species.
Report which you used.

---

## HARKBird localisation

In `HARKBird_4.5/parameter/default.json`. Only four keys affect the MUSIC
spectrum this pipeline consumes.

```json
"LOWER_BOUND_FREQUENCY": 2000,
"UPPER_BOUND_FREQUENCY": 8000,
"PERIOD": 20,
"NUM_SOURCE": 1
```

**Frequency bounds** restrict localisation to the band where your target calls
sit. The 2000 Hz floor was raised from 1000 Hz after wind and handling noise
around 1 kHz was found to dominate the spectrum. Lower it for species calling
below 2 kHz (owls, doves, corvids), but expect more noise contamination.
The upper bound cannot exceed half your sample rate.

**`PERIOD`** is the localisation interval in frames. At 16 kHz with the fixed
160-sample advance, `PERIOD = 20` gives one spectrum frame every **0.200 s**.
Halving it doubles temporal resolution and roughly doubles file size and
runtime.

**`NUM_SOURCE`** is the MUSIC signal-subspace dimension. Left at 1 because the
pipeline takes a single peak direction per frame anyway.

Other keys in this file (`THRESH`, `PAUSE_LENGTH`, `MIN_SOURCE_INTERVAL`) affect
only `df_separated.csv`, which nothing downstream reads. `LOCFRAMES`, `MICNO`,
`TFNAME`, `PRE_LENGTH` and the `SEP_*` bounds are **not applied at all** in this
pipeline — see
[`TECHNICAL_NOTES.md`](TECHNICAL_NOTES.md#which-parameters-actually-reach-the-code).

### Transfer function

Set in section 1 of `config.py`:

```python
TRANSFER_FN = "transfer_function/tf_circular_6ch.zip"
```

This encodes your array's acoustic geometry and **must match your hardware**.
HARKBird ships transfer functions for 4-, 6- and 8-microphone circular arrays.
For a non-standard array you will need to measure or simulate your own — see the
HARK documentation.

A mismatched transfer function produces confident, wrong directions with no
error or warning.

---

## Filenames

`tidy.py` parses site and timestamp from the filename using `FILENAME_REGEX`
in section 4 of `config.py`. The default expects:

```
SITE-YYYY-MM-DD_HH-MM-SS_dur=Nsecs.wav
```

e.g. `ASNW-2021-09-05_12-09-30_dur=600secs.wav`, giving site `ASNW` and a
timestamp. Everything downstream needs `location`, `year`, `month`, `day`,
`hour`, `minute`, `second`.

If your recorder names files differently, rewrite `FILENAME_REGEX`. It must
produce named groups `location`, `year`, `month`, `day`, `hour`, `minute` and
`second`; `duration_s` is optional. `tidy.py` fails with a clear message and
lists example filenames if the pattern doesn't match, rather than misparsing
silently.

The rest of the pipeline is filename-agnostic — only this one step cares.

---

## Directory structure

`localise.py` and `detect.py` expect one subfolder per site-day inside
`DATA_DIR` (section 1 of `config.py`), each containing WAVs:

```
Data/
├── ASNW-2021-09-05/
│   ├── ASNW-2021-09-05_12-09-30_dur=600secs.wav
│   └── localized_ASNW-2021-09-05_12-09-30_dur=600secs.wav/
└── PAWS-2021-09-05/
```

Folders beginning `localized` are skipped automatically. For a flat directory
with no subfolders, adapt `find_wavs()` in `localise.py`.
