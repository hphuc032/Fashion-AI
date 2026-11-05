"""Explicit, bounded download of only the two OCR and two translation models.

Never called automatically by the application. Sources are the official PaddleX
BOS catalog and the Argos package index. No model or generated file belongs in Git.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
import tempfile
import zipfile

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import load_settings
from app.providers.ocr.paddle_provider import MODEL_NAMES


def download(url: str, destination: Path) -> None:
    if destination.is_file():
        return
    partial = destination.with_suffix(destination.suffix + ".part")
    total = 0
    try:
        with requests.get(url, stream=True, timeout=(15, 60)) as response:
            response.raise_for_status()
            with partial.open("wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    total += len(chunk)
                    if total > 512 * 1024 * 1024:
                        raise ValueError("Model download exceeds 512 MiB")
                    output.write(chunk)
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)
    print(f"Downloaded {destination.name}: {total} bytes")


def safe_name(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
        raise ValueError("Unsafe model archive path")


def install_archive(archive: Path, root: Path, expected: str) -> None:
    if (root / expected).is_dir():
        return
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as temporary:
        stage = Path(temporary)
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as zipped:
                if sum(info.file_size for info in zipped.infolist()) > 1024**3:
                    raise ValueError("Archive too large")
                for info in zipped.infolist():
                    safe_name(info.filename)
                    if (info.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError("Archive contains symlink")
                zipped.extractall(stage)
        else:
            with tarfile.open(archive) as tar:
                entries = tar.getmembers()
                if sum(info.size for info in entries) > 1024**3:
                    raise ValueError("Archive too large")
                for info in entries:
                    safe_name(info.name)
                    if not info.isdir() and not info.isfile():
                        raise ValueError("Archive contains special entry")
                tar.extractall(stage, members=entries, filter="data")
        candidate = stage / expected
        if not candidate.is_dir():
            children = [p for p in stage.iterdir() if p.is_dir()]
            if len(children) != 1:
                raise ValueError("Unexpected model archive layout")
            candidate = children[0]
        manifest = {str(p.relative_to(candidate)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in candidate.rglob("*") if p.is_file()}
        (candidate / "local-manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        shutil.move(str(candidate), str(root / expected))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument("--translation", action="store_true")
    args = parser.parse_args()
    if not args.ocr and not args.translation:
        parser.error("Select --ocr and/or --translation")
    settings = load_settings()
    downloads = settings.storage_root / "models" / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    if args.ocr:
        for name in MODEL_NAMES:
            archive = downloads / f"{name}_infer.tar"
            download(f"https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/{archive.name}", archive)
            install_archive(archive, settings.ocr_models_dir, name)
    if args.translation:
        response = requests.get("https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json", timeout=30)
        response.raise_for_status()
        index = response.json()
        for source, target in (("zh", "en"), ("en", "vi")):
            package = next(p for p in index if p["from_code"] == source and p["to_code"] == target and p["package_version"] == "1.9")
            name = f"translate-{source}_{target}-1_9"
            archive = downloads / f"{name}.argosmodel"
            download(package["links"][0], archive)
            install_archive(archive, settings.argos_models_dir, name)
    print("Models ready. Downloads only; application performs no model download.")


if __name__ == "__main__":
    main()
