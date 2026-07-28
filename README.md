# HARKBirdNET

Localised bird species detection from multichannel field recordings.
HARKBirdNET pairs HARK's MUSIC direction-of-arrival estimation with BirdNET
species classification, assigning a direction to every detection from a single
compact microphone array — then groups those directions into approximate
individuals.

**Pipeline:** raw audio → HARK localisation → BirdNET detection + azimuth
lookup → DOA clustering → pseudo-individuals.

- **Adapting it to your site and array:** [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)
- **How it works internally:** [`docs/TECHNICAL_NOTES.md`](docs/TECHNICAL_NOTES.md)

---

## Requirements

- **Ubuntu 22.04** (x86_64). HARK is Ubuntu-version-specific.
- **≥ 16 GB RAM** for 10-minute multichannel recordings.
- A **multichannel microphone array with a matching HARK transfer function.**
  HARKBird ships transfer functions for 4-, 6- and 8-microphone circular
  arrays. Developed and tested on the MAARU recorder (6-microphone circular
  array, 16 kHz, 16-bit).

Validated configuration: Python 3.10.12 · PyHARK 2.0.0 · HARKBird 4.5 ·
birdnet 0.1.7 · numpy 1.26.4 · TensorFlow 2.15.1 · ffmpeg 4.4.2.

---

## Installation

Roughly 30–45 minutes, mostly downloads. Most problems encountered at step 3.

### 1. System packages

```bash
sudo apt update && sudo apt upgrade
sudo apt install curl python3-venv python3-pip
sudo apt install xterm sox python-is-python3 ffmpeg python3-tk
```

### 2. Add the HARK repository

```bash
sudo curl -sSL http://archive.hark.jp/harkrepos/public.gpg \
  -o /usr/share/keyrings/hark-archive-keyring.asc

sudo bash -c 'echo -e "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hark-archive-keyring.asc] http://archive.hark.jp/harkrepos $(lsb_release -cs) non-free\ndeb-src [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hark-archive-keyring.asc] http://archive.hark.jp/harkrepos $(lsb_release -cs) non-free" > /etc/apt/sources.list.d/hark.list'

sudo apt update
sudo apt install libhark-lib python3-hark-lib
```

### 3. Virtual environment + PyHARK v2

**PyHARK 2.x must go in a virtual environment.** The system `hark` package is
version 1.1.0, has no `hark.base`, and shadows it otherwise.

```bash
python3 -m venv ~/harkenv
source ~/harkenv/bin/activate
pip install --upgrade pip setuptools

pip install hark-lib hark-lib-core hark-modules-std hark-modules-matplotlib \
            hark-modules-kivy hark-modules-dlssl hark-tool \
            --trusted-host archive.hark.jp \
            --extra-index-url http://archive.hark.jp/whl/

pip install -r requirements.txt
```

Check:

```bash
python -c "import hark.base, hark.core; print('PyHARK OK')"
python -c "import birdnet; print('BirdNET OK')"
```

### 4. Install HARKBird 4.5

Not redistributed here. Download from the
[HARKBird project page](https://sites.google.com/view/alcore-suzuki/home/harkbird)
and unzip into the repository root (or anywhere — set `HARKBIRD_DIR` in
`config.py`). Transfer functions ship with it.

```bash
unzip HARKBird_4.5.zip
```

### 5. Apply the GHDSS patch — required

Without this, long recordings crash the machine. HARKBird runs source
separation internally and never releases the memory; a batch of 10-minute
6-channel files gets OOM-killed after ~18 recordings. This pipeline doesn't use
the separated audio, so it can be switched off.

```bash
cd HARKBird_4.5
cp hb_pyhark.py hb_pyhark.py.orig
patch -p1 < ../patches/disable_ghdss.patch
cd ..
```

`spectrum.txt`, `remixed.wav` and `df_separated.csv` are still produced.

### 6. Stop the machine sleeping

A suspended laptop kills a running batch.

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

Also set *Settings → Power → Screen Blank* to *Never*.

<details>
<summary><b>Install troubleshooting</b></summary>

**`pip3 install --break-system-packages` → `no such option`**
That flag doesn't exist in Ubuntu 22.04's pip. You don't need it — the virtual
environment solves the same problem.

**`sudo apt install hark-python-3` → package not found**
Wrong package name for this configuration. Use step 2 as written.

**`pip install pyHARK` → installs nothing useful**
Not the right package. PyHARK 2.x comes from the HARK wheel index in step 3.

**`import hark.base` → ModuleNotFoundError**
You're outside the virtual environment, or picking up system `hark` 1.1.0. Run
`source ~/harkenv/bin/activate` and check `pip show hark-lib` reports 2.0.0.

**Installing `birdnet` downgrades numpy to 1.26.4**
Expected — TensorFlow 2.15 requires it. That's the validated version.

**`patch` fails on `hb_pyhark.py`**
Your HARKBird version differs. Find the block with
`grep -n "ghdss\|GHDSS\|Synthesize\|SaveWavePCM" hb_pyhark.py` and comment out
from `# GHDSS インスタンシエイト` to the end of the file-renaming loop.

**Batch dies with `Killed` after N files**
Out of memory. Either the GHDSS patch isn't applied, or `localise.py` has been
modified to call `localize_separate()` directly instead of via subprocess. See
[`docs/TECHNICAL_NOTES.md`](docs/TECHNICAL_NOTES.md#memory).

</details>

---

## Configuration

**Edit `harkbirdnet/config.py`. That's the only file you need to change.**
Every script reads its settings from there.

Four things to set before your first real run:

| Setting | What it is |
| --- | --- |
| `DATA_DIR` | where your recordings live |
| `LAT`, `LON`, `WEEK` | your site and season, for BirdNET's species filter |
| `AZIMUTH_WINDOW` | clustering tolerance — **derive this from your own array's localisation error** |
| `TRANSFER_FN` | must match your microphone array |

The defaults are those used to develop the pipeline and will be wrong for you.
[`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) explains each one and how to
choose a value.

Scripts fail immediately with a clear message if a configured path doesn't
exist, rather than part-way through a long run.

### Expected data layout

```
Data/
├── SITE-2021-09-05/
│   ├── SITE-2021-09-05_08-00-00_dur=600secs.wav
│   └── localized_SITE-2021-09-05_08-00-00_dur=600secs.wav/
└── SITE-2021-09-06/
```

One subfolder per site-day. Filenames must match `FILENAME_REGEX` in
`config.py` — the default is `SITE-YYYY-MM-DD_HH-MM-SS_dur=Nsecs.wav`. This is
the only recorder-specific part of the pipeline; if your recorder differs, edit
that one regex.

---

## Running it

```bash
source ~/harkenv/bin/activate

python harkbirdnet/flac_to_wav.py                 # 1. FLAC → WAV (skip if WAV)
python harkbirdnet/localise.py                    # 2. HARK localisation
python harkbirdnet/detect.py                      # 3. BirdNET + azimuth
python harkbirdnet/combine.py                     # 4. bind into one table
python harkbirdnet/tidy.py                        # 5. parse site + timestamp
python harkbirdnet/generate-pseudoindividuals.py  # 6. DOA clustering
```

Run from the repository root. Steps 2 and 3 are resumable — they skip
recordings that already have a `spectrum.txt`, so an interrupted batch restarts
safely. Step 2 dominates the runtime.

> Expected wall-clock time per 10-minute recording: 15 minutes

Watch memory during a long run:

```bash
watch -n 5 free -h
```

Available memory should stay flat between files, not decline.

### Step 6 needs confidence thresholds

Clustering applies **per-species** confidence cutoffs from manual validation,
because BirdNET confidence isn't comparable across species. Supply them as a
CSV (`species_common,cutoff_prec`) at `CUTOFF_PATH`. Species missing from that
file are dropped entirely, and the script reports which.

To run without ground-truthing:

```bash
python harkbirdnet/generate-pseudoindividuals.py --global-cutoff 0.85
```

One flat threshold for every species. Fine for testing, weaker for
publication — report which you used. Full detail in the header of that script
and in [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

---

## Outputs

Per recording, in `localized_<filename>/`:

| File | Contents |
| --- | --- |
| `spectrum.txt` | MUSIC spectrum, frames × 72 azimuths |
| `remixed.wav` | mono mixdown |
| `df_separated.csv` | HARK source tracks (not used downstream) |
| `visualisation.png` | spectrogram + aziogram |
| `birdnet_detections.csv` | detections with azimuth |

In `OUTPUT_DIR`:

| File | Contents |
| --- | --- |
| `birdnet_all.csv` | all detections combined |
| `birdnet_all_tidy.csv` | plus site and parsed timestamp |
| `individuals_top_call_az25.csv` | one row per individual (best call) |
| `individuals_per_block_az25.csv` | one row per individual, with call count |
| `individuals_at_once_az25.csv` | individuals per species per block |

The `_az25` suffix records the clustering tolerance, so runs at different
values don't overwrite each other.

---

## Worked example

> **[PLACEHOLDER]** Run on `examples/`, with expected output for comparison.

---

## Known limitations

Explained in
[`docs/TECHNICAL_NOTES.md`](docs/TECHNICAL_NOTES.md#limitations).

- Azimuth is assigned by `argmax`, which always returns a direction — noise and
  echoes still get one.
- Use `azimuth_peak`, not `azimuth_mean`; the latter averages angles
  arithmetically and breaks at the ±180° wraparound.
- Clusters are **approximate** individuals, not verified ones, and are
  generally a minimum count.
- HARK resolves one dominant direction per frame, so simultaneous callers in
  similar directions are undercounted.
- BirdNET's window overlap inflates raw detection counts — don't report them as
  call counts.

---

## Repository layout
```
HARKBirdNET/
├── harkbirdnet/
│   ├── config.py                        ← the only file you edit
│   ├── flac_to_wav.py
│   ├── localise.py
│   ├── visualise.py
│   ├── detect.py
│   ├── combine.py
│   ├── tidy.py
│   └── generate-pseudoindividuals.py
├── patches/disable_ghdss.patch
├── docs/
│   ├── CONFIGURATION.md
│   └── TECHNICAL_NOTES.md
├── examples/
├── requirements.txt
└── README.md
```

---

## Citation

> **[TO DO]** CITATION.cff, Zenodo DOI, paper reference.

## License

> **[TO DO]** Repository licence. HARKBird and its transfer functions are
> the work of Reiji Suzuki (Nagoya University) under their own terms — linked
> here, not redistributed.

## Acknowledgements

HARKBird 4.5 was developed by Reiji Suzuki and colleagues at Nagoya University.
HARK is developed by Honda Research Institute Japan and Kyoto University.
