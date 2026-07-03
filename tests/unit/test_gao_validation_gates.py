"""Tests for Gao validation gates."""

import pandas as pd

from src.reporting.momentum_validation import evaluate_gao_gates, gao_verdict, ValidationGate


def _summary(net: float, gross: float, trades: int = 100):
    base = {
        "trade_count": trades,
        "total_pnl": net,
        "profit_factor": 1.1,
    }
    return {"net": base, "gross": {**base, "total_pnl": gross}}


def test_gao_gates_deploy_pass():
    trades = pd.DataFrame(
        {
            "pnl_points": [5.0] * 100,
            "entry_price": [20000.0] * 100,
            "return_bps": [2.5] * 100,
            "year": [2025] * 100,
        }
    )
    annual = pd.DataFrame({"year": [2025], "net_pnl": [500.0]})
    wf = pd.DataFrame({"slice": ["2024-2026"], "trades": [100], "net_pnl": [500.0], "avg_bps": [2.0]})
    slip = pd.DataFrame(
        {
            "slippage_pts": [0.5, 1.0],
            "net_pnl": [500.0, 300.0],
            "gross_pnl": [700.0, 700.0],
            "avg_bps": [2.0, 1.5],
            "profit_factor": [1.2, 1.1],
            "trades": [100, 100],
        }
    )
    boot = {"mean_bps": 2.0, "ci_low": 1.0, "ci_high": 3.0, "p_positive": 0.9}
    gates = evaluate_gao_gates(_summary(500, 700), _summary(500, 700), trades, boot, annual, slip, wf)
    assert gao_verdict(gates).startswith(("KEEP", "VALIDATE"))


def test_gao_v10_fails_thin_edge():
    trades = pd.DataFrame(
        {
            "pnl_points": [1.0] * 50,
            "entry_price": [20000.0] * 50,
            "return_bps": [0.5] * 50,
            "year": [2024] * 50,
        }
    )
    annual = pd.DataFrame({"year": [2024], "net_pnl": [50.0]})
    wf = pd.DataFrame({"slice": ["2024-2026"], "trades": [50], "net_pnl": [50.0], "avg_bps": [0.5]})
    slip = pd.DataFrame(
        {
            "slippage_pts": [0.5, 1.0],
            "net_pnl": [50.0, -10.0],
            "gross_pnl": [100.0, 100.0],
            "avg_bps": [0.5, -0.2],
            "profit_factor": [1.05, 0.95],
            "trades": [50, 50],
        }
    )
    boot = {"mean_bps": 0.5, "ci_low": -0.5, "ci_high": 1.5, "p_positive": 0.6}
    gates = evaluate_gao_gates(_summary(50, 100), _summary(50, 100), trades, boot, annual, slip, wf)
    v10 = next(g for g in gates if g.gate_id == "V10")
    assert not v10.passed
