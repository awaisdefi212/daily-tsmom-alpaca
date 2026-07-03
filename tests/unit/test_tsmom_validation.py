"""Unit tests for TSMOM validation gates."""

from __future__ import annotations

import pandas as pd

from src.reporting.momentum_validation import evaluate_tsmom_gates, tsmom_verdict


def _summary(net: float, gross: float) -> dict:
    return {
        "net": {"total_pnl": net},
        "gross": {"total_pnl": gross},
    }


def test_tsmom_verdict_keep():
    trades = pd.DataFrame(
        {
            "session_date": ["2024-01-01", "2024-02-01"],
            "pnl_points": [100.0, 80.0],
            "entry_price": [15000.0, 15100.0],
            "return_bps": [66.0, 52.0],
            "side": ["long", "short"],
        }
    )
    gross_trades = trades.copy()
    annual = pd.DataFrame({"year": [2024], "net_pnl": [180.0]})
    slip = pd.DataFrame(
        {
            "slippage_pts": [2.0],
            "net_pnl": [150.0],
            "gross_pnl": [200.0],
        }
    )
    wf = pd.DataFrame({"slice": ["2024-2026"], "net_pnl": [180.0]})
    lb = pd.DataFrame({"lookback_days": [189, 252, 378], "gross_pnl": [10.0, 20.0, 30.0]})
    gates = evaluate_tsmom_gates(
        _summary(170.0, 200.0),
        _summary(200.0, 200.0),
        trades,
        gross_trades,
        annual,
        slip,
        wf,
        lb,
    )
    assert all(g.passed for g in gates)
    assert tsmom_verdict(gates).startswith("KEEP")


def test_tsmom_verdict_keep_long_only():
    trades = pd.DataFrame(
        {
            "session_date": ["2024-01-01", "2024-02-01"],
            "pnl_points": [100.0, 80.0],
            "entry_price": [15000.0, 15100.0],
            "return_bps": [66.0, 52.0],
            "side": ["long", "long"],
        }
    )
    gross_trades = trades.copy()
    annual = pd.DataFrame({"year": [2024], "net_pnl": [180.0]})
    slip = pd.DataFrame({"slippage_pts": [2.0], "net_pnl": [150.0], "gross_pnl": [200.0]})
    wf = pd.DataFrame({"slice": ["2024-2026"], "net_pnl": [180.0]})
    lb = pd.DataFrame({"lookback_days": [189, 252, 378], "gross_pnl": [10.0, 20.0, 30.0]})
    gates = evaluate_tsmom_gates(
        _summary(170.0, 200.0),
        _summary(200.0, 200.0),
        trades,
        gross_trades,
        annual,
        slip,
        wf,
        lb,
        tsmom_long_only=True,
    )
    assert all(g.passed for g in gates)
    assert tsmom_verdict(gates).startswith("KEEP")


def test_tsmom_verdict_cancel():
    gates = evaluate_tsmom_gates(
        _summary(-10.0, -5.0),
        _summary(-5.0, -5.0),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame({"slippage_pts": [2.0], "net_pnl": [-20.0]}),
        pd.DataFrame({"slice": ["2024-2026"], "net_pnl": [-10.0]}),
        pd.DataFrame({"lookback_days": [252], "gross_pnl": [-1.0]}),
    )
    assert tsmom_verdict(gates) == "CANCEL - daily TSMOM does not survive validation"
