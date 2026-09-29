#!/usr/bin/env python3
"""Manual pipeline runner — runs each enabled data job in sequence.

Useful for local dev/testing without Celery. Production uses the cron
schedule defined in config/schedules.yaml.
"""
from __future__ import annotations

import atexit
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.logging import log_activity  # noqa: E402
from src.core.config import universe as universe_cfg  # noqa: E402
from src.data.collectors.price_collector import collect_eod  # noqa: E402
from src.data.collectors.news_collector import collect as collect_news  # noqa: E402
from src.data.collectors.macro_collector import collect as collect_macro  # noqa: E402
from src.data.collectors.fundamentals_collector import collect as collect_fundamentals  # noqa: E402
from src.data.collectors.finnhub_collector import collect as collect_insider_transactions  # noqa: E402
from src.data.collectors.options_flow_collector import collect as collect_options_flow  # noqa: E402
from src.data.feature_store.store import compute_daily as compute_features  # noqa: E402
from src.data.quality.watchdog import run as quality_watchdog  # noqa: E402
from src.data.universe import refresh_daily as refresh_universe  # noqa: E402
from src.monitoring.reports.daily import generate_and_post as daily_report  # noqa: E402
from src.signals.sentiment.aggregator import run_sentiment_pipeline  # noqa: E402
from src.signals.technical.composite import run_technical_pipeline  # noqa: E402
from src.signals.regime.detector import run_regime_pipeline  # noqa: E402
from src.signals.llm.deepseek_analyzer import run_llm_pipeline  # noqa: E402
from src.signals.alternative.insider import run_insider_pipeline  # noqa: E402
from src.signals.alternative.short_interest import run_short_interest_pipeline  # noqa: E402
from src.signals.alternative.options_flow import run_options_flow_pipeline  # noqa: E402
from src.signals.alternative.volume_anomaly import run_volume_anomaly_pipeline  # noqa: E402
from src.strategy.universe_scorer import run_ensemble_pipeline  # noqa: E402
from src.strategy.memory.reflector import run_reflections  # noqa: E402
from src.strategy.memory.eod_mover_analysis import run_eod_mover_analysis  # noqa: E402
from src.monitoring.snapshots import record_daily_snapshot  # noqa: E402
from src.simulation.engine import run_sim_step  # noqa: E402

LOCK_PATH = ROOT / "logs" / "run_pipeline.lock"
_LOCK_HANDLE = None


def _acquire_lock() -> bool:
    """Prevent overlapping pipeline runs from trampling each other."""
    global _LOCK_HANDLE
    LOCK_PATH.parent.mkdir(exist_ok=True)
    handle = LOCK_PATH.open("w")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        log_activity("pipeline", "run", "skipped", reason="already_running")
        return False

    handle.seek(0)
    handle.truncate()
    handle.write(f"{Path(sys.argv[0]).name}:{os.getpid()}\n")
    handle.flush()
    _LOCK_HANDLE = handle

    def _release() -> None:
        global _LOCK_HANDLE
        if _LOCK_HANDLE is None:
            return
        try:
            fcntl.flock(_LOCK_HANDLE.fileno(), fcntl.LOCK_UN)
        finally:
            _LOCK_HANDLE.close()
            _LOCK_HANDLE = None

    atexit.register(_release)
    return True


def _seed_tickers() -> list[str]:
    return universe_cfg()["seed_tickers"]


def _all_monitored_tickers() -> list[str]:
    cfg = universe_cfg()
    return list(dict.fromkeys(cfg["seed_tickers"] + cfg.get("extended_watchlist", [])))


def _run_sentiment() -> int:
    return run_sentiment_pipeline(_seed_tickers())


def _run_technical() -> int:
    return run_technical_pipeline(_seed_tickers())


def _run_llm() -> int:
    return run_llm_pipeline(_seed_tickers())


def _run_insider() -> int:
    return run_insider_pipeline(_seed_tickers())


def _run_short_interest() -> int:
    return run_short_interest_pipeline(_seed_tickers())


def _run_options_flow_signal() -> int:
    return run_options_flow_pipeline(_seed_tickers())


def _run_volume_anomaly() -> int:
    # Run on all monitored tickers (seed + extended) so the EOD scanner has data
    return run_volume_anomaly_pipeline(_all_monitored_tickers())


def _collect_eod_extended() -> dict:
    """Collect OHLCV for extended watchlist tickers (seed tickers collected separately)."""
    cfg = universe_cfg()
    extended = cfg.get("extended_watchlist", [])
    if not extended:
        return {"tickers": 0, "rows": 0}
    return collect_eod(tickers=extended)


def _run_alpha() -> dict:
    """Runs in a subprocess — see scripts/_run_alpha_isolated.py for why."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "_run_alpha_isolated.py")],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alpha pipeline subprocess exited {result.returncode}: {result.stderr[-1000:]}"
        )
    return json.loads(result.stdout.strip().splitlines()[-1])


def _run_ensemble() -> dict:
    return run_ensemble_pipeline(_seed_tickers())


JOBS = [
    ("universe.refresh", refresh_universe),
    ("price.eod", collect_eod),
    ("price.eod_extended", _collect_eod_extended),
    ("news.rss", collect_news),
    ("macro.fred", collect_macro),
    ("fundamentals.daily", collect_fundamentals),
    ("insider.finnhub", collect_insider_transactions),
    ("options_flow.collect", collect_options_flow),
    ("features.daily", compute_features),
    ("signals.sentiment", _run_sentiment),
    ("signals.technical", _run_technical),
    ("signals.regime", run_regime_pipeline),
    ("signals.llm", _run_llm),
    ("signals.insider", _run_insider),
    ("signals.short_interest", _run_short_interest),
    ("signals.options_flow", _run_options_flow_signal),
    ("signals.volume_anomaly", _run_volume_anomaly),
    ("signals.alpha", _run_alpha),
    ("strategy.ensemble", _run_ensemble),
    ("strategy.reflections", run_reflections),
    ("strategy.eod_movers", run_eod_mover_analysis),
    ("quality.watchdog", quality_watchdog),
    ("portfolio.snapshot", record_daily_snapshot),
    ("sim.step", run_sim_step),
    ("report.daily", daily_report),
]


def main() -> int:
    if not _acquire_lock():
        print("Pipeline already running; skipping duplicate invocation.")
        return 0

    failures = 0
    for name, fn in JOBS:
        print(f"\n--- {name} ---")
        try:
            result = fn()
            print(f"✓ {name}: {result}")
        except Exception as e:
            print(f"✗ {name}: {e}")
            failures += 1
    print(f"\n=== {len(JOBS) - failures}/{len(JOBS)} jobs OK ===")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
