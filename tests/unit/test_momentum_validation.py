"""Tests for momentum validation module."""

import pandas as pd

from src.reporting.momentum_validation import (
    bootstrap_mean_bps,
    payoff_stats,
    annual_breakdown,
    walk_forward_slices,
    evaluate_momentum_gates,
    momentum_verdict,
    ValidationGate,
)


def _sample_trades() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "session_date": pd.to_datetime(
                ["2018-01-02", "2018-01-03", "2019-06-01", "2024-03-01", "2025-01-02"]
            ),
            "entry_price": [15000.0] * 5,
            "pnl_points": [50.0, -20.0, 30.0, 40.0, -10.0],
            "exit_reason": ["eod", "stop", "eod", "eod", "stop"],
            "year": [2018, 2018, 2019, 2024, 2025],
            "return_bps": [33.3, -13.3, 20.0, 26.7, -6.7],
            "is_winner": [True, False, True, True, False],
        }
    )


def test_bootstrap_positive_mean():
    boot = bootstrap_mean_bps(_sample_trades(), n_samples=500, seed=1)
    assert boot["mean_bps"] > 0
    assert boot["ci_low"] < boot["ci_high"]


def test_annual_breakdown():
    annual = annual_breakdown(_sample_trades())
    assert len(annual) == 4
    assert set(annual["year"]) == {2018, 2019, 2024, 2025}


def test_payoff_ratio():
    stats = payoff_stats(_sample_trades())
    assert stats["win_rate"] == 0.6
    assert stats["payoff_ratio"] > 1.0


def test_momentum_verdict_validate_on_core_pass():
    gates = [
        ValidationGate(f"V{i}", "t", True, "1", ">0") for i in range(1, 10)
    ]
    gates[6] = ValidationGate("V7", "OOS", False, "0", ">0")
    gates[7] = ValidationGate("V8", "OOS bps", False, "0", ">0")
    assert momentum_verdict(gates).startswith("VALIDATE (conditional)")
