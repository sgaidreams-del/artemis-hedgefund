#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Artemis installer — macOS / Linux
#
#   ./install.sh            full guided install
#   ./install.sh --dev      also install test/lint tooling
#   ./install.sh --keys     only (re)configure API keys
#
# Safe to re-run: every step is idempotent and existing keys are kept unless
# you type a new value.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -t 1 ]]; then
    B=$'\033[1m'; D=$'\033[2m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'
else
    B=""; D=""; G=""; Y=""; R=""; N=""
fi
step() { echo; echo "${B}━━ $1${N}"; }
ok()   { echo "  ${G}✓${N} $1"; }
warn() { echo "  ${Y}!${N} $1"; }
die()  { echo "  ${R}✗ $1${N}" >&2; exit 1; }
ask()  {  # ask "question" default(y|n) → returns 0 for yes
    local prompt="$1" def="${2:-y}" reply
    local hint="[Y/n]"; [[ "$def" == n ]] && hint="[y/N]"
    read -r -p "  $prompt $hint " reply || true
    reply="${reply:-$def}"
    [[ "$reply" =~ ^[Yy] ]]
}

DEV=0; KEYS_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --dev)  DEV=1 ;;
        --keys) KEYS_ONLY=1 ;;
        -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
        *) die "Unknown option: $arg (see --help)" ;;
    esac
done

PY=".venv/bin/python"

if [[ "$KEYS_ONLY" == 1 ]]; then
    python3 scripts/configure.py
    exit 0
fi

cat <<EOF
${B}
    █████╗ ██████╗ ████████╗███████╗███╗   ███╗██╗███████╗
   ██╔══██╗██╔══██╗╚══██╔══╝██╔════╝████╗ ████║██║██╔════╝
   ███████║██████╔╝   ██║   █████╗  ██╔████╔██║██║███████╗
   ██╔══██║██╔══██╗   ██║   ██╔══╝  ██║╚██╔╝██║██║╚════██║
   ██║  ██║██║  ██║   ██║   ███████╗██║ ╚═╝ ██║██║███████║
   ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝     ╚═╝╚═╝╚══════╝${N}
   ${D}AI-driven paper-trading research system — installer${N}

   ${Y}Paper trading only. Not financial advice. See README → Disclaimer.${N}
EOF

# ── 1. Prerequisites ─────────────────────────────────────────────────────────
step "1/7  Checking prerequisites"

PYTHON=""
for cand in python3.13 python3.12 python3.11 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        ver="$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
        major="${ver%%.*}"; minor="${ver##*.}"
        if [[ "$major" == 3 && "$minor" -ge 11 && "$minor" -le 13 ]]; then
            PYTHON="$cand"; break
        fi
    fi
done
[[ -n "$PYTHON" ]] || die "Python 3.11–3.13 is required (3.14 is not yet supported by numba).
     macOS: brew install python@3.13    Ubuntu: sudo apt install python3.12 python3.12-venv"
ok "Python $("$PYTHON" --version | cut -d' ' -f2) ($PYTHON)"

command -v node >/dev/null 2>&1 || die "Node.js 20+ is required for the dashboard.
     macOS: brew install node    Linux: https://nodejs.org/en/download"
node_major="$(node -p 'process.versions.node.split(".")[0]')"
[[ "$node_major" -ge 20 ]] || die "Node.js 20+ required (found $(node --version))."
ok "Node $(node --version)"

HAVE_DOCKER=0; HAVE_PSQL=0
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then HAVE_DOCKER=1; ok "Docker Compose found"; fi
if command -v psql >/dev/null 2>&1; then HAVE_PSQL=1; ok "PostgreSQL client found"; fi
[[ "$HAVE_DOCKER" == 1 || "$HAVE_PSQL" == 1 ]] || warn "Neither Docker nor PostgreSQL found — you'll need one (step 4)."

# ── 2. Python environment ────────────────────────────────────────────────────
step "2/7  Python environment"
if [[ ! -x "$PY" ]]; then
    "$PYTHON" -m venv .venv
    ok "Created .venv"
else
    ok "Reusing existing .venv"
fi
echo "  ${D}Installing Python packages — first run downloads ~2 GB (PyTorch, LightGBM, …).${N}"
"$PY" -m pip install --quiet --upgrade pip
if [[ "$DEV" == 1 ]]; then
    "$PY" -m pip install --quiet -e ".[dev]"
else
    "$PY" -m pip install --quiet -e .
fi
ok "Python packages installed"

# ── 3. Dashboard ─────────────────────────────────────────────────────────────
step "3/7  Dashboard (React)"
(cd dashboard && npm ci --silent --no-audit --no-fund)
ok "Dashboard packages installed"

# ── 4. API keys ──────────────────────────────────────────────────────────────
step "4/7  API keys"
echo "  ${D}You'll be asked for each key. Secrets are hidden as you type and stored only"
echo "  in .env (permissions 600, git-ignored). Press Enter to skip optional ones.${N}"
"$PY" scripts/configure.py

# ── 5. Database ──────────────────────────────────────────────────────────────
step "5/7  Database"
DB_MODE=""
if [[ "$HAVE_DOCKER" == 1 ]] && ask "Run PostgreSQL + Redis in Docker? (recommended if you don't already run Postgres)" y; then
    DB_MODE=docker
elif [[ "$HAVE_PSQL" == 1 ]] && ask "Use your existing local PostgreSQL (e.g. Homebrew)?" y; then
    DB_MODE=local
fi

case "$DB_MODE" in
    docker)
        "$PY" scripts/configure.py --set POSTGRES_PORT=5433 --set REDIS_PORT=6380 >/dev/null
        docker compose up -d
        echo -n "  Waiting for Postgres"
        for _ in $(seq 1 30); do
            if "$PY" -c 'import sys; from src.core.db import ping; sys.exit(0 if ping() else 1)' 2>/dev/null; then break; fi
            echo -n "."; sleep 2
        done
        echo
        "$PY" scripts/setup_db.py
        ;;
    local)
        port="$("$PY" scripts/configure.py --get POSTGRES_PORT)"
        echo "  ${D}Creating the '$("$PY" scripts/configure.py --get POSTGRES_USER)' role and database on 127.0.0.1:${port}"
        echo "  (connects as Postgres superuser '$(whoami)' — Homebrew's default).${N}"
        "$PY" scripts/setup_db.py --create-role
        ;;
    *)
        warn "Skipped. Point POSTGRES_* in .env at a PostgreSQL 14+ server, then run:"
        echo "      $PY scripts/setup_db.py"
        ;;
esac

# ── 6. Health check + history ────────────────────────────────────────────────
step "6/7  Health check"
if "$PY" scripts/health_check.py; then
    if ask "Download 2 years of price history now? (needs Alpaca keys, ~1 min)" y; then
        "$PY" scripts/seed_historical.py --years 2 || warn "Backfill failed — re-run later: $PY scripts/seed_historical.py --years 2"
    fi
else
    warn "Fix the items above, then re-run ./install.sh (it's safe to repeat)."
fi

# ── 7. Scheduling (macOS, optional) ──────────────────────────────────────────
step "7/7  Scheduling (optional)"
if [[ "$(uname)" == "Darwin" ]]; then
    echo "  ${D}The daily data pipeline collects prices/news/signals after market close."
    echo "  It never places orders. (Unattended trading is a separate opt-in — see README.)${N}"
    if ask "Schedule the data pipeline to run Mon–Fri at 17:00?" n; then
        scripts/launchagent_setup.sh
    fi
else
    echo "  Linux: add this to crontab -e to run the data pipeline after the close:"
    echo "      0 17 * * 1-5  cd $ROOT && $PY scripts/run_pipeline.py >> logs/pipeline.log 2>&1"
fi

cat <<EOF

${G}${B}Install complete.${N}

  Start the dashboard:     ${B}./start.sh${N}    → http://localhost:5173
  Run the data pipeline:   ${B}$PY scripts/run_pipeline.py${N}
  Preview today's trades:  ${B}$PY scripts/run_daily_trade.py${N}    (dry run, submits nothing)
  Change API keys later:   ${B}./install.sh --keys${N}

EOF
