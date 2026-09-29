"""Config loader — reads YAML + .env into typed settings."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
ENV_PATH = ROOT / ".env"

# Load .env once at import time (no-op if missing)
load_dotenv(ENV_PATH, override=False)


@lru_cache(maxsize=8)
def load_yaml(name: str) -> dict[str, Any]:
    """Load a YAML config file from config/."""
    path = CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open() as f:
        return yaml.safe_load(f) or {}


def settings() -> dict[str, Any]:
    return load_yaml("settings.yaml")


def universe() -> dict[str, Any]:
    return load_yaml("universe.yaml")


def schedules() -> dict[str, Any]:
    return load_yaml("schedules.yaml")


def env(key: str, default: str | None = None, required: bool = False) -> str | None:
    v = os.environ.get(key, default)
    if required and not v:
        raise RuntimeError(
            f"Required env var {key!r} is not set. See .env.example."
        )
    return v


def is_paper() -> bool:
    return env("ENVIRONMENT", "paper") == "paper"
