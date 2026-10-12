"""Read the canonical application version from the repository root."""

from pathlib import Path


APP_VERSION = (Path(__file__).resolve().parents[1] / "VERSION").read_text().strip()
