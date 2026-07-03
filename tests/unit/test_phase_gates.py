"""Tests for paper slippage and phase 2 gates."""

import pandas as pd
import pytest

from scripts.analyze_paper_slippage import evaluate_phase1
from src.reporting.momentum_validation import (
    evaluate_phase2_gates,
    phase2_verdict,
    ValidationGate,
)


def test_paper_slippage_pass():
    rows = []
    for i in range(20):
        rows.append(
            {
                "session_date": f"2026-01-{i+1:02d}",
                "side": "long",
                "intended_entry": 100.0,
                "fill_entry": 100.2,
                "intended_exit": 110.0,
                "fill_exit": 109.8,
            }
        )
    df = pd.DataFrame(rows)
    result = evaluate_phase1(df)
    assert result["sessions"] == 20
    assert result["avg_round_trip_slip"] == pytest.approx(0.4)
    assert result["passed"]


def test_paper_slippage_fail_high_slip():
    df = pd.DataFrame(
        {
            "session_date": ["2026-01-01"] * 20,
            "side": ["long"] * 20,
            "intended_entry": [100.0] * 20,
            "fill_entry": [102.0] * 20,
            "intended_exit": [110.0] * 20,
            "fill_exit": [108.0] * 20,
        }
    )
    result = evaluate_phase1(df)
    assert result["avg_round_trip_slip"] == 4.0
    assert not result["passed"]


def test_phase2_gates_pass():
    wf = pd.DataFrame(
        {
            "slice": ["2024-2026"],
            "trades": [100],
            "net_pnl": [500.0],
            "avg_bps": [2.0],
        }
    )
    slip = pd.DataFrame(
        {
            "slippage_pts": [1.0],
            "trades": [100],
            "net_pnl": [100.0],
            "gross_pnl": [1000.0],
            "avg_bps": [1.0],
            "profit_factor": [1.1],
        }
    )
    gates = evaluate_phase2_gates(wf, slip)
    assert all(g.passed for g in gates)
    assert phase2_verdict(gates).startswith("PASS")


def test_phase2_gates_fail_oos():
    wf = pd.DataFrame(
        {
            "slice": ["2024-2026"],
            "trades": [100],
            "net_pnl": [-500.0],
            "avg_bps": [-2.0],
        }
    )
    slip = pd.DataFrame({"slippage_pts": [1.0], "net_pnl": [100.0]})
    gates = evaluate_phase2_gates(wf, slip)
    assert not gates[0].passed
    assert phase2_verdict(gates).startswith("FAIL")
