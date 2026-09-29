#!/usr/bin/env python3
"""Interactive API-key setup for Artemis. Writes .env (mode 600).

Re-run any time to add or rotate keys — press Enter to keep a current value.
Secrets are read with hidden input and never printed back.

    python scripts/configure.py                    # interactive
    python scripts/configure.py --no-verify        # skip live key checks
    python scripts/configure.py --non-interactive  # take values from the environment
    python scripts/configure.py --set POSTGRES_PORT=5433
    python scripts/configure.py --get POSTGRES_USER  # print one NON-secret value

Standard library only, so it runs before `pip install`.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import secrets
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / ".env.example"
LINE_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    url: str
    required: bool = False
    secret: bool = True
    hint: str = ""


# Prompted in this order, grouped by service.
FIELDS: list[tuple[str, list[Field]]] = [
    ("Alpaca — broker + market data (REQUIRED)", [
        Field("ALPACA_API_KEY", "Alpaca API key ID", "https://app.alpaca.markets/signup",
              required=True, secret=False, hint="Paper keys start with 'PK'."),
        Field("ALPACA_API_SECRET", "Alpaca secret key", "https://app.alpaca.markets/", required=True),
    ]),
    ("DeepSeek — LLM analysis (recommended)", [
        Field("DEEPSEEK_API_KEY", "DeepSeek API key", "https://platform.deepseek.com/api_keys",
              hint="Without it, LLM sentiment, debate, reflections and mover analysis are skipped."),
    ]),
    ("Finnhub — insider trades + earnings calendar (optional, free)", [
        Field("FINNHUB_API_KEY", "Finnhub API key", "https://finnhub.io/register"),
    ]),
    ("FRED — macro data (optional, free)", [
        Field("FRED_API_KEY", "FRED API key", "https://fred.stlouisfed.org/docs/api/api_key.html"),
    ]),
    ("Polygon.io — fallback price data (optional, paid)", [
        Field("POLYGON_API_KEY", "Polygon API key", "https://polygon.io/dashboard/api-keys"),
    ]),
    ("Reddit — social sentiment (optional, free)", [
        Field("REDDIT_CLIENT_ID", "Reddit client ID", "https://www.reddit.com/prefs/apps", secret=False),
        Field("REDDIT_CLIENT_SECRET", "Reddit client secret", "https://www.reddit.com/prefs/apps"),
    ]),
]
SECRET_KEYS = {f.key for _, group in FIELDS for f in group if f.secret} | {
    "POSTGRES_PASSWORD", "DISCORD_ARTEMIS_TOKEN",
}

BOLD, DIM, GREEN, YELLOW, RED, RESET = (
    ("\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[31m", "\033[0m")
    if sys.stdout.isatty() else ("",) * 6
)


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text().splitlines():
        m = LINE_RE.match(raw.strip())
        if m:
            values[m.group(1)] = _strip_value(m.group(2))
    return values


def _strip_value(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == "'" and v[-1] == "'":
        return v[1:-1].replace("\\'", "'")
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        return re.sub(r"\\(.)", r"\1", v[1:-1])
    # Drop inline comments ("paper   # paper | live") on unquoted values.
    return re.split(r"\s+#", v, maxsplit=1)[0].strip()


def render(template: Path, values: dict[str, str]) -> str:
    """Fill the .env.example layout with values, keeping its comments and order."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in template.read_text().splitlines():
        m = LINE_RE.match(raw.strip())
        if not m:
            out.append(raw)
            continue
        key = m.group(1)
        seen.add(key)
        out.append(f"{key}={_quote(values.get(key, ''))}")
    extras = [k for k in values if k not in seen]
    if extras:
        out += ["", "# ── Other (kept from previous .env) ──"]
        out += [f"{k}={_quote(values[k])}" for k in extras]
    return "\n".join(out) + "\n"


def _quote(v: str) -> str:
    """Quote values with special characters so python-dotenv and docker compose
    both read them literally (single quotes = no interpolation in either)."""
    if not re.search(r"[\s#'\"$`\\]", v):
        return v
    if "'" not in v:
        return f"'{v}'"
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_env(path: Path, content: str) -> None:
    """Atomic write with 0600 permissions from the start (no world-readable window)."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".env.", text=True)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def prompt_field(field: Field, current: str) -> str:
    status = f"{GREEN}currently set{RESET}" if current else f"{DIM}not set{RESET}"
    req = f"{RED}required{RESET}" if field.required else f"{DIM}optional{RESET}"
    print(f"  {BOLD}{field.label}{RESET} ({req}, {status})")
    print(f"  {DIM}Get one: {field.url}{RESET}")
    if field.hint:
        print(f"  {DIM}{field.hint}{RESET}")
    ask = "  Enter to keep current: " if current else "  Enter to skip: " if not field.required else "  > "
    while True:
        entered = (getpass.getpass(ask + "(input hidden) ") if field.secret else input(ask)).strip()
        if entered:
            return entered
        if current or not field.required:
            return current
        print(f"  {YELLOW}This key is required for trading and portfolio features.{RESET}")
        if input("  Leave it blank for now? [y/N] ").strip().lower() == "y":
            return ""


# ── Live verification (read-only calls) ──────────────────────────────────────

def _get(url: str, headers: dict[str, str]) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers={**headers, "User-Agent": "artemis-configure"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (urllib.error.URLError, TimeoutError, ValueError):
        return 0, {}


def verify(values: dict[str, str]) -> None:
    print(f"\n{BOLD}Verifying keys (read-only requests)…{RESET}")
    if values.get("ALPACA_API_KEY") and values.get("ALPACA_API_SECRET"):
        base = values.get("ALPACA_BASE_URL") or "https://paper-api.alpaca.markets"
        code, body = _get(f"{base.rstrip('/')}/v2/account", {
            "APCA-API-KEY-ID": values["ALPACA_API_KEY"],
            "APCA-API-SECRET-KEY": values["ALPACA_API_SECRET"],
        })
        mode = "paper" if "paper" in base else "LIVE"
        _report("Alpaca", code, f"{mode} account, status {body.get('status', '?')}")
    if values.get("DEEPSEEK_API_KEY"):
        base = values.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
        code, _ = _get(f"{base.rstrip('/')}/models",
                       {"Authorization": f"Bearer {values['DEEPSEEK_API_KEY']}"})
        _report("DeepSeek", code)
    if values.get("FINNHUB_API_KEY"):
        code, _ = _get("https://finnhub.io/api/v1/quote?symbol=AAPL",
                       {"X-Finnhub-Token": values["FINNHUB_API_KEY"]})
        _report("Finnhub", code)


def _report(name: str, code: int, ok_detail: str = "") -> None:
    if code == 200:
        print(f"  {GREEN}✓{RESET} {name} key works{f' ({ok_detail})' if ok_detail else ''}")
    elif code in (401, 403):
        print(f"  {RED}✗{RESET} {name} rejected the key (HTTP {code}) — re-run to fix it")
    elif code == 0:
        print(f"  {YELLOW}?{RESET} {name} unreachable (network) — key not checked")
    else:
        print(f"  {YELLOW}?{RESET} {name} returned HTTP {code} — key not confirmed")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Configure Artemis API keys (.env).")
    ap.add_argument("--env-file", type=Path, default=ROOT / ".env")
    ap.add_argument("--no-verify", action="store_true", help="skip live key checks")
    ap.add_argument("--non-interactive", action="store_true",
                    help="no prompts; take keys from environment variables of the same name")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="set a value without prompting (repeatable)")
    ap.add_argument("--get", metavar="KEY", help="print one non-secret value and exit")
    args = ap.parse_args()

    values = {**parse_env(TEMPLATE), **parse_env(args.env_file)}

    if args.get:
        if args.get in SECRET_KEYS:
            print(f"refusing to print secret {args.get}", file=sys.stderr)
            return 2
        print(values.get(args.get, ""))
        return 0

    for item in args.set:
        key, sep, val = item.partition("=")
        if not sep or not LINE_RE.match(f"{key}=x"):
            print(f"bad --set {item!r}; expected KEY=VALUE", file=sys.stderr)
            return 2
        values[key] = val

    interactive = not args.non_interactive and not args.set and sys.stdin.isatty()
    if args.non_interactive:
        for _, group in FIELDS:
            for f in group:
                if os.environ.get(f.key):
                    values[f.key] = os.environ[f.key]
    elif interactive:
        print(f"\n{BOLD}Artemis API key setup{RESET}")
        print(f"{DIM}Keys are saved only to {args.env_file} (permissions 600, git-ignored).{RESET}")
        for title, group in FIELDS:
            print(f"\n{BOLD}── {title}{RESET}")
            for f in group:
                values[f.key] = prompt_field(f, values.get(f.key, ""))

    if not values.get("POSTGRES_PASSWORD"):
        values["POSTGRES_PASSWORD"] = secrets.token_urlsafe(24)
        print(f"\n{GREEN}✓{RESET} Generated a random database password.")

    if "paper" not in values.get("ALPACA_BASE_URL", "paper"):
        print(f"\n{RED}{BOLD}WARNING: ALPACA_BASE_URL points at a LIVE trading endpoint.{RESET} "
              "Artemis is built and tested for paper trading only.")
    if values.get("ALPACA_API_KEY", "").startswith("AK") and "paper" in values.get("ALPACA_BASE_URL", ""):
        print(f"\n{YELLOW}Note: that looks like a live Alpaca key (AK…) but the URL is paper. "
              f"Paper keys start with PK.{RESET}")

    write_env(args.env_file, render(TEMPLATE, values))
    print(f"\n{GREEN}✓{RESET} Wrote {args.env_file}")

    print(f"\n{BOLD}Summary{RESET}")
    for _, group in FIELDS:
        for f in group:
            mark = f"{GREEN}✓ set{RESET}" if values.get(f.key) else (
                f"{RED}✗ missing{RESET}" if f.required else f"{DIM}– skipped{RESET}")
            print(f"  {f.key:<22} {mark}")

    if interactive and not args.no_verify:
        verify(values)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nAborted — .env unchanged.")
        sys.exit(130)
