"""Tests for the AutoResearch Engine (Unit 13)."""
from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest


# ── Test 1: prioritize ranks by expected_alpha × novelty_score ────────────────

def test_prioritize_ranks_by_score():
    """prioritize() should sort hypotheses by expected_alpha * novelty_score descending."""
    from src.autoresearch.hypothesis.prioritizer import prioritize

    hypotheses = [
        {"id": "low-alpha", "title": "simple momentum signal", "expected_alpha": 0.02},
        {"id": "high-alpha-novel", "title": "exotic vol surface arb", "expected_alpha": 0.15},
        {"id": "mid-alpha", "title": "earnings drift capture", "expected_alpha": 0.08},
    ]

    # Journal has one entry matching "momentum" → reduces novelty for low-alpha
    journal_entries = [
        {"description": "simple momentum signal past experiment", "result": "FAIL"},
    ]

    ranked = prioritize(hypotheses, journal_entries)

    assert len(ranked) == 3
    # Scores must be non-increasing
    scores = [h["score"] for h in ranked]
    assert scores == sorted(scores, reverse=True), f"Scores not sorted: {scores}"

    # "exotic vol surface arb" has no overlap with journal → high novelty AND high alpha
    assert ranked[0]["id"] == "high-alpha-novel"


def test_prioritize_zero_alpha_scores_zero():
    """A hypothesis with expected_alpha=0 should always score 0 regardless of novelty."""
    from src.autoresearch.hypothesis.prioritizer import prioritize

    hypotheses = [
        {"id": "zero-alpha", "title": "unique title never seen", "expected_alpha": 0.0},
        {"id": "small-alpha", "title": "another unique signal", "expected_alpha": 0.001},
    ]
    ranked = prioritize(hypotheses, [])

    zero_h = next(h for h in ranked if h["id"] == "zero-alpha")
    assert zero_h["score"] == 0.0


def test_prioritize_identical_titles_lower_novelty():
    """A hypothesis whose title exactly matches a past experiment should have low novelty."""
    from src.autoresearch.hypothesis.prioritizer import prioritize

    hypotheses = [
        {"id": "seen", "title": "momentum reversal v1", "expected_alpha": 0.10},
        {"id": "unseen", "title": "earnings gap fade", "expected_alpha": 0.10},
    ]
    journal_entries = [
        {"description": "momentum reversal v1"},  # exact match for "seen"
    ]

    ranked = prioritize(hypotheses, journal_entries)

    seen_h = next(h for h in ranked if h["id"] == "seen")
    unseen_h = next(h for h in ranked if h["id"] == "unseen")

    assert seen_h["novelty_score"] < unseen_h["novelty_score"]
    assert unseen_h["score"] > seen_h["score"]


# ── Test 2: generate_hypotheses with mocked LLM ───────────────────────────────

def test_generate_hypotheses_returns_list_of_dicts():
    """generate_hypotheses() with mocked OpenAI should return list of dicts with required keys."""
    mock_hypothesis = {
        "id": "test-momentum-001",
        "title": "Cross-sectional Momentum Decay",
        "signal_type": "momentum",
        "rationale": "Recent winners tend to reverse over a 5-day horizon.",
        "expected_alpha": 0.07,
        "priority": 2,
    }

    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps([mock_hypothesis])

    with (
        patch("src.autoresearch.hypothesis.generator.get_recent", return_value=[]),
        patch("src.autoresearch.hypothesis.generator.OpenAI") as mock_openai_cls,
        patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client

        from src.autoresearch.hypothesis.generator import generate_hypotheses

        result = generate_hypotheses(n=1)

    assert isinstance(result, list)
    assert len(result) == 1
    required_keys = {"id", "title", "signal_type", "rationale", "expected_alpha", "priority"}
    for h in result:
        assert required_keys.issubset(set(h.keys())), f"Missing keys: {required_keys - set(h.keys())}"


def test_generate_hypotheses_strips_markdown_fences():
    """generate_hypotheses() should handle LLM output wrapped in ```json fences."""
    mock_hypothesis = {
        "id": "wrapped-001",
        "title": "Mean Reversion at Open",
        "signal_type": "mean_reversion",
        "rationale": "Overnight gaps tend to fill within the first hour.",
        "expected_alpha": 0.05,
        "priority": 3,
    }

    fenced_content = "```json\n" + json.dumps([mock_hypothesis]) + "\n```"

    mock_response = MagicMock()
    mock_response.choices[0].message.content = fenced_content

    with (
        patch("src.autoresearch.hypothesis.generator.get_recent", return_value=[]),
        patch("src.autoresearch.hypothesis.generator.OpenAI") as mock_openai_cls,
        patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client

        from src.autoresearch.hypothesis.generator import generate_hypotheses

        result = generate_hypotheses(n=1)

    assert len(result) == 1
    assert result[0]["id"] == "wrapped-001"


# ── Test 3: analyze_result returns verdict in {DEPLOY, ITERATE, ABANDON} ─────

def test_analyze_result_returns_valid_verdict():
    """analyze_result() with mocked LLM returns verdict in {DEPLOY, ITERATE, ABANDON}."""
    mock_analysis = {
        "verdict": "DEPLOY",
        "commentary": "Strong Sharpe ratio with manageable drawdown. Signal is robust.",
        "next_steps": ["Paper trade for 30 days", "Increase position sizing gradually"],
    }

    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(mock_analysis)

    hypothesis = {
        "id": "test-h-001",
        "title": "Test Hypothesis",
        "signal_type": "technical",
        "expected_alpha": 0.10,
    }
    scorecard = {"sharpe": 1.4, "total_return": 0.23, "max_drawdown": -0.08}

    with (
        patch("src.autoresearch.experiment.analyzer.OpenAI") as mock_openai_cls,
        patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client

        from src.autoresearch.experiment.analyzer import analyze_result

        result = analyze_result(hypothesis, scorecard)

    assert "verdict" in result
    assert result["verdict"] in {"DEPLOY", "ITERATE", "ABANDON"}
    assert "commentary" in result
    assert "next_steps" in result


@pytest.mark.parametrize("verdict", ["DEPLOY", "ITERATE", "ABANDON"])
def test_analyze_result_all_verdicts(verdict: str):
    """analyze_result() should pass through all valid verdicts unchanged."""
    mock_analysis = {
        "verdict": verdict,
        "commentary": "Some commentary here.",
        "next_steps": ["Step 1"],
    }

    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(mock_analysis)

    with (
        patch("src.autoresearch.experiment.analyzer.OpenAI") as mock_openai_cls,
        patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client

        from src.autoresearch.experiment.analyzer import analyze_result

        result = analyze_result({}, {})

    assert result["verdict"] == verdict


def test_analyze_result_sanitizes_invalid_verdict():
    """analyze_result() should coerce an unexpected verdict to 'ITERATE'."""
    mock_analysis = {
        "verdict": "UNKNOWN_VERDICT",
        "commentary": "Some commentary.",
        "next_steps": [],
    }

    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(mock_analysis)

    with (
        patch("src.autoresearch.experiment.analyzer.OpenAI") as mock_openai_cls,
        patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client

        from src.autoresearch.experiment.analyzer import analyze_result

        result = analyze_result({}, {})

    assert result["verdict"] == "ITERATE"


# ── Test 4: check_guardrails returns False when experiment count >= 20 ────────

def test_check_guardrails_returns_false_at_limit():
    """check_guardrails() should return False when weekly experiment count >= 20."""
    with (
        patch(
            "src.autoresearch.guardrails._count_experiments_this_week",
            return_value=20,
        ),
        patch(
            "src.autoresearch.guardrails._has_concurrent_live_changes",
            return_value=False,
        ),
    ):
        from src.autoresearch.guardrails import check_guardrails

        result = check_guardrails()

    assert result is False


def test_check_guardrails_returns_false_over_limit():
    """check_guardrails() should return False when weekly experiment count > 20."""
    with (
        patch(
            "src.autoresearch.guardrails._count_experiments_this_week",
            return_value=25,
        ),
        patch(
            "src.autoresearch.guardrails._has_concurrent_live_changes",
            return_value=False,
        ),
    ):
        from src.autoresearch.guardrails import check_guardrails

        result = check_guardrails()

    assert result is False


def test_check_guardrails_returns_true_under_limit():
    """check_guardrails() should return True when below limit and no concurrent live."""
    with (
        patch(
            "src.autoresearch.guardrails._count_experiments_this_week",
            return_value=5,
        ),
        patch(
            "src.autoresearch.guardrails._has_concurrent_live_changes",
            return_value=False,
        ),
    ):
        from src.autoresearch.guardrails import check_guardrails

        result = check_guardrails()

    assert result is True


def test_check_guardrails_returns_false_concurrent_live():
    """check_guardrails() should return False when concurrent live changes exist."""
    with (
        patch(
            "src.autoresearch.guardrails._count_experiments_this_week",
            return_value=3,
        ),
        patch(
            "src.autoresearch.guardrails._has_concurrent_live_changes",
            return_value=True,
        ),
    ):
        from src.autoresearch.guardrails import check_guardrails

        result = check_guardrails()

    assert result is False


# ── Test 5: create_pr_for_experiment calls subprocess with correct args ───────

def test_create_pr_calls_subprocess_with_correct_args():
    """create_pr_for_experiment() should call subprocess.run with gh pr create args."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "https://github.com/owner/repo/pull/42\n"

    experiment_id = "abc12345-1234-5678-abcd-123456789012"
    scorecard = {"sharpe": 1.2, "total_return": 0.18, "max_drawdown": -0.12}

    with patch("src.autoresearch.git_gate.subprocess.run", return_value=mock_result) as mock_run:
        from src.autoresearch.git_gate import create_pr_for_experiment

        url = create_pr_for_experiment(experiment_id, scorecard)

    mock_run.assert_called_once()
    call_args = mock_run.call_args

    # Verify gh pr create is in the command
    cmd = call_args[0][0]
    assert "gh" in cmd
    assert "pr" in cmd
    assert "create" in cmd
    assert "--title" in cmd
    assert "--body" in cmd

    # Title should reference shortened experiment_id
    title_idx = cmd.index("--title")
    title_val = cmd[title_idx + 1]
    assert "abc12345" in title_val  # first 8 chars of experiment_id

    # Return value should be the PR URL
    assert url == "https://github.com/owner/repo/pull/42"


def test_create_pr_returns_none_message_on_failure():
    """create_pr_for_experiment() should return 'PR: none — <reason>' on gh failure."""
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "fatal: not a git repository"

    with patch("src.autoresearch.git_gate.subprocess.run", return_value=mock_result):
        from src.autoresearch.git_gate import create_pr_for_experiment

        url = create_pr_for_experiment("exp-id-000", {})

    assert url.startswith("PR: none")
    assert "fatal: not a git repository" in url


def test_create_pr_handles_file_not_found():
    """create_pr_for_experiment() should return 'PR: none — gh CLI not found' if gh missing."""
    with patch(
        "src.autoresearch.git_gate.subprocess.run",
        side_effect=FileNotFoundError("No such file: gh"),
    ):
        from src.autoresearch.git_gate import create_pr_for_experiment

        url = create_pr_for_experiment("exp-id-001", {})

    assert "PR: none" in url
    assert "not found" in url.lower()


# ── Bonus tests ───────────────────────────────────────────────────────────────

def test_create_sandbox_signals_returns_dataframe():
    """create_sandbox_signals() should return a DataFrame with expected columns."""
    from src.autoresearch.experiment.sandbox import create_sandbox_signals

    hypothesis = {
        "id": "test-sandbox-001",
        "title": "Test Sandbox Signal",
        "signal_type": "momentum",
        "expected_alpha": 0.05,
    }
    df = create_sandbox_signals(hypothesis, n_days=50)

    assert not df.empty
    for col in ("date", "signal", "returns", "position"):
        assert col in df.columns, f"Missing column: {col}"
    assert len(df) == 50


def test_create_sandbox_signals_deterministic():
    """create_sandbox_signals() should be deterministic for the same hypothesis id."""
    from src.autoresearch.experiment.sandbox import create_sandbox_signals

    hypothesis = {"id": "deterministic-test", "signal_type": "technical", "expected_alpha": 0.05}

    df1 = create_sandbox_signals(hypothesis, n_days=30)
    df2 = create_sandbox_signals(hypothesis, n_days=30)

    assert df1["returns"].tolist() == df2["returns"].tolist()


def test_promotion_stage_enum_values():
    """PromotionStage enum should have shadow, paper, live values."""
    from src.autoresearch.promotion.pipeline import PromotionStage

    assert PromotionStage.SHADOW.value == "shadow"
    assert PromotionStage.PAPER.value == "paper"
    assert PromotionStage.LIVE.value == "live"


def test_guardrails_constant():
    """MAX_EXPERIMENTS_PER_WEEK should be 20."""
    from src.autoresearch.guardrails import MAX_EXPERIMENTS_PER_WEEK

    assert MAX_EXPERIMENTS_PER_WEEK == 20
