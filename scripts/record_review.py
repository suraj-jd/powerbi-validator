"""Record a local Windows review with an existing ffmpeg installation.

Create the supplied stop file to finalize the MP4 cleanly.
"""

import argparse
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stop-file", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() or args.stop_file.exists():
        raise SystemExit("Choose unused recording and stop-file paths.")
    command = [args.ffmpeg, "-hide_banner", "-f", "gdigrab", "-framerate", "8", "-draw_mouse", "1",
               "-i", "desktop", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264",
               "-preset", "ultrafast", "-crf", "26", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
               "-t", "1800", str(args.output)]
    with args.output.with_suffix(".log").open("wb") as log:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        print("Recording started", flush=True)
        try:
            while process.poll() is None and not args.stop_file.exists():
                time.sleep(0.2)
        finally:
            if process.poll() is None:
                process.communicate(input=b"q", timeout=30)
        if process.returncode:
            raise SystemExit(process.returncode)
    print(f"Saved: {args.output}", flush=True)


if __name__ == "__main__":
    main()
