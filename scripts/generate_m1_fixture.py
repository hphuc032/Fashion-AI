"""Synthetic Chinese fashion-caption fixture, never third-party video."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import load_settings


def generate_fixture(output: Path, ffmpeg: str, font_path: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(str(font_path), 48)
    small = ImageFont.truetype(str(font_path), 30)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        folder = Path(temporary)
        for index in range(6):
            image = Image.new("RGB", (540, 960), "#13213b")
            draw = ImageDraw.Draw(image)
            draw.rectangle((30 + index * 15, 580, 220 + index * 15, 830), fill="#334a69")
            draw.text((32, 160), "男生穿搭" if index < 3 else "我喜欢这件衬衫", font=font, fill="white")
            draw.text((32, 320), "秋冬新款", font=font, fill="#ffe088")
            draw.text((32, 440), "ABC 123", font=small, fill="white")
            image.save(folder / f"frame-{index:02d}.png")
        subprocess.run([ffmpeg, "-nostdin", "-y", "-v", "error", "-framerate", "1", "-i", str(folder / "frame-%02d.png"),
                        "-r", "25", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output)],
                       check=True, shell=False, timeout=60, capture_output=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", type=Path, default=Path(os.getenv("WINDIR", "")) / "Fonts" / "msyh.ttc")
    parser.add_argument("--output", type=Path, default=Path("storage/temp/m1-chinese.mp4"))
    args = parser.parse_args()
    generate_fixture(args.output, load_settings().ffmpeg_path, args.font)
    print(f"Created synthetic Chinese fixture: {args.output}")
