"""Generate a rights-safe silent vertical fixture; does not use user videos."""
import argparse
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=Path("storage/temp/synthetic.mp4"))
args = parser.parse_args()
args.output.parent.mkdir(parents=True, exist_ok=True)
subprocess.run([os.getenv("FFMPEG_PATH", "ffmpeg"), "-y", "-v", "error", "-f", "lavfi",
                "-i", "testsrc2=size=360x640:rate=25:duration=3", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", str(args.output)], shell=False, check=True, timeout=60)
print(f"Created: {args.output}")
