"""
capture.py
----------
Captures calibration photos for the HandyFluor project.

Startup runs a one-time focus calibration: autofocus locks onto the sample
once, the resulting lens position is printed and then held fixed (manual
focus) for the rest of the session. This prevents focus drift between
concentrations, which would otherwise show up as a false signal in the
calibration curve. A confirmation photo is also saved at the locked focus
so you can check sharpness by eye afterward (e.g. in a gallery app).

Each run of this script is a "session". All photos taken during a session
are saved into their own timestamped sub-folder inside captures/, so
different sessions never mix their files together.

Main loop: one concentration at a time. You type a concentration value,
and the script cycles through all 5 camera configurations (an exposure/
gain sweep), taking 3 photos under each one. One concentration entry = 5
configs x 3 photos = 15 photos total.

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
from libcamera import controls, Transform


# ---------------------------------------------------------------------------
# EDIT THESE: your 5 camera configurations to test.
# exposure_time is in microseconds. analogue_gain is a multiplier (1.0 = no extra gain).
# awb_enable is always False here — white balance must stay fixed across every
# shot in a calibration series, or color gains shift with sample brightness
# and corrupt intensity readings. colour_gains is the one fixed value used
# throughout (calibrate it once against a neutral reference if needed).
#
# This is an EXPOSURE SWEEP, not a style/look sweep: everything except
# exposure_time (and gain, for the fallback row) is held identical across
# configs on purpose.
# ---------------------------------------------------------------------------
CAMERA_CONFIGS = [

    # 1. 0.2 s
    {"exposure_time": 200000, "analogue_gain": 1.0,
     "awb_enable": False, "colour_gains": (1.0, 1.0)},

    # 2. 0.5 s
    {"exposure_time": 500000, "analogue_gain": 1.0,
     "awb_enable": False, "colour_gains": (1.0, 1.0)},

    # 3. 1 s
    {"exposure_time": 1000000, "analogue_gain": 1.0,
     "awb_enable": False, "colour_gains": (1.0, 1.0)},

    # 4. 2 s
    {"exposure_time": 2000000, "analogue_gain": 1.0,
     "awb_enable": False, "colour_gains": (1.0, 1.0)},

    # 5. 2 s + gain fallback, only if config 4 is still too dim
    {"exposure_time": 2000000, "analogue_gain": 2.0,
     "awb_enable": False, "colour_gains": (1.0, 1.0)},

]

# The camera module is mounted upside down in the rig, so every photo comes
# out rotated 180 degrees. Flipping both axes corrects that at capture time,
# so every saved photo (focus-check included) is already right-side up.
CAMERA_TRANSFORM = Transform(hflip=True, vflip=True)

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
    "session", "config_number", "concentration", "replicate", "filename",
    "exposure_time", "analogue_gain", "colour_gains", "awb_enable",
    "lens_position", "timestamp",
]

# Keeps track of the filenames from the most recent concentration batch,
# so "undo" knows exactly what to remove.
last_batch_filenames = []

# Set once at startup by calibrate_focus(), then held fixed for the session.
locked_lens_position = None

# Set once at startup by start_new_session(). All photos this run go here.
session_dir = None
session_id = None


def ensure_output_files_exist():
    """Make sure the captures/ folder and capture_log.csv exist before we start."""
    if not os.path.exists(CAPTURES_DIR):
        os.makedirs(CAPTURES_DIR)

    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(LOG_HEADERS)


def start_new_session():
    """
    Create a fresh, timestamped sub-folder under captures/ for this run of
    the script, e.g. captures/session_20260917_153000/. Every photo taken
    during this run -- including the focus-check photo -- goes in here, so
    sessions never mix.

    Returns (session_id, session_dir).
    """
    new_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_session_dir = os.path.join(CAPTURES_DIR, f"session_{new_session_id}")
    os.makedirs(new_session_dir, exist_ok=True)

    print(f"New session: {new_session_id} -> saving photos in {new_session_dir}/\n")

    return new_session_id, new_session_dir


def calibrate_focus(picam2):
    """
    One-time focus calibration round, run at startup before any captures.

    Put the actual sample under the camera in its real imaging position
    BEFORE running this. It runs autofocus once, reads back the lens
    position autofocus landed on, then switches to manual mode locked at
    that exact position. Every capture for the rest of the session reuses
    this fixed position -- autofocus never runs again mid-session.

    Also saves a full-resolution confirmation photo at the locked focus
    (focus_check.jpg, in this session's folder) so you can open it in a
    gallery/image viewer afterward and check the sample actually looks
    sharp, instead of just trusting the reported lens position.

    Returns the locked lens position (float).
    """
    print("\nFocus calibration: place your sample under the camera now.")
    input("Press Enter when the sample is in position...")

    picam2.set_controls({"AfMode": controls.AfModeEnum.Auto})
    print("Running autofocus...")
    success = picam2.autofocus_cycle()  # blocks until AF settles or times out

    if not success:
        print("Autofocus did not report a confident lock. You can re-run "
              "calibration, or check focus manually before continuing.")

    metadata = picam2.capture_metadata()
    position = metadata["LensPosition"]

    # Lock manual focus at the position AF just found. No autofocus runs
    # again after this point in the session.
    picam2.set_controls({
        "AfMode": controls.AfModeEnum.Manual,
        "LensPosition": position,
    })
    time.sleep(0.5)  # let the lens settle at the locked position

    # Save a confirmation photo at this locked focus so you can visually
    # verify sharpness in a gallery app, rather than just trusting the
    # number below.
    focus_check_path = os.path.join(session_dir, "focus_check.jpg")
    picam2.capture_file(focus_check_path)

    print(f"Focus locked at LensPosition = {position:.3f}. "
          f"This value is fixed for the rest of the session.")
    print(f"Saved a focus-check photo to {focus_check_path} "
          f"-- open it in a gallery/file viewer to confirm it looks sharp.\n")

    return position


def apply_camera_settings(picam2, config):
    """Lock the camera's exposure, gain, and white balance to a fixed configuration.

    Focus is NOT touched here -- it was locked once by calibrate_focus()
    at startup and stays fixed across every config and every concentration.
    """
    camera_controls = {
        "ExposureTime": config["exposure_time"],
        "AnalogueGain": config["analogue_gain"],
        "AeEnable": False,       # turn off auto-exposure, we're setting it manually
        "AwbEnable": config["awb_enable"],
        "NoiseReductionMode": 0,  # 0 = off
    }

    if not config["awb_enable"]:
        camera_controls["ColourGains"] = config["colour_gains"]

    picam2.set_controls(camera_controls)
    time.sleep(SETTINGS_APPLY_DELAY_SECONDS)


def take_one_photo(picam2, config_number, config, concentration, replicate):
    """Capture a single photo (into this session's folder) and log it.
    Returns the filename that was saved (relative to session_dir)."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"config{config_number}_conc{concentration}mgL_rep{replicate}_{timestamp}.png"
    filepath = os.path.join(session_dir, filename)

    picam2.capture_file(filepath)

    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            session_id,
            config_number,
            concentration,
            replicate,
            filename,
            config["exposure_time"],
            config["analogue_gain"],
            config["colour_gains"],
            config["awb_enable"],
            locked_lens_position,
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

    # Delete the photo files (they live in this session's folder).
    for filename in last_batch_filenames:
        filepath = os.path.join(session_dir, filename)
        if os.path.exists(filepath):
            os.remove(filepath)

    # Remove the matching rows from the CSV log. Match on both session and
    # filename, since filenames could in principle repeat across sessions.
    with open(LOG_FILE, "r", newline="") as f:
        rows = list(csv.reader(f))

    header, data_rows = rows[0], rows[1:]
    rows_to_keep = [
        row for row in data_rows
        if not (row[0] == session_id and row[4] in last_batch_filenames)
    ]

    with open(LOG_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows_to_keep)

    print(f"Undo complete: removed {len(last_batch_filenames)} photo(s).\n")
    last_batch_filenames = []


def clear_all_data():
    """Delete every captured photo (every session folder) and reset the log
    file to just its header."""
    global last_batch_filenames

    for entry in os.listdir(CAPTURES_DIR):
        entry_path = os.path.join(CAPTURES_DIR, entry)
        if os.path.isdir(entry_path):
            for filename in os.listdir(entry_path):
                filepath = os.path.join(entry_path, filename)
                if os.path.isfile(filepath):
                    os.remove(filepath)
            os.rmdir(entry_path)
        elif os.path.isfile(entry_path):
            os.remove(entry_path)

    with open(LOG_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(LOG_HEADERS)

    last_batch_filenames = []
    print("All captures and log data cleared.\n")

    # This session's own folder was just deleted along with everything
    # else -- recreate it so subsequent captures in this run still have
    # somewhere to go.
    os.makedirs(session_dir, exist_ok=True)


def print_help():
    print(
        "Commands:\n"
        "  <number>   run all 5 configs (3 photos each) for that concentration, e.g. 5.0\n"
        "  undo       delete the most recent batch of photos\n"
        "  clear yes  delete ALL captures (every session) and reset the log\n"
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
    global locked_lens_position, session_id, session_dir

    ensure_output_files_exist()
    session_id, session_dir = start_new_session()

    picam2 = Picamera2()
    picam2.configure(picam2.create_still_configuration(transform=CAMERA_TRANSFORM))
    picam2.start()

    try:
        # One-time focus calibration round. Runs autofocus once, then locks
        # manual focus at the result. No autofocus runs again after this --
        # every config and every concentration for the rest of the session
        # reuses this same fixed lens position.
        locked_lens_position = calibrate_focus(picam2)

        run_capture_session(picam2)
    finally:
        picam2.stop()


if __name__ == "__main__":
    main()