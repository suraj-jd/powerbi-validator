"""Export full-resolution documentation screenshots from a verified review recording.

The capture manifest contains name, epochMilliseconds, and email_hidden=true
for each screenshot. Review account privacy before recording these markers.
This script never launches the app, seeds sample data, or edits its database.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=Path, required=True)
    parser.add_argument("--capture-times", type=Path, required=True)
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg"))
    parser.add_argument("--output", type=Path, default=Path("docs/screenshots"))
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1020)
    args = parser.parse_args()
    if not args.ffmpeg:
        parser.error("Provide an existing ffmpeg executable using --ffmpeg.")
    log = args.recording.with_suffix(".log").read_text(encoding="utf-8", errors="replace")
    match = re.search(r"start: ([0-9.]+)", log)
    if not match:
        parser.error("The recording log does not contain its capture start time.")
    started_at = float(match.group(1))
    captures = json.loads(args.capture_times.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    for capture in captures:
        name = capture["name"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            parser.error("Screenshot names must contain only letters, numbers, hyphens, and underscores.")
        if capture.get("email_hidden") is not True:
            parser.error(f"Account email privacy was not verified for {name}.")
        offset = capture["epochMilliseconds"] / 1000 - started_at + 0.25
        if offset < 0:
            parser.error(f"Capture {name} predates the recording.")
        destination = args.output / (name + ".png")
        subprocess.run([args.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", str(offset), "-i", str(args.recording), "-frames:v", "1",
                        "-vf", f"crop={args.width}:{args.height}:0:0", str(destination)], check=True)
        if not destination.is_file():
            raise RuntimeError(f"No frame was exported for {name}.")
        print(f"Saved {destination}")


if __name__ == "__main__":
    main()
