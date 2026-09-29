"""Prompt templates for the DeepSeek LLM ticker analyzer. SPEC §LLM."""
from __future__ import annotations

TICKER_ANALYSIS_SYSTEM: str = (
    "You are a quantitative equity analyst. "
    "Analyze the provided ticker data and return a JSON object with exactly these keys:\n"
    "  bull_points: list of strings (reasons to be bullish, max 5)\n"
    "  bear_points: list of strings (reasons to be bearish, max 5)\n"
    "  sentiment_score: float in [-1.0, 1.0] where -1 is strongly bearish and 1 is strongly bullish\n"
    "  confidence: float in [0.0, 1.0] indicating your confidence in the analysis\n"
    "Return ONLY valid JSON — no markdown, no explanation, no extra text."
)

TICKER_ANALYSIS_USER: str = (
    "Analyze {ticker}:\n"
    "  P/E Ratio: {pe_ratio}\n"
    "  Market Cap: ${market_cap_b}B\n"
    "  Dividend Yield: {dividend_yield}\n"
    "  Sector: {sector}\n"
    "  Technical Score: {technical_score}\n"
    "  Recent Headlines:\n{headlines}\n\n"
    "Return a JSON object with bull_points, bear_points, sentiment_score, and confidence."
)
