# Configuration

Everything is set in `harkbirdnet/config.py`, except HARKBird's localisation
parameters which live in its own `parameter/default.json`.

The defaults come from a woodland site in southeast England recorded with a
6-microphone MAARU array. **Most will be wrong for you.**

## Quick reference

| Setting | Section | Default | Change it |
| --- | --- | --- | --- |
| `DATA_DIR` | 1 | `PROJECT_ROOT/Data` | **always** |
| `HARKBIRD_DIR` | 1 | `PROJECT_ROOT/HARKBird_4.5` | if installed elsewhere |
| `TRANSFER_FN` | 1 | `tf_circular_6ch.zip` | **different array** |
| `LAT`, `LON`, `WEEK` | 2 | 51.4175, 0.1462, 33 | **always** |
| `MIN_CONFIDENCE` | 2 | 0.5 | rarely |
| `CHUNK_OVERLAP_S` | 2 | 1.5 | rarely |
| `TEMPORAL_WINDOW` | 3 | 600 s | different recording length |
| `AZIMUTH_WINDOW` | 3 | 25° | **different array** |
| `AZIMUTH_COL` | 3 | `azimuth_peak` | no |
| `CUTOFF_PATH` | 3 | `OUTPUT_DIR/...csv` | if stored elsewhere |
| `FILENAME_REGEX` | 4 | MAARU convention | **different recorder** |
| `LOWER/UPPER_BOUND_FREQUENCY` | `default.json` | 2000 / 8000 Hz | different taxa |

---

## Transfer function

```python
TRANSFER_FN = "transfer_function/tf_circular_6ch.zip"
```

Encodes your array's microphone geometry and **must match your hardware**.
HARKBird ships 4-, 6- and 8-microphone circular arrays; for anything else you
must measure or simulate your own (see the HARK documentation).

A mismatched transfer function produces confident, wrong directions with no
error or warning.

---

## BirdNET

```python
LAT  = 51.4175
LON  = 0.1462
WEEK = 33
```

Latitude, longitude and week build a species filter, so only plausible species
for your place and season are eligible. This substantially cuts false positives.

**`WEEK` is BirdNET's own index: 1–48, four weeks per month.** Not an ISO week.

```
week = (month − 1) × 4 + min(4, ceil(day / 7))
```

5 September → 33. 25 September → 36. Use `-1` for a year-round list if your
recordings span months.

**`MIN_CONFIDENCE = 0.5`** is a floor, not the final threshold — per-species
cutoffs are applied during clustering. Leave it unless you have a reason.

**`CHUNK_OVERLAP_S = 1.5`** means BirdNET's 3 s windows overlap, giving several
azimuth estimates per call. That redundancy is what makes clustering work.
Setting it to 0 halves runtime and measurably degrades clustering.

Overlap inflates raw detection counts — never report them as call counts.

---

## Clustering

```python
TEMPORAL_WINDOW = 600      # block length (seconds)
AZIMUTH_WINDOW  = 25       # cluster tolerance (degrees)
AZIMUTH_COL     = "azimuth_peak"
```

Override for one run without editing the file:

```bash
python harkbirdnet/generate-pseudoindividuals.py --azimuth-window 30
```

### How it works

Within each species × time block:

1. Sort detections by descending confidence.
2. A detection more than `AZIMUTH_WINDOW` from every existing seed becomes a
   new seed.
3. Every detection joins its nearest seed. Distances are circular, so 175° and
   −175° are 10° apart.

Each cluster is one pseudo-individual — an approximation, not a verified bird.

### `AZIMUTH_WINDOW` — derive your own

It is a **radius** from the seed, not a diameter, so cluster width can approach
twice the value.

Playback trials with the MAARU array (n = 52, 1–8 m) gave a median error of 0°
and 92.3% of estimates within 10°. The remainder were off by 100° or more —
the distribution is bimodal, with nothing in between. 25° covers the
well-behaved mode with margin and allows for movement within a block.

To measure yours: play a source at known bearings at realistic distances, run
it through `localise.py` and `detect.py`, and compare estimated with true
bearing.

- **Too small** → one bird whose direction wanders splits into several.
- **Too large** → separate birds in similar directions merge.

Maximum clusters per species-block is `floor(360 / AZIMUTH_WINDOW)` — 14 at 25°.
Assignment has no distance cap, so an outlier always joins its nearest cluster.

Output files are suffixed with the value used (`_az25`), so runs don't
overwrite each other. Reporting sensitivity across two or three values is good
practice.

### `TEMPORAL_WINDOW`

Clustering **resets at every block boundary**. Set this to your recording
length. A bird calling across a boundary is counted once per block, so counts
must not be summed across blocks as unique birds.

### `AZIMUTH_COL`

Leave as `azimuth_peak`. See
[`TECHNICAL_NOTES.md`](TECHNICAL_NOTES.md#azimuth-assignment).

### Confidence cutoffs

BirdNET confidence is not comparable across species, so clustering expects a
per-species threshold from manual validation. CSV at `CUTOFF_PATH` with columns
`species_common` and `cutoff_prec`.

To derive them: sample detections per species across the confidence range,
score each as correct or incorrect by listening, and take the confidence at
which precision meets your target.

**Species absent from the file are dropped entirely** — the script reports
which. To skip this step:

```bash
python harkbirdnet/generate-pseudoindividuals.py --global-cutoff 0.85
```

One flat threshold. Fine for testing, weaker for publication. Report which you
used.

---

## HARKBird localisation

In `HARKBird_4.5/parameter/default.json`. Four keys affect the MUSIC spectrum:

```json
"LOWER_BOUND_FREQUENCY": 2000,
"UPPER_BOUND_FREQUENCY": 8000,
"PERIOD": 20,
"NUM_SOURCE": 1
```

**Frequency bounds** restrict localisation to your target band. The 2000 Hz
floor was raised from 1000 Hz after wind and handling noise dominated the
spectrum. Lower it for species calling below 2 kHz, and expect more noise. The
upper bound cannot exceed half your sample rate.

**`PERIOD`** is the localisation interval in frames. At 16 kHz this gives one
spectrum frame every 0.2 s. Halving it doubles resolution, file size and
runtime.

Other keys either affect `df_separated.csv` only or are not applied at all —
see [`TECHNICAL_NOTES.md`](TECHNICAL_NOTES.md#which-harkbird-parameters-actually-apply).

---

## Filenames

`tidy.py` parses site and timestamp using `FILENAME_REGEX`. The default expects:

```
SITE-YYYY-MM-DD_HH-MM-SS_dur=Nsecs.wav
```

Rewrite it for your recorder. It must produce named groups `location`, `year`,
`month`, `day`, `hour`, `minute`, `second`; `duration_s` is optional. `tidy.py`
fails with a clear message listing example filenames if the pattern doesn't
match.

This is the only recorder-specific step — everything else is filename-agnostic.

---

## Directory structure

`localise.py` and `detect.py` expect one subfolder per site-day inside
`DATA_DIR`:

```
Data/
├── ASNW-2021-09-05/
│   ├── ASNW-2021-09-05_12-09-30_dur=600secs.wav
│   └── localized_ASNW-2021-09-05_12-09-30_dur=600secs.wav/
└── PAWS-2021-09-05/
```

Folders beginning `localized` are skipped automatically. For a flat directory,
adapt `find_wavs()` in `localise.py`.
