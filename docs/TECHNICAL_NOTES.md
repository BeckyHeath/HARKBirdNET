# Technical notes

Internals worth knowing when adapting or debugging the pipeline. For install
see the [README](../README.md); for settings see
[`CONFIGURATION.md`](CONFIGURATION.md).

---

## Memory

Two separate problems. Both fixes are required for long recordings.

**GHDSS separation.** HARKBird runs source separation internally even when
source tracking is suppressed, and never frees the matrices. A batch of
10-minute 6-channel files was OOM-killed at 12.7 GB after ~18 files.
`patches/disable_ghdss.patch` switches it off. The pipeline only uses
`spectrum.txt`, so nothing is lost except the `sep_*.wav` files.

**PyHARK inter-file leak.** Even with separation off, memory climbs across
files — PyHARK holds C++-side state Python can't collect, and `gc.collect()`
doesn't help. `localise.py` therefore runs each recording in its own
subprocess, so the interpreter is torn down between files.

**If you refactor `localise.py`, keep the subprocess isolation.** A plain loop
calling `localize_separate()` is the obvious simplification and it will fail on
any real dataset.

Check with `watch -n 5 free -h` — available memory should stay flat.

---

## Which HARKBird parameters actually apply

`parameter/default.json` has 14 keys. Only 7 reach the code, because
`hb_pyhark.py` builds the HARK pipeline directly in Python rather than through
the `.n` network files.

| Reaches | Keys |
| --- | --- |
| `LocalizeMUSIC` — shapes `spectrum.txt` | `LOWER_BOUND_FREQUENCY`, `UPPER_BOUND_FREQUENCY`, `PERIOD`, `NUM_SOURCE` |
| `SourceTracker` — shapes `df_separated.csv` only | `THRESH`, `PAUSE_LENGTH`, `MIN_SOURCE_INTERVAL` |
| **Nothing** | `LOCFRAMES`, `TFNAME`, `MICNO`, `PRE_LENGTH`, `SEP_*_BOUND_FREQUENCY`, `Network` |

`LOCFRAMES` is commented out in `hb_pyhark.py`, so the MUSIC correlation window
runs at HARK's internal default. `TFNAME` is overridden by `localise.py`.

Fixed in code, not configurable: frame length 512, advance 160,
`MUSIC_ALGORITHM='SEVD'`, `WINDOW_TYPE='FUTURE'`, identity noise correlation
matrix.

**The `.n` files are used by the HARKBird GUI only.** `default.n` is a template;
the GUI substitutes values into it and writes `network.n`. Neither is read by
this pipeline, so running the GUI will not reproduce these results unless its
parameters are set to match.

---

## Spectrum resolution

`spectrum.txt` is tab-separated, rows = time, columns = 72 azimuths from −180°
to 175° in 5° steps.

```
Δt = PERIOD × advance / sample_rate = 20 × 160 / 16000 = 0.200 s
```

So rows ≈ duration / 0.2, typically one or two short because
`WINDOW_TYPE='FUTURE'` needs lookahead at the end of the file. A 600 s
recording gives ~2997 rows; the 141.9 s worked example gives 707.

---

## Azimuth assignment

Each detection gets two azimuths:

- **`azimuth_peak`** — `argmax` across the 72 azimuths at the detection's
  midpoint frame.
- **`azimuth_mean`** — per-frame `argmax` across the detection, then the
  arithmetic mean.

**Use `azimuth_peak`.** Averaging angles arithmetically breaks at the ±180°
wraparound (170° and −170° average to 0°, not 180°). In playback trials
`azimuth_peak` was within 25° of truth 92.3% of the time against 65.4% for
`azimuth_mean`. The column is kept only for comparison.

**`argmax` always returns a direction.** There is no source-presence test, so a
detection landing in a frame dominated by wind or an echo still gets a
confident-looking azimuth. The pipeline never emits `NA`.

---

## What a cluster is

A **pseudo-individual**: same-species detections in one time block whose
directions are mutually close. It is an approximation and generally a
**minimum count**.

The algorithm is greedy, confidence-ordered and circular. Seeds are taken in
descending confidence; a detection more than `AZIMUTH_WINDOW` from every seed
becomes a new seed. Every detection then joins its nearest seed, with no
distance cap.

Chosen over *k*-means (needs *k* in advance, handles wraparound badly) and
DBSCAN (assumes a density notion that doesn't apply, discards singletons).

**Undercounts** because HARK resolves one direction per frame, distant birds
fall below threshold, silent birds are invisible, and birds in similar
directions merge.

**Overcounts** when localisation error exceeds `AZIMUTH_WINDOW`, when a bird
moves within a block, or across block boundaries — clustering resets at every
boundary, so a bird calling either side is counted twice.

Counts are per species per block and should not be summed across blocks as
unique birds.

---

## Limitations

1. `argmax` azimuth assignment has no source-presence guard.
2. `azimuth_mean` is wrong at the ±180° wraparound — use `azimuth_peak`.
3. Localisation errors are bimodal: mostly within 10°, occasionally 100°+.
   A large error seeds a spurious individual at any tolerance. Inspect
   `n_calls` — spurious individuals usually have a single low-confidence
   detection.
4. Clusters are approximate individuals, not verified ones.
5. BirdNET's window overlap inflates raw detection counts.
6. Species absent from the confidence-cutoff file are dropped entirely.

---

## Pipeline data flow

```
*.flac
  │  flac_to_wav.py
  ▼
*.wav (multichannel)
  │  localise.py            HARK MUSIC, one subprocess per file
  ▼
localized_<file>/
  ├── spectrum.txt          ← the only HARK output used downstream
  ├── remixed.wav
  ├── df_separated.csv      (unused)
  └── visualisation.png
  │  detect.py              BirdNET 3 s windows + azimuth lookup
  ▼
birdnet_detections.csv → combine.py → birdnet_all.csv
  │  tidy.py                parse site + timestamp
  ▼
birdnet_all_tidy.csv
  │  generate-pseudoindividuals.py
  ▼
individuals_top_call_az25.csv
individuals_per_block_az25.csv
individuals_at_once_az25.csv
```
