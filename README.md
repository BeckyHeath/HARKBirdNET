# HARKBirdNET

Localised bird species detection from multichannel field recordings.

Acoustic monitoring tells you what is calling, not where from. HARKBirdNET adds
direction: it pairs HARK's MUSIC direction-of-arrival estimation with BirdNET
species classification, then clusters detections by direction to give a minimum
count of birds calling at once. All from a single compact array — no
synchronised multi-recorder setup needed.

```
raw audio → HARK localisation → BirdNET detection + azimuth
          → DOA clustering → pseudo-individuals
```

Analysis code for the field demo looking at vertical stratification is in a seperate repo

Details: [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) ·
[`docs/TECHNICAL_NOTES.md`](docs/TECHNICAL_NOTES.md)

---

## 1. What you'll need

| | |
| --- | --- |
| **OS** | Ubuntu 22.04 (x86_64) — HARK is version-specific |
| **RAM** | ≥ 16 GB for 10-minute recordings |
| **Audio** | Multichannel WAV or FLAC. Mono will not work. |
| **Filenames** | Must encode site and timestamp (default: `SITE-YYYY-MM-DD_HH-MM-SS_dur=Nsecs.wav`) |
| **Transfer function** | Must match your array. HARKBird ships 4-, 6- and 8-mic circular. |
| **Location** | Latitude, longitude and approximate date |
| **Localisation error** | Measured for your array — sets the clustering tolerance |

Two of these catch people out:

**The transfer function** encodes your array's geometry. A mismatched one gives
confident, wrong directions with no error or warning.

**Clustering tolerance (`AZIMUTH_WINDOW`)** is a hardware property, not a
constant. The shipped 25° is what was measured for the MAARU array. Derive your
own — [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) explains how.

Per-species confidence thresholds from manual validation are used at the last
step, but aren't needed to get started — see §4.

Recordings go in one subfolder per site-day:

```
Data/
├── SITE-2021-09-05/
│   └── SITE-2021-09-05_08-00-00_dur=600secs.wav
└── SITE-2021-09-06/
```

---

## 2. Install

Validated on Python 3.10.12 · PyHARK 2.0.0 · HARKBird 4.5 · birdnet 0.1.7 ·
numpy 1.26.4 · TensorFlow 2.15.1 · ffmpeg 4.4.2.

**System packages**

```bash
sudo apt update && sudo apt upgrade
sudo apt install curl python3-venv python3-pip
sudo apt install xterm sox python-is-python3 ffmpeg python3-tk
```

**HARK repository**

```bash
sudo curl -sSL http://archive.hark.jp/harkrepos/public.gpg \
  -o /usr/share/keyrings/hark-archive-keyring.asc

sudo bash -c 'echo -e "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hark-archive-keyring.asc] http://archive.hark.jp/harkrepos $(lsb_release -cs) non-free\ndeb-src [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hark-archive-keyring.asc] http://archive.hark.jp/harkrepos $(lsb_release -cs) non-free" > /etc/apt/sources.list.d/hark.list'

sudo apt update
sudo apt install libhark-lib python3-hark-lib
```

**Virtual environment + PyHARK v2** — must be a venv. The system `hark` is
1.1.0, has no `hark.base`, and shadows it otherwise.

```bash
python3 -m venv ~/harkenv
source ~/harkenv/bin/activate
pip install --upgrade pip setuptools

pip install hark-lib hark-lib-core hark-modules-std hark-modules-matplotlib \
            hark-modules-kivy hark-modules-dlssl hark-tool \
            --trusted-host archive.hark.jp \
            --extra-index-url http://archive.hark.jp/whl/

pip install -r requirements.txt

python -c "import hark.base, hark.core; print('PyHARK OK')"
python -c "import birdnet; print('BirdNET OK')"
```

**HARKBird 4.5** — download from the
[project page](https://sites.google.com/view/alcore-suzuki/home/harkbird) and
unzip into the repository root (or set `HARKBIRD_DIR` in `config.py`).

```bash
unzip HARKBird_4.5.zip
```

**GHDSS patch — required.** HARKBird runs source separation internally and
never frees the memory; long recordings get OOM-killed after ~18 files. This
pipeline doesn't use the separated audio.

```bash
cd HARKBird_4.5
cp hb_pyhark.py hb_pyhark.py.orig
patch -p1 < ../patches/disable_ghdss.patch
cd ..
```

**Stop the machine sleeping** — a suspended laptop kills a running batch.

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

<details>
<summary><b>Troubleshooting</b></summary>

**`--break-system-packages` → `no such option`** — doesn't exist in Ubuntu
22.04's pip, and isn't needed; the venv solves the same problem.

**`import hark.base` → ModuleNotFoundError** — you're outside the venv, or
picking up system `hark` 1.1.0. Check `pip show hark-lib` reports 2.0.0.

**`birdnet` downgrades numpy to 1.26.4** — expected, TensorFlow 2.15 requires
it.

**`patch` fails** — your HARKBird version differs. Find the block with
`grep -n "GHDSS\|Synthesize\|SaveWavePCM" hb_pyhark.py` and comment out from
`# GHDSS インスタンシエイト` to the end of the file-renaming loop.

**Batch dies with `Killed`** — out of memory. Either the patch isn't applied,
or `localise.py` has been changed to call `localize_separate()` directly
instead of via subprocess. See
[`docs/TECHNICAL_NOTES.md`](docs/TECHNICAL_NOTES.md#memory).

</details>

---

## 3. Configure

**Edit `harkbirdnet/config.py`. That's the only file you change.**

| Setting | |
| --- | --- |
| `DATA_DIR` | where your recordings live |
| `TRANSFER_FN` | must match your array |
| `LAT`, `LON`, `WEEK` | site and season, for BirdNET's species filter |
| `AZIMUTH_WINDOW` | clustering tolerance, from your array's error |
| `FILENAME_REGEX` | how your recorder names files |

Defaults are site-specific and will be wrong for you.
[`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) explains each.

---

## 4. Run

```bash
source ~/harkenv/bin/activate

python harkbirdnet/flac_to_wav.py                 # 1. FLAC → WAV (skip if WAV)
python harkbirdnet/localise.py                    # 2. HARK localisation
python harkbirdnet/detect.py                      # 3. BirdNET + azimuth
python harkbirdnet/combine.py                     # 4. bind into one table
python harkbirdnet/tidy.py                        # 5. parse site + timestamp
python harkbirdnet/generate-pseudoindividuals.py  # 6. DOA clustering
```

Run from the repository root. Steps 2 and 3 skip recordings that already have a
`spectrum.txt`, so an interrupted batch restarts safely. Step 2 dominates
runtime.

Step 6 expects per-species confidence cutoffs (`species_common,cutoff_prec`) at
`CUTOFF_PATH`. Without them:

```bash
python harkbirdnet/generate-pseudoindividuals.py --global-cutoff 0.85
```

One flat threshold for every species — fine for testing, weaker for
publication. Report which you used.

---

## 5. Outputs

Per recording, in `localized_<filename>/`: `spectrum.txt` (MUSIC spectrum,
frames × 72 azimuths), `remixed.wav`, `df_separated.csv` (unused downstream),
`visualisation.png`, `birdnet_detections.csv`.

In `OUTPUT_DIR`:

| File | |
| --- | --- |
| `birdnet_all.csv` | all detections combined |
| `birdnet_all_tidy.csv` | plus site and parsed timestamp |
| `individuals_top_call_az25.csv` | one row per individual (best call) |
| `individuals_per_block_az25.csv` | one row per individual, with call count |
| `individuals_at_once_az25.csv` | individuals per species per block |

The `_az25` suffix records the clustering tolerance, so runs at different
values don't overwrite each other.

---

## 6. Worked example

> **[PLACEHOLDER]** Field-test recording with a source at known bearings, so
> estimated azimuths can be checked against ground truth. See
> `examples/README.md`.

---

## 7. Limitations

- Azimuth comes from `argmax`, which always returns a direction — noise and
  echoes get one too.
- Use `azimuth_peak`, not `azimuth_mean`; the latter averages angles
  arithmetically and breaks at the ±180° wraparound.
- Clusters are approximate individuals, and generally a minimum count.
- HARK resolves one direction per frame, so simultaneous callers in similar
  directions are undercounted.
- BirdNET's window overlap inflates raw detection counts — don't report them as
  call counts.

Full explanation in
[`docs/TECHNICAL_NOTES.md`](docs/TECHNICAL_NOTES.md#limitations).

---

## Layout

```
harkbirdnet/     config.py ← the only file you edit
                 flac_to_wav.py · localise.py · visualise.py · detect.py
                 combine.py · tidy.py · generate-pseudoindividuals.py
patches/         disable_ghdss.patch
docs/            CONFIGURATION.md · TECHNICAL_NOTES.md
examples/
```

## Licence

> **[PLACEHOLDER]** HARKBird and its transfer functions are the work of Reiji
> Suzuki (Nagoya University) under their own terms — linked, not redistributed.

HARKBird 4.5 was developed by Reiji Suzuki and colleagues at Nagoya University.
HARK is developed by Honda Research Institute Japan and Kyoto University.
