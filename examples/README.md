# Worked example

Three outdoor playback trials: a Eurasian Wren recording played from known
bearings around the array. Running these confirms your install works and lets
you check estimated directions against ground truth — the part most likely to
be silently wrong on a new machine.

## The recordings

| File | Distance | Weatherproofing | Duration |
| --- | --- | --- | --- |
| `1m_wN_Bird_t01.wav` | 1 m | no | 77.0 s |
| `1m_wY_Bird_t01.wav` | 1 m | yes | 79.5 s |
| `2m_wN_Bird_t01.wav` | 2 m | no | 77.4 s |

All 6-channel, 16 kHz, 16-bit, outdoors. Each begins with a frequency sweep
marking the start of the trial — not a bird, and BirdNET ignores it.

> **[PLACEHOLDER]** Recording date and location (for `LAT`/`LON`/`WEEK`),
> speaker height, reference direction for the bearings, and the source of the
> playback audio with attribution if needed.

## Ground truth

The speaker moves through five bearings, holding at 30° for the first two
calls:

| Call | `1m_wN` | `1m_wY` | `2m_wN` | True bearing |
| --- | --- | --- | --- | --- |
| 1 | 2.7 s | 6.3 s | 3.3 s | **30°** |
| 2 | 14.1 s | 15.1 s | 14.3 s | **30°** |
| 3 | 27.1 s | 28.3 s | 27.5 s | **120°** |
| 4 | 42.1 s | 43.1 s | 42.5 s | **165°** |
| 5 | 57.1 s | 58.3 s | 57.3 s | **−150°** |
| 6 | 72.1 s | 73.3 s | 72.3 s | **−60°** |

Five distinct positions, so a clean run gives five wren individuals per
recording.

---

## Running it

Temporarily set these in `harkbirdnet/config.py`, then restore your own:

```python
DATA_DIR = PROJECT_ROOT / "examples"
LAT  = [PLACEHOLDER]
LON  = [PLACEHOLDER]
WEEK = [PLACEHOLDER]
```

`LAT`/`LON`/`WEEK` matter — they set BirdNET's species filter. With coordinates
from elsewhere, Eurasian Wren won't be in it and you'll get **zero detections**.

```bash
source ~/harkenv/bin/activate
python harkbirdnet/localise.py
python harkbirdnet/detect.py
```

The filenames don't match the default `FILENAME_REGEX`, so either rename them
to the `SITE-YYYY-MM-DD_HH-MM-SS_dur=Nsecs.wav` convention to continue, or stop
here — this is where the azimuth check happens.

```bash
python harkbirdnet/combine.py
python harkbirdnet/tidy.py
python harkbirdnet/generate-pseudoindividuals.py --global-cutoff 0.5
```

---

## Expected output — `1m_wY_Bird_t01.wav`

**`spectrum.txt`** should have 72 columns and ~397 rows (duration ÷ 0.2, minus
a frame or two). **`df_separated.csv` will be header-only** — correct, because
`THRESH` is 99 and detection is BirdNET's job.

**`detect.py`** gives 19 detections. The wren ones by position:

| Position | Window (s) | `azimuth_peak` | Confidence |
| --- | --- | --- | --- |
| **30°** | 15.0–18.0 | 30 | 0.86 |
| | 16.5–19.5 | 30 | 0.91 |
| | 18.0–21.0 | 50 | 0.88 |
| **120°** | 28.5–31.5 | 120 | 0.55 |
| | 30.0–33.0 | 120 | 0.95 |
| | 31.5–34.5 | 115 | 0.75 |
| **165°** | 43.5–46.5 | **80** | 0.75 |
| | 45.0–48.0 | 165 | 0.60 |
| | 46.5–49.5 | 160 | 0.74 |
| **−150°** | 58.5–61.5 | −150 | 0.97 |
| | 60.0–63.0 | −150 | 0.93 |
| | 61.5–64.5 | −145 | 0.94 |
| **−60°** | 72.0–75.0 | **−80** | 0.55 |
| | 73.5–76.5 | −60 | 0.98 |
| | 75.0–78.0 | −60 | 0.95 |
| | 76.5–79.5 | −50 | 0.91 |

Plus Gray Wagtail at 10.5 s and 49.5 s, and Great Tit at 46.5 s. These are
outdoor recordings, so background birds and false positives both occur — which
is why per-species cutoffs matter in real use.

**The pattern to notice:** the highest-confidence window of each burst is
correct within 5°. Errors sit in the low-confidence windows at the edges of a
call, where the 3 s window only partly overlaps and the midpoint frame lands in
near-silence. **Confidence is a useful proxy for azimuth reliability.**

**`generate-pseudoindividuals.py`** gives nine individuals in one block:

| Species | `azimuth_peak` | `n_calls` |
| --- | --- | --- |
| Eurasian Wren | −150 | 3 |
| Eurasian Wren | −60 | 4 |
| Eurasian Wren | 30 | 3 |
| Eurasian Wren | **80** | 1 |
| Eurasian Wren | 120 | 3 |
| Eurasian Wren | 160 | 2 |
| Gray Wagtail | −45 | 1 |
| Gray Wagtail | 95 | 1 |
| Great Tit | 160 | 1 |

**Six wren individuals from five true positions.** The extra is the 80° cluster:
that single bad detection sits 85° from the 165° position, far outside the 25°
tolerance, so it seeds its own individual. No value of `AZIMUTH_WINDOW`
prevents this.

The −80° error behaves differently — 20° from −60°, inside tolerance, so it
joins that cluster, giving it four calls instead of three.

This is why `n_calls` is worth inspecting: genuine positions accumulate three
or four detections, spurious ones typically have one low-confidence detection.

> **[PLACEHOLDER]** Expected output for the other two recordings, once run.

---

## If it doesn't match

| Symptom | Likely cause |
| --- | --- |
| Zero detections | `LAT`/`LON`/`WEEK` not set as above |
| Azimuths wrong, detections fine | `TRANSFER_FN` doesn't match the array |
| `spectrum.txt` missing | `localise.py` didn't finish — check for `Killed` |
| Row count far off | `PERIOD` changed in `parameter/default.json` |
| `tidy.py` fails | Files not renamed to the expected convention |
| Individual counts differ | `AZIMUTH_WINDOW` changed from 25 |

Small confidence differences are expected across BirdNET and TensorFlow
versions. Azimuths should match exactly.
