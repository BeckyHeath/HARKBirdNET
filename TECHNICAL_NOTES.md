# Technical notes

Internals, verified parameter behaviour, and honest limitations. For install see the [README](../README.md); for
tuning see [`CONFIGURATION.md`](CONFIGURATION.md). All settings live in
`harkbirdnet/config.py`.

---

## Memory

Two distinct memory problems were encountered during development. Both fixes are
required, and neither is optional for long recordings.

### 1. GHDSS separation

HARKBird runs GHDSS source separation as part of `localize_separate()`, even
when source tracking is suppressed with a high `THRESH`. The separation
matrices are computed regardless and are not released between files.

Observed failure: a batch of 10-minute 6-channel WAVs (16 kHz, 16-bit, ~115 MB
each) was OOM-killed by the kernel after roughly 18 files, at 12.7 GB resident
on a 15 GB machine.

Since this pipeline consumes only `spectrum.txt`, separation is disabled by
`patches/disable_ghdss.patch`, which comments out the GHDSS, Synthesize and
SaveWavePCM blocks in `hb_pyhark.py`. `spectrum.txt`, `remixed.wav` and
`df_separated.csv` are unaffected; only the `sep_*.wav` files stop being
written, which also saves substantial disk space.

### 2. PyHARK inter-file leak

Even with separation disabled, memory climbs steadily across successive files.
PyHARK is a Python binding over a C++ core, and HARK objects created inside
`localize_separate()` retain state that Python's garbage collector cannot reach.
**`gc.collect()` does not help** — it was tried and made no difference.

The fix is process-level isolation: `localise.py` runs each recording in its own
Python subprocess via `subprocess.run`, so the interpreter is fully torn down
after every file and memory returns to baseline.

**If you refactor this code, keep the subprocess isolation.** A loop calling
`localize_separate()` directly is the obvious simplification and it will fail on
any substantial dataset.

Verify with `watch -n 5 free -h` — available memory should stay flat between
files.

---

## Which parameters actually reach the code

`HARKBird_4.5/parameter/default.json` contains fourteen keys. **Seven reach the
code; seven do not.**

The reason is that `hb_pyhark.py` constructs the HARK pipeline directly in
Python (`hark.core.LocalizeMUSIC()`, `hark.core.SourceTracker()`) rather than
through HARKBird's `.n` network files. `load_parameters()` reads the whole JSON
into a dictionary, but only some keys are passed on.

**Reach `LocalizeMUSIC` — these shape `spectrum.txt`:**

| JSON key | Value | HARK parameter |
| --- | --- | --- |
| `LOWER_BOUND_FREQUENCY` | 2000 | `LOWER_BOUND_FREQUENCY` |
| `UPPER_BOUND_FREQUENCY` | 8000 | `UPPER_BOUND_FREQUENCY` |
| `PERIOD` | 20 | `PERIOD` |
| `NUM_SOURCE` | 1 | `NUM_SOURCE` |

**Reach `SourceTracker` — affect `df_separated.csv` only, which nothing
downstream reads:** `THRESH` 99, `PAUSE_LENGTH` 750, `MIN_SOURCE_INTERVAL` 20.

`THRESH` is set deliberately high to suppress HARK's own source tracking, since
detection is BirdNET's job.

**Not applied at all:**

| JSON key | Why not |
| --- | --- |
| `LOCFRAMES` | The line is commented out in `hb_pyhark.py`. Maps to `WINDOW` in HARK terms (frames used for the correlation function). HARK's internal default applies, **not 30**. |
| `TFNAME` | Overridden by `localise.py`'s `TRANSFER_FN` argument |
| `MICNO` | Not passed; all channels used |
| `PRE_LENGTH` | Maps to `PREROLL_LENGTH`, GUI path only |
| `SEP_UPPER/LOWER_BOUND_FREQUENCY` | GHDSS only, disabled |
| `Network` | Names the `.n` file, GUI path only |

> Do not report `LOCFRAMES = 30` as an applied parameter.

**Fixed in code, not configurable, but needed for reproduction:** frame length
512, frame advance 160, `MUSIC_ALGORITHM = 'SEVD'`, `WINDOW_TYPE = 'FUTURE'`,
identity noise correlation matrix (spatially white noise assumed), input scaled
by 2¹⁵.

> **[PLACEHOLDER — verify]** `MultiFFT` is instantiated with no arguments, so
> HARK's default analysis window applies. HARKBird's GUI network file specifies
> `HAMMING`, but HARK's documented default is `CONJ`. Confirm which is in effect
> before reporting the analysis window.

### The `.n` network files

`HARKBird_4.5/network/default.n` is a template containing `#TOKEN#`
placeholders. HARKBird's GUI (`hb_main.py`) substitutes parameter values into it
and writes `network.n`.

**Neither file is read by this pipeline.** `hb_pyhark.py` contains no reference
to them. Consequently `network.n` can hold stale values from an earlier
parameter set without affecting batch results — but running the HARKBird GUI
will *not* reproduce these results unless its parameters are set to match.

---

## Spectrum resolution and time alignment

`spectrum.txt` is a tab-separated matrix, rows = time frames, columns = 72
azimuths spanning −180° to 175° in 5° steps. The column ordering comes from an
`np.fft.fftshift` applied before writing.

At 16 kHz with frame advance 160 and `PERIOD` 20:

```
Δt = PERIOD × advance / sample_rate = 20 × 160 / 16000 = 0.200 s
```

A 600 s recording gives approximately 2999 rows.

> **[PLACEHOLDER — verify]** Confirm row count against a real 600 s recording.

### A small systematic lag

`detect.py` maps detection time to spectrum row as:

```python
frame_idx = round(time_mid / duration * (n_frames - 1))
```

This assumes frames are evenly distributed across the full recording duration.
They are very nearly, but not exactly — the last frame centre falls slightly
before the file end. The result is a lag that grows linearly through the
recording:

| Position in file | Offset |
| --- | --- |
| 0 s | 0.000 s |
| 60 s | 0.000 s |
| 300 s | −0.200 s |
| 600 s | −0.300 s |

At worst this is one and a half spectrum frames, well inside a single 3 s
BirdNET window, so it is very unlikely to change any result. It is documented
here because it is real and quantifiable rather than because it is material.

---

## Azimuth assignment

For each BirdNET detection, `detect.py` records two azimuths:

- **`azimuth_peak`** — `argmax` across the 72 azimuth columns at the detection's
  **midpoint frame only**.
- **`azimuth_mean`** — `argmax` per frame across all frames spanning the
  detection, then the arithmetic mean of those angles.

**Use `azimuth_peak`.** `azimuth_mean` averages angles arithmetically, which
breaks at the ±180° wraparound: 170° and −170° average to 0° rather than 180°.
This is a genuine defect, and is the likely reason `azimuth_mean` performs worse
in localisation trials. A circular mean would fix it. The column is retained
only for comparison.

**`argmax` always returns a direction.** There is no source-presence test and no
confidence guard, so a detection falling in a frame dominated by wind, an echo,
or a passing aircraft still receives a confident-looking azimuth. The pipeline
never emits `NA`.

---

## What a cluster is, and isn't

A cluster is a **pseudo-individual**: a group of same-species detections in one
time block whose directions are mutually close. It is an approximation and,
generally, a **minimum count**.

The algorithm is greedy, confidence-ordered and circular. Seeds are taken in
descending confidence order, with a new seed created whenever a detection lies
more than `AZIMUTH_WINDOW` from all existing seeds. Every detection is then
assigned to its nearest seed with no distance cap.

Chosen over the alternatives because *k*-means requires *k* in advance (unknown
here), handles circular wraparound badly, and has no physically meaningful
stopping rule; and DBSCAN assumes a density notion that doesn't apply and
discards singletons, which here are real detections.

### Sources of undercounting

- **HARK resolves one dominant direction per frame.** Two birds calling
  simultaneously from different directions yield one azimuth, usually the
  louder.
- **Distant birds drop below the confidence threshold** and never enter
  clustering at all.
- **Silent birds are invisible.** This is a calling-bird count, not a
  population count.
- **Birds in similar directions merge**, regardless of distance from the array.

### Sources of overcounting

- **Localisation error exceeding `AZIMUTH_WINDOW`** splits one bird into
  several.
- **A bird that moves** during a block may seed a second cluster.
- **Block boundaries reset clustering**, so a bird calling across a boundary is
  counted once per block.

Counts are per species per block. They should not be summed across blocks as
unique individuals.

---

## Limitations

Consolidated:

1. `argmax` azimuth assignment has no source-presence guard.
2. `azimuth_mean` is arithmetically wrong at the ±180° wraparound.
3. Detection-to-frame mapping carries a lag up to ~0.3 s at 600 s.
4. Clusters are approximate individuals, not verified ones.
5. HARK resolves one direction per frame, so simultaneous callers are
   undercounted.
6. BirdNET window overlap inflates raw detection counts — never report them as
   call counts.
7. Per-species confidence cutoffs require manual validation; species absent from
   the cutoffs file are dropped entirely.
8. The `.n` network files are used by the HARKBird GUI only.

> **[PLACEHOLDER]** Study-design limitations (recorder replication, site
> confounding) belong in the paper, not here.

---

## Pipeline data flow

```
*.flac
  │  flac_to_wav.py                 ffmpeg, pcm_s16le
  ▼
*.wav  (6-channel, 16 kHz)
  │  localise.py                    HARK MUSIC, one subprocess per file
  ▼
localized_<file>/
  ├── spectrum.txt                  frames × 72 azimuths  ← the only HARK
  ├── remixed.wav                     output used downstream
  ├── df_separated.csv              HARK source tracks (unused)
  └── visualisation.png
  │  detect.py                      BirdNET 3 s windows, 1.5 s overlap
  ▼                                 + azimuth lookup from spectrum.txt
birdnet_detections.csv  (per recording)
  │  combine.py
  ▼
birdnet_all.csv
  │  tidy.py                        parse site + timestamp from filename
  ▼
birdnet_all_tidy.csv
  │  generate-pseudoindividuals.py  per-species confidence cutoffs,
  ▼                                 10-min blocks, 25° circular clustering
individuals_top_call_az25.csv
individuals_per_block_az25.csv
individuals_at_once_az25.csv
```
