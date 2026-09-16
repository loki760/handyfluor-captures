"""
gallery.py
----------
Serves the photos in captures/ as a browsable page, organized like a
folder structure: Config -> Concentration -> photos.

Run this on the Pi, then on your Mac (same wifi network) open the
URL it prints, e.g. http://<pi-ip>:8000
"""

import http.server
import os
import re
import socket
from collections import defaultdict

# Folder of photos to show. Change this if your photos are somewhere else.
CAPTURES_DIR = "captures"

# Port the webpage will be served on.
PORT = 8000

# Matches filenames like: config2_conc5.0mgL_rep3_20260916_142033_123456.png
FILENAME_PATTERN = re.compile(r"config(\d+)_conc([\d.]+)mgL_rep(\d+)_")

# The focus-check photo saved by calibrate_focus() in capture.py. This
# doesn't match FILENAME_PATTERN (it's not part of the config/concentration
# sweep), so it's shown separately at the top instead of being skipped.
FOCUS_CHECK_FILENAME = "_focus_check.png"


def get_local_ip():
    """Figure out this Pi's local network IP address, just to print it nicely."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def group_photos_by_config_and_concentration():
    """
    Reads all PNGs in CAPTURES_DIR and organizes them into a nested structure:
        { config_number: { concentration: [filenames] } }
    Photos that don't match the expected naming pattern are skipped.
    """
    grouped = defaultdict(lambda: defaultdict(list))

    filenames = sorted(f for f in os.listdir(CAPTURES_DIR) if f.lower().endswith(".png"))

    for filename in filenames:
        if filename == FOCUS_CHECK_FILENAME:
            continue  # shown separately at the top of the page, not in the tree

        match = FILENAME_PATTERN.match(filename)
        if not match:
            continue  # skip files that don't match our naming pattern

        config_number = int(match.group(1))
        concentration = float(match.group(2))
        grouped[config_number][concentration].append(filename)

    return grouped


def build_thumbnail_grid(filenames):
    """Builds the HTML for a row of thumbnails for one concentration."""
    thumbs = ""
    for filename in filenames:
        thumbs += f"""
        <a href="{CAPTURES_DIR}/{filename}" target="_blank">
            <div class="thumb">
                <img src="{CAPTURES_DIR}/{filename}">
                <p>{filename}</p>
            </div>
        </a>
        """
    return f'<div class="grid">{thumbs}</div>'


def build_focus_check_section():
    """
    Builds a small section showing the most recent focus-check photo
    (saved by capture.py's calibrate_focus() step), if one exists.
    """
    check_path = os.path.join(CAPTURES_DIR, FOCUS_CHECK_FILENAME)
    if not os.path.exists(check_path):
        return ""

    return f"""
    <details class="config" open>
        <summary>Focus Check (latest)</summary>
        <div class="config-body">
            <div class="grid">
                <a href="{CAPTURES_DIR}/{FOCUS_CHECK_FILENAME}" target="_blank">
                    <div class="thumb">
                        <img src="{CAPTURES_DIR}/{FOCUS_CHECK_FILENAME}">
                        <p>{FOCUS_CHECK_FILENAME}</p>
                    </div>
                </a>
            </div>
        </div>
    </details>
    """


def build_gallery_html():
    """Builds the full page: a collapsible folder-style tree of Config -> Concentration -> photos."""
    grouped = group_photos_by_config_and_concentration()

    total_photos = sum(
        len(filenames)
        for concentrations in grouped.values()
        for filenames in concentrations.values()
    )

    if not grouped:
        body = "<p>No photos found yet in captures/.</p>"
    else:
        body = ""
        for config_number in sorted(grouped.keys()):
            concentrations = grouped[config_number]
            photo_count = sum(len(files) for files in concentrations.values())

            concentration_sections = ""
            for concentration in sorted(concentrations.keys()):
                filenames = concentrations[concentration]
                concentration_sections += f"""
                <details class="concentration" open>
                    <summary>Concentration {concentration} mg/L ({len(filenames)} photos)</summary>
                    {build_thumbnail_grid(filenames)}
                </details>
                """

            body += f"""
            <details class="config" open>
                <summary>Config {config_number} ({photo_count} photos)</summary>
                <div class="config-body">
                    {concentration_sections}
                </div>
            </details>
            """

    html = f"""
    <html>
    <head>
        <title>HandyFluor Captures</title>
        <style>
            body {{ font-family: sans-serif; background: #fafafa; padding: 20px; }}

            details.config {{
                border: 1px solid #ccc;
                border-radius: 6px;
                margin-bottom: 12px;
                padding: 8px 12px;
                background: white;
            }}
            details.config > summary {{
                font-size: 18px;
                font-weight: bold;
                cursor: pointer;
                padding: 6px 0;
            }}
            .config-body {{ padding-left: 16px; }}

            details.concentration {{
                border-left: 3px solid #999;
                margin: 10px 0;
                padding-left: 10px;
            }}
            details.concentration > summary {{
                font-size: 14px;
                font-weight: 600;
                cursor: pointer;
                padding: 4px 0;
                color: #333;
            }}

            .grid {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 8px; }}
            .thumb {{ width: 180px; text-align: center; }}
            .thumb img {{ width: 180px; height: auto; border: 1px solid #ccc; }}
            .thumb p {{ font-size: 10px; word-wrap: break-word; color: #555; }}
        </style>
    </head>
    <body>
        <h2>HandyFluor Captures ({total_photos} photos total)</h2>
        {build_focus_check_section()}
        {body}
    </body>
    </html>
    """
    return html


class GalleryRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serves the generated gallery page at "/", and photo files normally otherwise."""

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            html = build_gallery_html()
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        else:
            super().do_GET()


def main():
    ip = get_local_ip()
    print("Gallery running! Open this on your Mac's browser:")
    print(f"  http://{ip}:{PORT}")

    server = http.server.HTTPServer(("0.0.0.0", PORT), GalleryRequestHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()