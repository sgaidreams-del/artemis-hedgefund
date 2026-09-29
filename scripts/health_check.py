#!/usr/bin/env python3
"""Smoke-test that all infrastructure pieces are reachable."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.config import env  # noqa: E402
from src.core.db import ping  # noqa: E402


def main() -> int:
    print("=== Artemis Health Check ===\n")
    rc = 0

    # 1. .env presence
    env_path = ROOT / ".env"
    if env_path.exists():
        print(f"✓ .env present at {env_path}")
    else:
        print(f"✗ .env MISSING — copy from .env.example and fill values")
        rc = 1

    # 2. Required env vars
    required = [
        "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USER", "POSTGRES_DB", "POSTGRES_PASSWORD",
    ]
    for k in required:
        v = env(k)
        print(f"  {'✓' if v else '✗'} {k}={'<set>' if v else '<MISSING>'}")
        if not v:
            rc = 1

    # 3. Optional env vars (warn but don't fail)
    optional = [
        "ALPACA_API_KEY", "ALPACA_API_SECRET", "DEEPSEEK_API_KEY", "FINNHUB_API_KEY",
        "FRED_API_KEY", "POLYGON_API_KEY",
    ]
    for k in optional:
        v = env(k)
        print(f"  {'✓' if v else '⚠'} {k}={'<set>' if v else '<not set — feature disabled>'}")

    # 4. Postgres
    print()
    if ping():
        print("✓ PostgreSQL reachable")
    else:
        print("✗ PostgreSQL NOT reachable — start with `docker compose up -d`")
        rc = 1

    print()
    print("OK" if rc == 0 else "FAIL — see above")
    return rc


if __name__ == "__main__":
    sys.exit(main())
