# HandyFluor Calibration Capture

Two simple scripts for capturing and reviewing calibration photos on the
Raspberry Pi 5 + Arducam 16MP, as part of the HandyFluor project.

`capture.py` takes photos of your samples across 5 different camera settings,
so you can later compare and pick the best one. `gallery.py` lets you browse
the photos from your Mac's browser, organized like a folder tree.

## Setup

Install the one dependency (everything else is Python's standard library):

```
pip install picamera2
```

## 1. Capturing photos — `capture.py`

Run it on the Pi:

```
python3 capture.py
```

It's a single loop. You just type a concentration, and the script
automatically cycles through **all 5 camera configurations**, taking **3
photos** under each one — so one concentration entry gives you 15 photos
total (5 configs x 3 photos).

Commands at the prompt:

| Input        | What it does                                                          |
|--------------|------------------------------------------------------------------------|
| `5.0`        | Runs all 5 configs (3 photos each) for concentration `5.0` (any number works) |
| `undo`       | Deletes the most recent batch of photos you just took                  |
| `clear yes`  | Deletes **everything** captured so far (type this exact phrase to confirm) |
| `quit`       | Stops the program                                                       |

Place your sample, type its concentration, wait for the 15 photos to finish,
then place the next sample and repeat.

### Editing the 5 camera configurations

Near the top of `capture.py`:

```python
CAMERA_CONFIGS = [
    {"exposure_time": 5000,  "analogue_gain": 1.0, "awb_enable": False, "colour_gains": (1.5, 1.5)},
    ...
]
```

Edit these 5 dictionaries with the exposure/gain/white-balance values you
want to test. `exposure_time` is in microseconds, `analogue_gain` is a
multiplier, and `colour_gains` is `(red_gain, blue_gain)` — only used when
`awb_enable` is `False`.

You can also tune capture speed near the top:
- `PHOTOS_PER_SETTING` — how many photos per config (default 3)
- `SETTINGS_APPLY_DELAY_SECONDS` — pause after changing camera settings (default 0.2s)
- `DELAY_BETWEEN_PHOTOS_SECONDS` — pause between photos within the same setting (default 0.1s)

## 2. Browsing photos — `gallery.py`

Once you have some photos, run:

```
python3 gallery.py
```

It will print something like:

```
Gallery running! Open this on your Mac's browser:
  http://192.168.1.42:8000
```

Open that address in Safari or Chrome on your Mac (same wifi network as the
Pi). The page organizes photos like a folder tree:

```
Config 1 (15 photos)
   Concentration 0.0 mg/L (3 photos)   [thumbnails]
   Concentration 5.0 mg/L (3 photos)   [thumbnails]
   ...
Config 2 (15 photos)
   ...
```

Each section is collapsible — click a heading to expand/collapse it. Click
any thumbnail to see the full-size image.

## Folder structure

```
capture.py
gallery.py
README.md
captures/           <- all photos get saved here
capture_log.csv     <- one row per photo: config, concentration, replicate, settings, timestamp
```

## Filename format

```
config{config_number}_conc{concentration}mgL_rep{replicate}_{timestamp}.png
```

Example: `config2_conc5.0mgL_rep3_20260916_142033_123456.png` means
configuration 2, concentration 5.0 mg/L, the 3rd of 3 photos for that config.