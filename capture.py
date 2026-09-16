"""
capture.py
----------
Captures calibration photos for the HandyFluor project.

One loop, one concentration at a time: you type a concentration value,
and the script automatically cycles through all 5 camera configurations,
taking 3 photos under each one. So one concentration entry = 5 configs x 3
photos = 15 photos total.

Commands you can type at the prompt:
    <a number>   -> run all 5 configs (3 photos each) for that concentration
    undo         -> delete the most recent batch of photos you just took
    clear yes    -> delete EVERYTHING captured so far (need to type "clear yes")
    quit         -> stop the program
"""

import csv
import os
import time
from datetime import datetime

from picamera2 import Picamera2


# ---------------------------------------------------------------------------
# EDIT THESE: your 5 camera configurations to test.
# exposure_time is in microseconds. analogue_gain is a multiplier (1.0 = no extra gain).
# awb_enable = True lets the camera auto white-balance. If False, it uses the
# colour_gains you set manually (red_gain, blue_gain).
# ---------------------------------------------------------------------------
CAMERA_CONFIGS = [

    # 1. Natural / daylight
    {"exposure_time": 10000, "analogue_gain": 1.0,
     "awb_enable": True, "colour_gains": (1.0, 1.0)},

    # 2. Bright / crisp
    {"exposure_time": 5000, "analogue_gain": 1.0,
     "awb_enable": True, "colour_gains": (1.1, 1.1)},

    # 3. Warm portrait
    {"exposure_time": 10000, "analogue_gain": 1.0,
     "awb_enable": False, "colour_gains": (1.3, 1.0)},

    # 4. Cool / cinematic
    {"exposure_time": 10000, "analogue_gain": 1.0,
     "awb_enable": False, "colour_gains": (0.8, 1.1)},

    # 5. Low-light / indoor
    {"exposure_time": 20000, "analogue_gain": 2.0,
     "awb_enable": True, "colour_gains": (1.0, 1.0)},

]

# Where photos and the log file go.
CAPTURES_DIR = "captures"
LOG_FILE = "capture_log.csv"

# How many photos to take per configuration, for each concentration.
PHOTOS_PER_SETTING = 3

# Small delay after changing camera settings, so the camera actually applies
# them before we take a photo. Kept short so the whole thing feels fast.
SETTINGS_APPLY_DELAY_SECONDS = 0.2

# Delay between the 3 photos within the same setting. Set to 0 for max speed.
DELAY_BETWEEN_PHOTOS_SECONDS = 0.1

# Column names for the CSV log file.
LOG_HEADERS = [
    "config_number", "concentration", "replicate", "filename",
    "exposure_time", "analogue_gain", "colour_gains", "awb_enable", "timestamp",
]

# Keeps track of the filenames from the most recent concentration batch,
# so "undo" knows exactly what to remove.
last_batch_filenames = []


def ensure_output_files_exist():
    """Make sure the captures/ folder and capture_log.csv exist before we start."""
    if not os.path.exists(CAPTURES_DIR):
        os.makedirs(CAPTURES_DIR)

    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(LOG_HEADERS)


def apply_camera_settings(picam2, config):
    """Lock the camera's exposure, gain, and white balance to a fixed configuration."""
    controls = {
        "ExposureTime": config["exposure_time"],
        "AnalogueGain": config["analogue_gain"],
        "AeEnable": False,       # turn off auto-exposure, we're setting it manually
        "AwbEnable": config["awb_enable"],
        "NoiseReductionMode": 0,  # 0 = off
    }

    if not config["awb_enable"]:
        controls["ColourGains"] = config["colour_gains"]

    picam2.set_controls(controls)
    time.sleep(SETTINGS_APPLY_DELAY_SECONDS)


def take_one_photo(picam2, config_number, config, concentration, replicate):
    """Capture a single photo and log it. Returns the filename that was saved."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"config{config_number}_conc{concentration}mgL_rep{replicate}_{timestamp}.png"
    filepath = os.path.join(CAPTURES_DIR, filename)

    picam2.capture_file(filepath)

    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            config_number,
            concentration,
            replicate,
            filename,
            config["exposure_time"],
            config["analogue_gain"],
            config["colour_gains"],
            config["awb_enable"],
            timestamp,
        ])

    return filename


def capture_all_configs_for_concentration(picam2, concentration):
    """
    For one concentration: cycle through all 5 camera configs, taking
    PHOTOS_PER_SETTING photos under each one.
    """
    global last_batch_filenames
    last_batch_filenames = []  # reset, this becomes the new "undo-able" batch

    print(f"\nCapturing concentration {concentration} across all {len(CAMERA_CONFIGS)} configs...")

    for config_number, config in enumerate(CAMERA_CONFIGS, start=1):
        apply_camera_settings(picam2, config)

        for replicate in range(1, PHOTOS_PER_SETTING + 1):
            filename = take_one_photo(picam2, config_number, config, concentration, replicate)
            last_batch_filenames.append(filename)
            print(f"  [config {config_number}] saved {filename}")

            if DELAY_BETWEEN_PHOTOS_SECONDS > 0:
                time.sleep(DELAY_BETWEEN_PHOTOS_SECONDS)

    total = len(CAMERA_CONFIGS) * PHOTOS_PER_SETTING
    print(f"Done. Took {total} photos for concentration {concentration}.\n")


def undo_last_capture():
    """Delete the most recent concentration batch (all configs, all replicates)."""
    global last_batch_filenames

    if not last_batch_filenames:
        print("Nothing to undo yet.")
        return

    # Delete the photo files.
    for filename in last_batch_filenames:
        filepath = os.path.join(CAPTURES_DIR, filename)
        if os.path.exists(filepath):
            os.remove(filepath)

    # Remove the matching rows from the CSV log.
    with open(LOG_FILE, "r", newline="") as f:
        rows = list(csv.reader(f))

    header, data_rows = rows[0], rows[1:]
    rows_to_keep = [row for row in data_rows if row[3] not in last_batch_filenames]

    with open(LOG_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows_to_keep)

    print(f"Undo complete: removed {len(last_batch_filenames)} photo(s).\n")
    last_batch_filenames = []


def clear_all_data():
    """Delete every captured photo and reset the log file to just its header."""
    global last_batch_filenames

    for filename in os.listdir(CAPTURES_DIR):
        filepath = os.path.join(CAPTURES_DIR, filename)
        if os.path.isfile(filepath):
            os.remove(filepath)

    with open(LOG_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(LOG_HEADERS)

    last_batch_filenames = []
    print("All captures and log data cleared.\n")


def print_help():
    print(
        "Commands:\n"
        "  <number>   run all 5 configs (3 photos each) for that concentration, e.g. 5.0\n"
        "  undo       delete the most recent batch of photos\n"
        "  clear yes  delete ALL captures and reset the log\n"
        "  quit       exit the program\n"
    )


def run_capture_session(picam2):
    """Main loop: keep asking for a concentration and capture across all configs."""
    print_help()

    while True:
        user_input = input("Enter concentration, or a command: ").strip()

        if user_input == "":
            continue

        if user_input == "quit":
            print("Exiting.")
            return

        if user_input == "undo":
            undo_last_capture()
            continue

        if user_input == "clear yes":
            clear_all_data()
            continue

        if user_input == "clear":
            print("Type 'clear yes' if you really want to delete everything.")
            continue

        try:
            concentration = float(user_input)
        except ValueError:
            print("Didn't recognize that. Type a number, or one of the commands above.")
            print_help()
            continue

        capture_all_configs_for_concentration(picam2, concentration)


def main():
    ensure_output_files_exist()

    picam2 = Picamera2()
    picam2.configure(picam2.create_still_configuration())
    picam2.start()

    try:
        run_capture_session(picam2)
    finally:
        picam2.stop()


if __name__ == "__main__":
    main()