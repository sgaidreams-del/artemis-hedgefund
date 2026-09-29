import pytest
import json
from unittest.mock import patch, MagicMock
from src.strategy.debate.checklist_scorer import score_bull_checklist, score_bear_checklist

def _mock_llm_response(content):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    return resp

# Checklist tests
def test_bull_checklist_high_momentum():
    signals = {"technical_composite": 0.8, "sentiment_1d": 0.6, "llm_sentiment": 0.5}
    fundamentals = {"pe_ratio": 18, "dividend_yield": 0.025}
    result = score_bull_checklist("AAPL", signals, fundamentals)
    assert result.momentum_score > 2.0
    assert 0 <= result.total <= 10

def test_bear_checklist_high_pe():
    signals = {"technical_composite": 0.2, "llm_sentiment": 0.1}
    fundamentals = {"pe_ratio": 50}
    result = score_bear_checklist("TSLA", signals, fundamentals)
    assert result.overvaluation_score == 3.0
    assert 0 <= result.total <= 10

def test_checklist_scores_always_in_range():
    signals = {"technical_composite": -0.9, "sentiment_1d": 0.9, "llm_sentiment": -0.5,
               "insider_signal": 0.8, "short_interest_signal": -0.5, "options_flow_signal": -0.6}
    fundamentals = {"pe_ratio": 45, "dividend_yield": 0.0}
    bull = score_bull_checklist("X", signals, fundamentals)
    bear = score_bear_checklist("X", signals, fundamentals)
    assert 0 <= bull.total <= 10
    assert 0 <= bear.total <= 10

# Debate gate tests
def test_run_debate_skips_when_paused():
    from src.strategy.debate.judge import run_debate
    with patch("src.strategy.debate.judge.is_paused", return_value=True):
        result = run_debate("AAPL", {}, {}, [])
    assert result is None

def test_run_debate_skips_strongly_onesided():
    """When composite is |>0.8|, debate is skipped to save LLM cost."""
    from src.strategy.debate.judge import run_debate
    strongly_bullish_signals = {
        "technical_composite": 0.9,
        "llm_sentiment": 0.9,
        "sentiment_1d": 0.9,
    }
    with patch("src.strategy.debate.judge.is_paused", return_value=False):
        result = run_debate("NVDA", strongly_bullish_signals, {}, [])
    assert result is None

def test_adjudicate_parses_verdict():
    from src.strategy.debate.judge import adjudicate
    from src.strategy.debate.checklist_scorer import BullChecklist, BearChecklist

    bull_cl = BullChecklist(2.0, 2.0, 1.0, 0.5, total=5.5)
    bear_cl = BearChecklist(1.0, 2.0, 1.0, 0.5, total=4.5)

    verdict_json = json.dumps({
        "verdict": "buy", "confidence": 0.75,
        "reasoning": "Bull case stronger.", "winning_side": "bull"
    })
    with patch("src.strategy.debate.judge._get_client") as mock_get:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_llm_response(verdict_json)
        mock_get.return_value = mock_client
        result = adjudicate("AAPL", "Strong momentum", "High PE", bull_cl, bear_cl)

    assert result["verdict"] == "buy"
    assert result["confidence"] == pytest.approx(0.75)

def test_adjudicate_returns_hold_on_parse_error():
    from src.strategy.debate.judge import adjudicate
    from src.strategy.debate.checklist_scorer import BullChecklist, BearChecklist
    bull_cl = BullChecklist(1.0, 1.0, 0.5, 0.5, total=3.0)
    bear_cl = BearChecklist(1.0, 1.0, 0.5, 0.5, total=3.0)
    with patch("src.strategy.debate.judge._get_client") as mock_get:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_llm_response("not json {{")
        mock_get.return_value = mock_client
        result = adjudicate("MSFT", "good", "bad", bull_cl, bear_cl)
    assert result["verdict"] == "hold"
    assert result["confidence"] == 0.0
