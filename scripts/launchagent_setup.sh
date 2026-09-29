#!/usr/bin/env bash
# launchagent_setup.sh — render and register Artemis macOS LaunchAgents.
#
#   com.artemis.pipeline — data collection + signals + EOD analysis (Mon–Fri 17:00 local)
#                          Never submits orders.
#   com.artemis.trader   — unattended daily rebalance that SUBMITS ORDERS (Mon–Fri 06:35 local).
#                          Opt-in only: pass --with-trader and confirm interactively.
#
# Usage:
#   scripts/launchagent_setup.sh                 # pipeline only (recommended)
#   scripts/launchagent_setup.sh --with-trader   # pipeline + unattended trader
#   scripts/launchagent_setup.sh --uninstall     # remove both agents

set -euo pipefail

if [[ "$(uname)" != "Darwin" ]]; then
    echo "LaunchAgents are macOS-only. On Linux, schedule the pipeline with cron, e.g.:"
    echo "  0 17 * * 1-5  cd $(cd "$(dirname "$0")/.." && pwd) && .venv/bin/python scripts/run_pipeline.py"
    exit 1
fi

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "${SCRIPTS_DIR}/.." && pwd)"
LAUNCH_AGENTS="${HOME}/Library/LaunchAgents"
UID_NUM="$(id -u)"

WITH_TRADER=0
UNINSTALL=0
for arg in "$@"; do
    case "$arg" in
        --with-trader) WITH_TRADER=1 ;;
        --uninstall)   UNINSTALL=1 ;;
        *) echo "Unknown option: $arg"; exit 2 ;;
    esac
done

remove_agent() {
    local label="$1"
    launchctl bootout "gui/${UID_NUM}/${label}" 2>/dev/null || true
    rm -f "${LAUNCH_AGENTS}/${label}.plist"
    echo "    Removed ${label}"
}

install_agent() {
    local label="$1"
    local src="${SCRIPTS_DIR}/${label}.plist.template"
    local dest="${LAUNCH_AGENTS}/${label}.plist"

    echo "==> Installing ${label}..."
    mkdir -p "${LAUNCH_AGENTS}" "${HOME}/Library/Logs"
    # launchd does not expand variables, so write absolute paths in.
    sed -e "s#__ARTEMIS_ROOT__#${ROOT}#g" -e "s#__HOME__#${HOME}#g" "${src}" > "${dest}"
    plutil -lint "${dest}" >/dev/null
    launchctl bootout "gui/${UID_NUM}/${label}" 2>/dev/null || true
    launchctl bootstrap "gui/${UID_NUM}" "${dest}"
    echo "    Loaded: $(launchctl list | grep "${label}" || echo '(not found)')"
}

if [[ "${UNINSTALL}" == 1 ]]; then
    remove_agent "com.artemis.pipeline"
    remove_agent "com.artemis.trader"
    exit 0
fi

install_agent "com.artemis.pipeline"

if [[ "${WITH_TRADER}" == 1 ]]; then
    echo ""
    echo "WARNING: com.artemis.trader submits orders to your Alpaca account every weekday"
    echo "morning with nobody watching. Only enable this on a PAPER account you are happy"
    echo "to let the strategy manage unattended. Risk halts and the kill switch still apply."
    read -r -p "Type 'enable unattended trading' to continue: " answer
    if [[ "${answer}" == "enable unattended trading" ]]; then
        install_agent "com.artemis.trader"
    else
        echo "Skipped com.artemis.trader."
    fi
fi

echo ""
echo "Useful commands:"
echo "  Status:          launchctl list | grep artemis"
echo "  Pipeline log:    tail -f ~/Library/Logs/artemis_pipeline.log"
echo "  Trader log:      tail -f ~/Library/Logs/artemis_trader.log"
echo "  Remove agents:   scripts/launchagent_setup.sh --uninstall"
echo "  Manual dry-run:  .venv/bin/python scripts/run_daily_trade.py"
echo "  Manual trade:    .venv/bin/python scripts/run_daily_trade.py --live"
