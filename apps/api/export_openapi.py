"""Explicit build-time public contract export; no lifespan, engine or data access."""
import json
from pathlib import Path
from fashion_api.main import create_app

if __name__ == "__main__":
    destination = Path(__file__).with_name("openapi.json")
    destination.write_text(json.dumps(create_app().openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
