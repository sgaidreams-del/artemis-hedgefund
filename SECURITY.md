# Security

## Reporting a vulnerability

Please **don't open a public issue** for security problems. Use GitHub's
[private vulnerability reporting](../../security/advisories/new) (Security tab → *Report a
vulnerability*). Include steps to reproduce, and we'll respond as soon as we can.

## Threat model

Artemis is a **single-user application that runs on your own machine**. It holds broker API keys
that can place orders, so we assume:

- **Trusted:** you, your user account, and the files in this repo.
- **Untrusted:**
  - every website your browser visits while the dashboard is running;
  - other users and devices on your network;
  - all external data, including news headlines, API responses and LLM output.

It is **not** designed to be exposed to the internet or shared between users. There is no login.

## Protections

| Area | Protection |
|---|---|
| **Secrets** | Keys live only in `.env`, which `scripts/configure.py` writes atomically with mode `600`. `.env` is git-ignored. Secrets are entered with hidden input, never printed back, and `--get` refuses to print them. The database password is randomly generated per install, with no hardcoded fallback. |
| **Network exposure** | The API, dashboard, Postgres (Docker) and Redis (Docker) all bind to `127.0.0.1`. |
| **Cross-site request forgery** | Every non-GET API request must carry an `X-Artemis-Client: dashboard` header, and requests with a foreign `Origin` are refused. A custom header forces a CORS preflight, which fails for any origin that isn't allowlisted, so a malicious web page can't trigger a rebalance or disable the kill switch. |
| **DNS rebinding** | A trusted-host check rejects any `Host` other than `localhost` or `127.0.0.1`, so a rebinding attacker can't read portfolio data either. |
| **SQL injection** | All queries are parameterized. Dynamic identifiers use `psycopg.sql.Identifier`. |
| **Order safety** | A single fail-closed pre-trade gate covers limit-only orders, quantity and dollar caps, a price collar, stale-quote rejection, a rate limit, idempotency and market hours. Loss and drawdown halts freeze trading, and the kill switch also cancels open orders. |
| **Unattended trading** | Off by default. It needs `--with-trader` and a typed confirmation phrase. The installer never enables it. |
| **Live money** | Paper endpoint by default. `configure.py` warns loudly if a live URL is configured. |

## Pre-release audit (2026-09)

A security review was done before the first public release. Findings and how each was resolved:

| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | **High** | **CSRF on order-placing endpoints.** `POST /api/trading/rebalance/execute` and `POST /api/kill-switch/resume` took no body, so any website could send them as "simple" cross-origin requests. CORS only hides the response; it doesn't block the request. A malicious page could have submitted a rebalance or turned the kill switch off. | Fixed. A required custom header plus an Origin check (`dashboard_api/main.py`), covered by tests in `tests/test_api_csrf_guard.py`. |
| 2 | Medium | **DNS rebinding** could let a website read `/api/*` portfolio data through a hostname that resolves to 127.0.0.1. | Fixed. `TrustedHostMiddleware`. |
| 3 | Medium | **Hardcoded default DB password** in `src/core/db.py`, `docker-compose.yaml` and the docs. | Fixed. The fallback is removed, Compose requires a value, and the installer generates a random password. |
| 4 | Low | Personal machine paths in LaunchAgent plists and a tracked `.claude/settings.local.json`. | Fixed. The plists are now templates rendered at install time, and the local settings file is untracked and git-ignored. |
| 5 | Low | Table and column names interpolated into SQL with an f-string in the data-quality watchdog. The values were internal constants, so it wasn't exploitable. | Hardened with `sql.Identifier`. |
| 6 | Info | A secret scan of the working tree and full git history found no API keys, tokens or private keys. | The public repository was also published with fresh history. |

## Known residual risks

- **Prompt injection via news.** Headlines are passed to an LLM whose output influences signals.
  A crafted headline could skew one signal. It can't bypass the pre-trade gate or risk limits,
  which are deterministic code.
- **Error messages** returned by the API can include exception text. That's acceptable on
  localhost, but it's one more reason not to expose the API.
- **Pickled models.** The regime model in `models/` is loaded with `pickle`. Only load model
  files you generated yourself.
- **Third-party scrapers.** `yfinance` is unofficial. Its data isn't authenticated and may be
  wrong.
- **Dependency vulnerabilities.** Run `pip-audit` and `npm audit` periodically.

## If a key leaks

1. Revoke or regenerate it immediately in the provider's dashboard (Alpaca, DeepSeek, …).
2. Run `./install.sh --keys` to store the new key.
3. If it was an Alpaca key, check the account's order history for activity you don't recognize.
