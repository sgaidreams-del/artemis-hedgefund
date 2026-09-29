"""
Deterministic checklist scorer for Bull/Bear debate gate.
All scoring is pure Python — no LLM calls here.
These scores ground the LLM agents so they reason over numbers, not vibes.
"""
from dataclasses import dataclass

@dataclass
class BullChecklist:
    momentum_score: float   # 0-3: recent price momentum
    quality_score: float    # 0-3: profitability/balance sheet quality
    value_score: float      # 0-2: valuation attractiveness
    contrarian_score: float # 0-2: oversold conditions, negative sentiment
    total: float            # sum, 0-10

@dataclass
class BearChecklist:
    momentum_score: float   # 0-3: negative momentum
    overvaluation_score: float  # 0-3: stretched valuation
    risk_score: float       # 0-2: leverage, volatility
    sentiment_score: float  # 0-2: overbought, euphoria
    total: float            # sum, 0-10


def score_bull_checklist(ticker: str, signals: dict, fundamentals: dict) -> BullChecklist:
    """
    Compute bull checklist from available data.

    signals: dict of {signal_name: value} — all in [-1, +1]
    fundamentals: dict with keys like pe_ratio, market_cap, dividend_yield
    """
    # Momentum score (0-3): based on technical_composite and recent return signals
    tech = signals.get("technical_composite", 0.0)
    sentiment_1d = signals.get("sentiment_1d", 0.0)
    momentum = (tech + sentiment_1d) / 2.0
    momentum_score = max(0.0, min(3.0, (momentum + 1.0) * 1.5))  # maps [-1,+1] → [0, 3]

    # Quality score (0-3): PE ratio and dividend yield proxies
    pe_raw = fundamentals.get("pe_ratio")
    pe = pe_raw if pe_raw is not None else 25.0
    div_yield = fundamentals.get("dividend_yield") or 0.0
    quality_score = 0.0
    if 5 < pe < 20:   quality_score += 1.5  # reasonable PE
    elif 20 <= pe < 30: quality_score += 0.75
    if div_yield > 0.02: quality_score += 1.0  # pays dividend
    quality_score = min(3.0, quality_score)

    # Value score (0-2): low PE or high insider buying
    insider = signals.get("insider_signal", 0.0)
    value_score = 0.0
    if pe < 15:  value_score += 1.0
    if insider > 0.5: value_score += 1.0
    value_score = min(2.0, value_score)

    # Contrarian score (0-2): high short interest or bearish sentiment = contrarian opportunity
    short_sig = signals.get("short_interest_signal", 0.0)
    llm_sig = signals.get("llm_sentiment", 0.0)
    contrarian_score = 0.0
    if short_sig < -0.3:  contrarian_score += 1.0  # heavily shorted = squeeze potential
    if llm_sig < -0.3:    contrarian_score += 1.0  # negative sentiment = buy the dip
    contrarian_score = min(2.0, contrarian_score)

    total = momentum_score + quality_score + value_score + contrarian_score
    return BullChecklist(
        momentum_score=round(momentum_score, 2),
        quality_score=round(quality_score, 2),
        value_score=round(value_score, 2),
        contrarian_score=round(contrarian_score, 2),
        total=round(total, 2),
    )


def score_bear_checklist(ticker: str, signals: dict, fundamentals: dict) -> BearChecklist:
    """
    Compute bear checklist from available data.
    """
    # Negative momentum score (0-3)
    tech = signals.get("technical_composite", 0.0)
    sentiment_1d = signals.get("sentiment_1d", 0.0)
    neg_momentum = -(tech + sentiment_1d) / 2.0  # invert: negative tech/sentiment = bear signal
    momentum_score = max(0.0, min(3.0, (neg_momentum + 1.0) * 1.5))

    # Overvaluation score (0-3): high PE
    pe_raw = fundamentals.get("pe_ratio")
    pe = pe_raw if pe_raw is not None else 25.0
    overval_score = 0.0
    if pe > 40:   overval_score = 3.0
    elif pe > 30: overval_score = 2.0
    elif pe > 20: overval_score = 1.0

    # Risk score (0-2): high short interest, bearish options flow
    short_sig = signals.get("short_interest_signal", 0.0)
    opts_sig = signals.get("options_flow_signal", 0.0)
    risk_score = 0.0
    if short_sig < -0.3: risk_score += 1.0
    if opts_sig < -0.3:  risk_score += 1.0
    risk_score = min(2.0, risk_score)

    # Overbought/euphoria score (0-2)
    llm_sig = signals.get("llm_sentiment", 0.0)
    sent_score = 0.0
    if llm_sig > 0.6:  sent_score += 1.0  # euphoria
    if tech > 0.7:     sent_score += 1.0  # overbought technically
    sent_score = min(2.0, sent_score)

    total = momentum_score + overval_score + risk_score + sent_score
    return BearChecklist(
        momentum_score=round(momentum_score, 2),
        overvaluation_score=round(overval_score, 2),
        risk_score=round(risk_score, 2),
        sentiment_score=round(sent_score, 2),
        total=round(total, 2),
    )
