"""Options flow collector — populates the options_flow table.

Volume / put-call ratio / unusual-volume come from Alpaca's option bars
(free indicative feed — omit `end` so the request doesn't fall inside the
free tier's 15-minute embargo; an explicit `end` near "now" raises
"OPRA agreement is not signed" even though no agreement is actually
missing). IV isn't available on this account's feed (Alpaca returns
implied_volatility=None regardless of feed), so IV comes from yfinance's
existing options.get_options_chain(), already used by the execution path.

iv_rank is a percentile of today's ATM IV against this ticker's own
history accumulated in options_flow.metadata — there's no broker-provided
1yr IV history, so the rank is only as good as how many days we've
collected. Early on this resolves to insufficient_data, same cold-start
behavior the rest of the system already has for ensemble_scores etc.
"""
from __future__ import annotations

from datetime import date, timedelta

from psycopg.types.json import Json

from ...core.config import env, universe
from ...core.db import conn
from ...core.logging import get_logger, log_activity
from ...data.options_flow import classify_signal

log = get_logger("options_flow_collector")

_STRIKE_BAND_PCT = 0.10  # ±10% of spot
_EXPIRY_MIN_DAYS = 1
_EXPIRY_MAX_DAYS = 45
_UNUSUAL_VOLUME_MULTIPLE = 2.0  # today's volume vs trailing-day average
_MAX_QUOTE_AGE_SECONDS = 900  # 15min — beyond this, Alpaca's free-tier quote is unreliable for strike filtering


def _spot_price(ticker: str) -> float | None:
    """Alpaca's latest quote if fresh enough, else yfinance's last close.

    Seen in practice: Alpaca's free IEX quote can be hours stale and wrong
    by a large margin (e.g. a split-adjustment mismatch), which silently
    produces zero contracts in the strike-band filter rather than a loud
    error — this is purely for picking a reasonable strike band, not a
    trade decision, so a same-day yfinance close is an acceptable fallback.
    """
    from ...execution.broker import get_latest_quote

    quote = get_latest_quote(ticker)
    if quote and quote.get("age_seconds", float("inf")) <= _MAX_QUOTE_AGE_SECONDS:
        return quote["price"]

    import yfinance as yf

    hist = yf.Ticker(ticker).history(period="1d")
    if hist.empty:
        return None
    return float(hist["Close"].iloc[-1])


def _option_client():
    from alpaca.data.historical.option import OptionHistoricalDataClient

    return OptionHistoricalDataClient(
        api_key=env("ALPACA_API_KEY", required=True),
        secret_key=env("ALPACA_API_SECRET", required=True),
    )


def _nearest_expiry_chain(client, ticker: str, spot: float) -> tuple[str, list[str], list[str]] | None:
    """Return (expiry, call_symbols, put_symbols) for the nearest expiry within the window."""
    from alpaca.data.requests import OptionChainRequest

    lo, hi = round(spot * (1 - _STRIKE_BAND_PCT), 2), round(spot * (1 + _STRIKE_BAND_PCT), 2)
    req = OptionChainRequest(
        underlying_symbol=ticker,
        strike_price_gte=str(lo),
        strike_price_lte=str(hi),
        expiration_date_gte=(date.today() + timedelta(days=_EXPIRY_MIN_DAYS)).isoformat(),
        expiration_date_lte=(date.today() + timedelta(days=_EXPIRY_MAX_DAYS)).isoformat(),
    )
    chain = client.get_option_chain(req)
    if not chain:
        return None

    by_expiry: dict[str, dict[str, list[str]]] = {}
    for symbol in chain:
        # Alpaca's chain keys are unpadded: ROOT + YYMMDD + C/P + strike*1000
        rest = symbol[len(ticker):]
        exp = f"20{rest[0:2]}-{rest[2:4]}-{rest[4:6]}"
        cp = "calls" if rest[6] == "C" else "puts"
        by_expiry.setdefault(exp, {"calls": [], "puts": []})[cp].append(symbol)

    nearest = min(by_expiry.keys())
    return nearest, by_expiry[nearest]["calls"], by_expiry[nearest]["puts"]


def _volume_metrics(client, call_symbols: list[str], put_symbols: list[str]) -> dict | None:
    from alpaca.data.requests import OptionBarsRequest
    from alpaca.data.timeframe import TimeFrame

    symbols = call_symbols + put_symbols
    if not symbols:
        return None

    req = OptionBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=date.today() - timedelta(days=6),
    )
    bars = client.get_option_bars(req).data

    call_volume = sum(bars[s][-1].volume for s in call_symbols if bars.get(s))
    put_volume = sum(bars[s][-1].volume for s in put_symbols if bars.get(s))

    today_total = call_volume + put_volume
    trailing_avgs = []
    for s in symbols:
        series = bars.get(s)
        if series and len(series) > 1:
            trailing_avgs.append(sum(b.volume for b in series[:-1]) / (len(series) - 1))
    trailing_avg_total = sum(trailing_avgs) if trailing_avgs else 0.0

    unusual_volume = bool(trailing_avg_total > 0 and today_total > _UNUSUAL_VOLUME_MULTIPLE * trailing_avg_total)
    # Clip — options_flow.put_call_ratio is NUMERIC(6,3) (max ~999.999); near-zero
    # call_volume on an otherwise-real day would otherwise overflow the column.
    put_call_ratio = min(put_volume / call_volume, 999.0) if call_volume > 0 else None

    return {
        "call_volume": call_volume,
        "put_volume": put_volume,
        "put_call_ratio": put_call_ratio,
        "unusual_volume": unusual_volume,
    }


def _atm_iv(ticker: str, spot: float, expiry: str) -> float | None:
    """Average IV of the calls/puts closest to spot for the given expiry, via yfinance."""
    from ...execution.options import get_options_chain

    days_out = (date.fromisoformat(expiry) - date.today()).days
    chains = get_options_chain(ticker, expiry_min_days=max(0, days_out - 2), expiry_max_days=days_out + 2)
    if not chains:
        return None

    ivs: list[float] = []
    for entry in chains:
        for rows in (entry["calls"], entry["puts"]):
            near = sorted(rows, key=lambda r: abs(float(r.get("strike", 0)) - spot))[:2]
            for r in near:
                iv = r.get("impliedVolatility")
                if iv is not None and iv > 0:
                    ivs.append(float(iv))
    if not ivs:
        return None
    return sum(ivs) / len(ivs)


def _iv_rank(cur, ticker: str, atm_iv: float) -> tuple[float | None, float | None]:
    """Percentile of atm_iv against this ticker's own accumulated history. None if too little history."""
    cur.execute(
        "SELECT metadata->>'atm_iv' FROM options_flow WHERE ticker=%s AND metadata->>'atm_iv' IS NOT NULL",
        (ticker,),
    )
    history = [float(r[0]) for r in cur.fetchall() if r[0] is not None]
    if len(history) < 5:
        return None, None

    all_values = sorted(history + [atm_iv])
    rank_pct = (all_values.index(atm_iv) + 1) / len(all_values) * 100.0
    return round(rank_pct, 3), round(rank_pct, 3)


def collect(tickers: list[str] | None = None) -> dict:
    tickers = tickers or universe()["seed_tickers"]
    today = date.today()
    client = _option_client()

    inserted, skipped, failed = 0, 0, 0
    with conn() as c, c.cursor() as cur:
        for ticker in tickers:
            try:
                spot = _spot_price(ticker)
                if not spot:
                    log.info("options_flow_collector: no spot price", ticker=ticker)
                    skipped += 1
                    continue

                nearest = _nearest_expiry_chain(client, ticker, spot)
                if nearest is None:
                    log.info("options_flow_collector: no contracts in window", ticker=ticker)
                    skipped += 1
                    continue
                expiry, call_symbols, put_symbols = nearest

                vol_metrics = _volume_metrics(client, call_symbols, put_symbols)
                if vol_metrics is None:
                    skipped += 1
                    continue

                atm_iv = _atm_iv(ticker, spot, expiry)
                iv_rank, iv_percentile = (None, None) if atm_iv is None else _iv_rank(cur, ticker, atm_iv)

                signal = classify_signal(iv_rank, vol_metrics["put_call_ratio"], vol_metrics["unusual_volume"])

                cur.execute(
                    """
                    INSERT INTO options_flow
                        (ticker, date, iv_rank, iv_percentile, put_call_ratio, unusual_volume, signal, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker, date) DO UPDATE
                      SET iv_rank        = EXCLUDED.iv_rank,
                          iv_percentile  = EXCLUDED.iv_percentile,
                          put_call_ratio = EXCLUDED.put_call_ratio,
                          unusual_volume = EXCLUDED.unusual_volume,
                          signal         = EXCLUDED.signal,
                          metadata       = EXCLUDED.metadata
                    """,
                    (
                        ticker, today, iv_rank, iv_percentile,
                        vol_metrics["put_call_ratio"], vol_metrics["unusual_volume"], signal,
                        Json({
                            "atm_iv": atm_iv,
                            "expiry": expiry,
                            "call_volume": vol_metrics["call_volume"],
                            "put_volume": vol_metrics["put_volume"],
                        }),
                    ),
                )
                inserted += 1
            except Exception as e:
                log.warning("options_flow_collector_failed", ticker=ticker, err=str(e))
                failed += 1
                c.rollback()  # a failed statement poisons the rest of this transaction otherwise
        c.commit()

    log_activity("options_flow_collector", "collect", "ok",
                 tickers=len(tickers), inserted=inserted, skipped=skipped, failed=failed)
    return {"tickers": len(tickers), "inserted": inserted, "skipped": skipped, "failed": failed}
