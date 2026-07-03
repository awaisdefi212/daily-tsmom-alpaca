"""Advanced validation metrics for intraday momentum strategy."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.backtest.backtest_engine import BacktestResult, run_backtest, prepare_bars
from src.config import AppConfig
from src.reporting.reporting import summarize_backtest, trades_to_dataframe


@dataclass
class ValidationGate:
    gate_id: str
    name: str
    passed: bool
    actual: str
    threshold: str


def trades_to_enriched_df(result: BacktestResult) -> pd.DataFrame:
    df = trades_to_dataframe(result.trades)
    if df.empty:
        return df
    df["year"] = pd.to_datetime(df["session_date"]).dt.year
    df["return_bps"] = (df["pnl_points"] / df["entry_price"]) * 10_000.0
    df["is_winner"] = df["pnl_points"] > 0
    return df


def annual_breakdown(trades_df: pd.DataFrame) -> pd.DataFrame:
    if trades_df.empty:
        return pd.DataFrame(columns=["year", "trades", "net_pnl", "avg_bps", "win_rate"])
    rows = []
    for year, grp in trades_df.groupby("year"):
        wins = grp[grp["pnl_points"] > 0]
        rows.append(
            {
                "year": int(year),
                "trades": len(grp),
                "net_pnl": float(grp["pnl_points"].sum()),
                "avg_bps": float(grp["return_bps"].mean()),
                "win_rate": len(wins) / len(grp),
            }
        )
    return pd.DataFrame(rows).sort_values("year")


def walk_forward_slices(trades_df: pd.DataFrame) -> pd.DataFrame:
    slices = [
        ("2016-2019", 2016, 2019),
        ("2020-2023", 2020, 2023),
        ("2024-2026", 2024, 2026),
    ]
    rows = []
    for label, y0, y1 in slices:
        mask = (trades_df["year"] >= y0) & (trades_df["year"] <= y1)
        grp = trades_df.loc[mask]
        if grp.empty:
            rows.append({"slice": label, "trades": 0, "net_pnl": 0.0, "avg_bps": 0.0})
            continue
        rows.append(
            {
                "slice": label,
                "trades": len(grp),
                "net_pnl": float(grp["pnl_points"].sum()),
                "avg_bps": float(grp["return_bps"].mean()),
            }
        )
    return pd.DataFrame(rows)


def slippage_stress(
    df: pd.DataFrame,
    config: AppConfig,
    slip_values: list[float],
    *,
    prepared_bars: pd.DataFrame | None = None,
) -> pd.DataFrame:
    prepared = prepared_bars if prepared_bars is not None else prepare_bars(df, config)
    rows = []
    for slip in slip_values:
        cfg = config.model_copy(deep=True)
        cfg.costs.slippage_points = slip
        net = run_backtest(df, cfg, prepared_bars=prepared)
        gross_cfg = config.model_copy(deep=True)
        gross_cfg.costs.slippage_points = 0.0
        gross = run_backtest(df, gross_cfg, prepared_bars=prepared)
        summary = summarize_backtest(net, gross)
        tdf = trades_to_enriched_df(net)
        avg_bps = float(tdf["return_bps"].mean()) if not tdf.empty else 0.0
        rows.append(
            {
                "slippage_pts": slip,
                "trades": summary["net"]["trade_count"],
                "net_pnl": summary["net"]["total_pnl"],
                "gross_pnl": summary["gross"]["total_pnl"],
                "avg_bps": avg_bps,
                "profit_factor": summary["net"]["profit_factor"],
            }
        )
    return pd.DataFrame(rows)


def lookback_stress(
    df: pd.DataFrame,
    config: AppConfig,
    lookback_days: list[int],
) -> pd.DataFrame:
    rows = []
    for lb in lookback_days:
        cfg = config.model_copy(deep=True)
        cfg.strategy.noise_lookback_days = lb
        prepared = prepare_bars(df, cfg)
        net = run_backtest(df, cfg, prepared_bars=prepared)
        gross_cfg = config.model_copy(deep=True)
        gross_cfg.costs.slippage_points = 0.0
        gross_cfg.strategy.noise_lookback_days = lb
        gross = run_backtest(df, gross_cfg, prepared_bars=prepared)
        summary = summarize_backtest(net, gross)
        tdf = trades_to_enriched_df(net)
        rows.append(
            {
                "lookback_days": lb,
                "trades": summary["net"]["trade_count"],
                "net_pnl": summary["net"]["total_pnl"],
                "gross_pnl": summary["gross"]["total_pnl"],
                "avg_bps": float(tdf["return_bps"].mean()) if not tdf.empty else 0.0,
            }
        )
    return pd.DataFrame(rows)


def bootstrap_mean_bps(
    trades_df: pd.DataFrame,
    n_samples: int = 2000,
    seed: int = 42,
) -> dict[str, float]:
    if trades_df.empty:
        return {"mean_bps": 0.0, "ci_low": 0.0, "ci_high": 0.0, "p_positive": 0.0}
    rng = np.random.default_rng(seed)
    bps = trades_df["return_bps"].to_numpy()
    means = [float(rng.choice(bps, size=len(bps), replace=True).mean()) for _ in range(n_samples)]
    return {
        "mean_bps": float(bps.mean()),
        "ci_low": float(np.percentile(means, 2.5)),
        "ci_high": float(np.percentile(means, 97.5)),
        "p_positive": float(np.mean(np.array(means) > 0)),
    }


def payoff_stats(trades_df: pd.DataFrame) -> dict[str, float]:
    if trades_df.empty:
        return {"win_rate": 0.0, "payoff_ratio": 0.0, "avg_win_pts": 0.0, "avg_loss_pts": 0.0}
    wins = trades_df[trades_df["pnl_points"] > 0]
    losses = trades_df[trades_df["pnl_points"] <= 0]
    avg_win = float(wins["pnl_points"].mean()) if not wins.empty else 0.0
    avg_loss = float(abs(losses["pnl_points"].mean())) if not losses.empty else 0.0
    payoff = avg_win / avg_loss if avg_loss > 0 else float("inf")
    return {
        "win_rate": len(wins) / len(trades_df),
        "payoff_ratio": payoff,
        "avg_win_pts": avg_win,
        "avg_loss_pts": avg_loss,
    }


def exit_reason_breakdown(trades_df: pd.DataFrame) -> pd.DataFrame:
    if trades_df.empty:
        return pd.DataFrame()
    return (
        trades_df.groupby("exit_reason")
        .agg(
            count=("pnl_points", "count"),
            net_pnl=("pnl_points", "sum"),
            avg_bps=("return_bps", "mean"),
            win_rate=("is_winner", "mean"),
        )
        .reset_index()
    )


def evaluate_momentum_gates(
    net_summary: dict,
    gross_summary: dict,
    trades_df: pd.DataFrame,
    bootstrap: dict[str, float],
    annual: pd.DataFrame,
    slip_stress: pd.DataFrame,
    wf_slices: pd.DataFrame,
) -> list[ValidationGate]:
    net_pnl = net_summary["net"]["total_pnl"]
    gross_pnl = gross_summary["gross"]["total_pnl"]
    avg_bps = float(trades_df["return_bps"].mean()) if not trades_df.empty else 0.0

    slip_10 = slip_stress.loc[slip_stress["slippage_pts"] == 1.0]
    net_at_10 = float(slip_10["net_pnl"].iloc[0]) if not slip_10.empty else -1.0

    oos = wf_slices.loc[wf_slices["slice"] == "2024-2026"]
    oos_pnl = float(oos["net_pnl"].iloc[0]) if not oos.empty else -1.0
    oos_bps = float(oos["avg_bps"].iloc[0]) if not oos.empty else -1.0

    positive_years = int((annual["net_pnl"] > 0).sum()) if not annual.empty else 0
    total_years = len(annual)
    year_pct = positive_years / total_years if total_years else 0.0

    payoff = payoff_stats(trades_df)

    return [
        ValidationGate("V1", "Gross edge", gross_pnl > 0, f"{gross_pnl:.1f}", "> 0"),
        ValidationGate("V2", "Net at 0.5pt slip", net_pnl > 0, f"{net_pnl:.1f}", "> 0"),
        ValidationGate("V3", "Net at 1.0pt slip", net_at_10 > 0, f"{net_at_10:.1f}", "> 0"),
        ValidationGate("V4", "Avg bps/trade", avg_bps > 0, f"{avg_bps:.2f}", "> 0"),
        ValidationGate(
            "V5",
            "Bootstrap 95% CI low > 0",
            bootstrap["ci_low"] > 0,
            f"{bootstrap['ci_low']:.2f}",
            "> 0",
        ),
        ValidationGate(
            "V6",
            "Positive years",
            year_pct >= 0.6,
            f"{positive_years}/{total_years} ({year_pct:.0%})",
            ">= 60%",
        ),
        ValidationGate(
            "V7",
            "OOS net PnL (2024-26)",
            oos_pnl > 0,
            f"{oos_pnl:.1f}",
            "> 0",
        ),
        ValidationGate(
            "V8",
            "OOS avg bps (2024-26)",
            oos_bps > 0,
            f"{oos_bps:.2f}",
            "> 0",
        ),
        ValidationGate(
            "V9",
            "Payoff ratio",
            payoff["payoff_ratio"] >= 1.5,
            f"{payoff['payoff_ratio']:.2f}",
            ">= 1.5",
        ),
    ]


def momentum_verdict(gates: list[ValidationGate]) -> str:
    passed = {g.gate_id: g.passed for g in gates}
    core = [passed.get(f"V{i}", False) for i in range(1, 6)]
    oos = passed.get("V7", False) and passed.get("V8", False)

    if all(passed.values()):
        return "KEEP - all validation gates passed; proceed to paper trading"

    if all(core) and oos:
        return "VALIDATE - core edge + OOS positive; paper trade 20 sessions with slippage logging"

    if all(core):
        return "VALIDATE (conditional) - core edge holds; OOS weak - paper trade with caution"

    if passed.get("V1") and passed.get("V2"):
        return "MARGINAL - gross+net positive but bootstrap or stress gates failed"

    return "CANCEL - edge does not survive validation"


def format_validation_report(
    gates: list[ValidationGate],
    verdict: str,
    annual: pd.DataFrame,
    wf_slices: pd.DataFrame,
    slip_stress: pd.DataFrame,
    lookback_stress_df: pd.DataFrame,
    bootstrap: dict[str, float],
    payoff: dict[str, float],
    exit_breakdown: pd.DataFrame,
) -> str:
    lines = [
        "=== Intraday Momentum Validation Report ===",
        "",
        "--- Paper-style metrics ---",
        f"Avg bps/trade: {bootstrap['mean_bps']:.2f}",
        f"Bootstrap 95% CI: [{bootstrap['ci_low']:.2f}, {bootstrap['ci_high']:.2f}]",
        f"P(bootstrap mean > 0): {bootstrap['p_positive']:.1%}",
        f"Win rate: {payoff['win_rate']:.1%}",
        f"Payoff ratio: {payoff['payoff_ratio']:.2f}",
        f"Avg win: {payoff['avg_win_pts']:.1f} pts | Avg loss: {payoff['avg_loss_pts']:.1f} pts",
        "",
        "--- Annual breakdown ---",
    ]
    for _, row in annual.iterrows():
        lines.append(
            f"  {int(row['year'])}: {int(row['trades'])} trades, "
            f"net {row['net_pnl']:+.1f} pts, avg {row['avg_bps']:+.2f} bps, "
            f"WR {row['win_rate']:.0%}"
        )

    lines.extend(["", "--- Walk-forward slices ---"])
    for _, row in wf_slices.iterrows():
        lines.append(
            f"  {row['slice']}: {int(row['trades'])} trades, "
            f"net {row['net_pnl']:+.1f} pts, avg {row['avg_bps']:+.2f} bps"
        )

    lines.extend(["", "--- Slippage stress ---"])
    for _, row in slip_stress.iterrows():
        lines.append(
            f"  slip {row['slippage_pts']:.1f}pt: net {row['net_pnl']:+.1f}, "
            f"gross {row['gross_pnl']:+.1f}, avg {row['avg_bps']:+.2f} bps, PF {row['profit_factor']:.2f}"
        )

    lines.extend(["", "--- Lookback stress (paper uses 14d; Quantitativo 90d) ---"])
    for _, row in lookback_stress_df.iterrows():
        lines.append(
            f"  {int(row['lookback_days'])}d: net {row['net_pnl']:+.1f}, "
            f"gross {row['gross_pnl']:+.1f}, avg {row['avg_bps']:+.2f} bps"
        )

    if not exit_breakdown.empty:
        lines.extend(["", "--- Exit reason breakdown ---"])
        for _, row in exit_breakdown.iterrows():
            lines.append(
                f"  {row['exit_reason']}: n={int(row['count'])}, net {row['net_pnl']:+.1f}, "
                f"avg {row['avg_bps']:+.2f} bps, WR {row['win_rate']:.0%}"
            )

    lines.extend(
        [
            "",
            "Gate          Status  Actual              Threshold",
            "------------------------------------------------------",
        ]
    )
    for g in gates:
        status = "PASS" if g.passed else "FAIL"
        lines.append(f"{g.gate_id} {g.name:<22} {status:<6} {g.actual:<19} {g.threshold}")
    lines.append("")
    lines.append(f"VERDICT: {verdict}")
    return "\n".join(lines)


def evaluate_phase2_gates(
    wf_slices: pd.DataFrame,
    slip_stress: pd.DataFrame,
) -> list[ValidationGate]:
    """Phase 2 pass criteria: OOS 2024-26 net > 0 and net at 1.0pt slip > 0."""
    oos = wf_slices.loc[wf_slices["slice"] == "2024-2026"]
    oos_pnl = float(oos["net_pnl"].iloc[0]) if not oos.empty else -1.0
    slip_10 = slip_stress.loc[slip_stress["slippage_pts"] == 1.0]
    net_at_10 = float(slip_10["net_pnl"].iloc[0]) if not slip_10.empty else -1.0
    return [
        ValidationGate("P2a", "OOS net (2024-26)", oos_pnl > 0, f"{oos_pnl:.1f}", "> 0"),
        ValidationGate("P2b", "Net at 1.0pt slip", net_at_10 > 0, f"{net_at_10:.1f}", "> 0"),
    ]


def phase2_verdict(gates: list[ValidationGate]) -> str:
    if all(g.passed for g in gates):
        return "PASS - proceed to Phase 3 (ES portfolio) or extended paper trading on 90d config"
    return "FAIL - remain on 14d config; do not optimize further parameters"


def evaluate_gao_gates(
    net_summary: dict,
    gross_summary: dict,
    trades_df: pd.DataFrame,
    bootstrap: dict[str, float],
    annual: pd.DataFrame,
    slip_stress: pd.DataFrame,
    wf_slices: pd.DataFrame,
) -> list[ValidationGate]:
    """Gao session momentum gates: standard V1-V9 plus mean net/trade friction floor."""
    gates = evaluate_momentum_gates(
        net_summary, gross_summary, trades_df, bootstrap, annual, slip_stress, wf_slices
    )
    mean_net = float(trades_df["pnl_points"].mean()) if not trades_df.empty else 0.0
    gates.append(
        ValidationGate(
            "V10",
            "Mean net/trade",
            mean_net > 2.0,
            f"{mean_net:.2f}",
            "> 2.0 pts",
        )
    )
    return gates


def gao_verdict(gates: list[ValidationGate]) -> str:
    passed = {g.gate_id: g.passed for g in gates}
    deploy = (
        passed.get("V1")
        and passed.get("V2")
        and passed.get("V3")
        and passed.get("V7")
        and passed.get("V10")
    )
    if deploy and all(passed.values()):
        return "KEEP - all Gao validation gates passed; proceed to paper trading"
    if deploy:
        return "VALIDATE - core Gao gates pass (gross, 0.5/1.0 slip, OOS, thick edge); review secondary gates"
    if passed.get("V1") and passed.get("V2"):
        return "MARGINAL - positive at 0.5pt but failed 1.0pt slip, OOS, or friction floor"
    return "CANCEL - Gao session momentum does not survive validation"


def format_gao_validation_report(
    gates: list[ValidationGate],
    verdict: str,
    annual: pd.DataFrame,
    wf_slices: pd.DataFrame,
    slip_stress: pd.DataFrame,
    bootstrap: dict[str, float],
    payoff: dict[str, float],
    exit_breakdown: pd.DataFrame,
) -> str:
    lines = [
        "=== Gao Session Momentum Validation Report ===",
        "",
        "--- Paper-style metrics ---",
        f"Avg bps/trade: {bootstrap['mean_bps']:.2f}",
        f"Bootstrap 95% CI: [{bootstrap['ci_low']:.2f}, {bootstrap['ci_high']:.2f}]",
        f"P(bootstrap mean > 0): {bootstrap['p_positive']:.1%}",
        f"Win rate: {payoff['win_rate']:.1%}",
        f"Payoff ratio: {payoff['payoff_ratio']:.2f}",
        f"Avg win: {payoff['avg_win_pts']:.1f} pts | Avg loss: {payoff['avg_loss_pts']:.1f} pts",
        "",
        "--- Annual breakdown ---",
    ]
    for _, row in annual.iterrows():
        lines.append(
            f"  {int(row['year'])}: {int(row['trades'])} trades, "
            f"net {row['net_pnl']:+.1f} pts, avg {row['avg_bps']:+.2f} bps, "
            f"WR {row['win_rate']:.0%}"
        )

    lines.extend(["", "--- Walk-forward slices ---"])
    for _, row in wf_slices.iterrows():
        lines.append(
            f"  {row['slice']}: {int(row['trades'])} trades, "
            f"net {row['net_pnl']:+.1f} pts, avg {row['avg_bps']:+.2f} bps"
        )

    lines.extend(["", "--- Slippage stress ---"])
    for _, row in slip_stress.iterrows():
        lines.append(
            f"  slip {row['slippage_pts']:.1f}pt: net {row['net_pnl']:+.1f}, "
            f"gross {row['gross_pnl']:+.1f}, avg {row['avg_bps']:+.2f} bps, PF {row['profit_factor']:.2f}"
        )

    if not exit_breakdown.empty:
        lines.extend(["", "--- Exit reason breakdown ---"])
        for _, row in exit_breakdown.iterrows():
            lines.append(
                f"  {row['exit_reason']}: n={int(row['count'])}, net {row['net_pnl']:+.1f}, "
                f"avg {row['avg_bps']:+.2f} bps, WR {row['win_rate']:.0%}"
            )

    lines.extend(
        [
            "",
            "Gate          Status  Actual              Threshold",
            "------------------------------------------------------",
        ]
    )
    for g in gates:
        status = "PASS" if g.passed else "FAIL"
        lines.append(f"{g.gate_id} {g.name:<22} {status:<6} {g.actual:<19} {g.threshold}")
    lines.append("")
    lines.append(f"VERDICT: {verdict}")
    return "\n".join(lines)


def compute_eu_spread_pass_rate(prepared_bars: pd.DataFrame) -> float:
    """Fraction of EU entry bars with spread within max_overnight_spread."""
    if prepared_bars.empty or "is_eu_entry_bar" not in prepared_bars.columns:
        return 0.0
    entries = prepared_bars.loc[prepared_bars["is_eu_entry_bar"]]
    if entries.empty:
        return 0.0
    if "spread_ok" in entries.columns:
        return float(entries["spread_ok"].mean())
    return 1.0


def evaluate_overnight_gates(
    net_summary: dict,
    gross_summary: dict,
    trades_df: pd.DataFrame,
    bootstrap: dict[str, float],
    annual: pd.DataFrame,
    slip_stress: pd.DataFrame,
    wf_slices: pd.DataFrame,
    eu_spread_pass_rate: float,
) -> list[ValidationGate]:
    gates = evaluate_gao_gates(
        net_summary, gross_summary, trades_df, bootstrap, annual, slip_stress, wf_slices
    )
    slip_20 = slip_stress.loc[slip_stress["slippage_pts"] == 2.0]
    net_at_20 = float(slip_20["net_pnl"].iloc[0]) if not slip_20.empty else -1.0
    gates.append(
        ValidationGate("V3b", "Net at 2.0pt slip", net_at_20 > 0, f"{net_at_20:.1f}", "> 0")
    )
    gates.append(
        ValidationGate(
            "V11",
            "EU spread pass rate",
            eu_spread_pass_rate >= 0.8,
            f"{eu_spread_pass_rate:.1%}",
            ">= 80%",
        )
    )
    return gates


def overnight_verdict(gates: list[ValidationGate]) -> str:
    passed = {g.gate_id: g.passed for g in gates}
    deploy = (
        passed.get("V1")
        and passed.get("V2")
        and passed.get("V3")
        and passed.get("V3b")
        and passed.get("V7")
        and passed.get("V10")
        and passed.get("V11")
    )
    if deploy and all(passed.values()):
        return "KEEP - all overnight validation gates passed; proceed to paper trading"
    if deploy:
        return "VALIDATE - core overnight gates pass; review secondary gates"
    if passed.get("V1") and passed.get("V2"):
        return "MARGINAL - positive at 0.5pt but failed 2.0pt slip, OOS, or spread quality"
    return "CANCEL - overnight EU open does not survive validation"


def format_overnight_validation_report(
    gates: list[ValidationGate],
    verdict: str,
    annual: pd.DataFrame,
    wf_slices: pd.DataFrame,
    slip_stress: pd.DataFrame,
    bootstrap: dict[str, float],
    payoff: dict[str, float],
    exit_breakdown: pd.DataFrame,
    eu_spread_pass_rate: float,
) -> str:
    lines = [
        "=== Overnight EU Open Validation Report ===",
        f"EU entry spread pass rate: {eu_spread_pass_rate:.1%}",
        "",
        "--- Paper-style metrics ---",
        f"Avg bps/trade: {bootstrap['mean_bps']:.2f}",
        f"Bootstrap 95% CI: [{bootstrap['ci_low']:.2f}, {bootstrap['ci_high']:.2f}]",
        f"P(bootstrap mean > 0): {bootstrap['p_positive']:.1%}",
        f"Win rate: {payoff['win_rate']:.1%}",
        f"Payoff ratio: {payoff['payoff_ratio']:.2f}",
        f"Avg win: {payoff['avg_win_pts']:.1f} pts | Avg loss: {payoff['avg_loss_pts']:.1f} pts",
        "",
        "--- Annual breakdown ---",
    ]
    for _, row in annual.iterrows():
        lines.append(
            f"  {int(row['year'])}: {int(row['trades'])} trades, "
            f"net {row['net_pnl']:+.1f} pts, avg {row['avg_bps']:+.2f} bps, "
            f"WR {row['win_rate']:.0%}"
        )

    lines.extend(["", "--- Walk-forward slices ---"])
    for _, row in wf_slices.iterrows():
        lines.append(
            f"  {row['slice']}: {int(row['trades'])} trades, "
            f"net {row['net_pnl']:+.1f} pts, avg {row['avg_bps']:+.2f} bps"
        )

    lines.extend(["", "--- Slippage stress ---"])
    for _, row in slip_stress.iterrows():
        lines.append(
            f"  slip {row['slippage_pts']:.1f}pt: net {row['net_pnl']:+.1f}, "
            f"gross {row['gross_pnl']:+.1f}, avg {row['avg_bps']:+.2f} bps, PF {row['profit_factor']:.2f}"
        )

    if not exit_breakdown.empty:
        lines.extend(["", "--- Exit reason breakdown ---"])
        for _, row in exit_breakdown.iterrows():
            lines.append(
                f"  {row['exit_reason']}: n={int(row['count'])}, net {row['net_pnl']:+.1f}, "
                f"avg {row['avg_bps']:+.2f} bps, WR {row['win_rate']:.0%}"
            )

    lines.extend(
        [
            "",
            "Gate          Status  Actual              Threshold",
            "------------------------------------------------------",
        ]
    )
    for g in gates:
        status = "PASS" if g.passed else "FAIL"
        lines.append(f"{g.gate_id} {g.name:<22} {status:<6} {g.actual:<19} {g.threshold}")
    lines.append("")
    lines.append(f"VERDICT: {verdict}")
    return "\n".join(lines)


def format_phase2_report(gates: list[ValidationGate], verdict: str, lookback_days: int) -> str:
    lines = [
        f"=== Phase 2 Gate (90d lookback = {lookback_days}) ===",
        "",
        "Gate          Status  Actual              Threshold",
        "------------------------------------------------------",
    ]
    for g in gates:
        status = "PASS" if g.passed else "FAIL"
        lines.append(f"{g.gate_id} {g.name:<22} {status:<6} {g.actual:<19} {g.threshold}")
    lines.append("")
    lines.append(f"VERDICT: {verdict}")
    return "\n".join(lines)


def tsmom_lookback_stress(
    df: pd.DataFrame,
    config: AppConfig,
    lookback_days: list[int],
) -> pd.DataFrame:
    rows = []
    for lb in lookback_days:
        cfg = config.model_copy(deep=True)
        cfg.strategy.tsmom_lookback_days = lb
        prepared = prepare_bars(df, cfg)
        net = run_backtest(df, cfg, prepared_bars=prepared)
        gross_cfg = config.model_copy(deep=True)
        gross_cfg.costs.slippage_points = 0.0
        gross_cfg.strategy.tsmom_lookback_days = lb
        gross = run_backtest(df, gross_cfg, prepared_bars=prepared)
        summary = summarize_backtest(net, gross)
        tdf = trades_to_enriched_df(net)
        rows.append(
            {
                "lookback_days": lb,
                "trades": summary["net"]["trade_count"],
                "net_pnl": summary["net"]["total_pnl"],
                "gross_pnl": summary["gross"]["total_pnl"],
                "avg_bps": float(tdf["return_bps"].mean()) if not tdf.empty else 0.0,
            }
        )
    return pd.DataFrame(rows)


def side_gross_pnl(trades_df: pd.DataFrame) -> dict[str, float]:
    if trades_df.empty:
        return {"long_pnl": 0.0, "short_pnl": 0.0}
    long_pnl = float(trades_df.loc[trades_df["side"] == "long", "pnl_points"].sum())
    short_pnl = float(trades_df.loc[trades_df["side"] == "short", "pnl_points"].sum())
    return {"long_pnl": long_pnl, "short_pnl": short_pnl}


def evaluate_tsmom_gates(
    net_summary: dict,
    gross_summary: dict,
    trades_df: pd.DataFrame,
    gross_trades_df: pd.DataFrame,
    annual: pd.DataFrame,
    slip_stress: pd.DataFrame,
    wf_slices: pd.DataFrame,
    lookback_stress_df: pd.DataFrame,
    *,
    tsmom_long_only: bool = False,
) -> list[ValidationGate]:
    gross_pnl = gross_summary["gross"]["total_pnl"]
    net_pnl = net_summary["net"]["total_pnl"]
    avg_bps = float(trades_df["return_bps"].mean()) if not trades_df.empty else 0.0

    slip_20 = slip_stress.loc[slip_stress["slippage_pts"] == 2.0]
    net_at_20 = float(slip_20["net_pnl"].iloc[0]) if not slip_20.empty else -1.0

    oos = wf_slices.loc[wf_slices["slice"] == "2024-2026"]
    oos_pnl = float(oos["net_pnl"].iloc[0]) if not oos.empty else -1.0

    positive_years = int((annual["net_pnl"] > 0).sum()) if not annual.empty else 0
    total_years = len(annual)
    year_pct = positive_years / total_years if total_years else 0.0

    lb_gross_ok = (
        not lookback_stress_df.empty
        and (lookback_stress_df["gross_pnl"] > 0).all()
    )
    sides = side_gross_pnl(gross_trades_df)
    short_count = (
        int((gross_trades_df["side"] == "short").sum()) if not gross_trades_df.empty else 0
    )

    gates = [
        ValidationGate("V1", "Gross PnL", gross_pnl > 0, f"{gross_pnl:.1f}", "> 0"),
        ValidationGate("V2", "Net @ 0.5pt slip", net_pnl > 0, f"{net_pnl:.1f}", "> 0"),
        ValidationGate("V3", "Net @ 2.0pt slip", net_at_20 > 0, f"{net_at_20:.1f}", "> 0"),
        ValidationGate("V4", "Avg bps/trade", avg_bps > 30, f"{avg_bps:.2f}", "> 30"),
        ValidationGate("V5", "OOS net (2024-26)", oos_pnl > 0, f"{oos_pnl:.1f}", "> 0"),
        ValidationGate(
            "V6",
            "Positive years",
            year_pct >= 0.5,
            f"{positive_years}/{total_years} ({year_pct:.0%})",
            ">= 50%",
        ),
        ValidationGate(
            "V7",
            "Lookback stress gross",
            lb_gross_ok,
            "all > 0" if lb_gross_ok else "fail",
            "9/12/18m gross > 0",
        ),
    ]

    if tsmom_long_only:
        gates.extend(
            [
                ValidationGate(
                    "V8",
                    "No short trades",
                    short_count == 0,
                    f"{short_count}",
                    "== 0",
                ),
                ValidationGate(
                    "V8b",
                    "Long gross PnL",
                    sides["long_pnl"] > 0,
                    f"{sides['long_pnl']:.0f}",
                    "> 0",
                ),
            ]
        )
    else:
        gates.append(
            ValidationGate(
                "V8",
                "Long+short gross",
                sides["long_pnl"] > 0 and sides["short_pnl"] > 0,
                f"L {sides['long_pnl']:.0f} / S {sides['short_pnl']:.0f}",
                "both > 0",
            )
        )

    return gates


def tsmom_verdict(gates: list[ValidationGate]) -> str:
    passed = {g.gate_id: g.passed for g in gates}
    core = [passed.get(f"V{i}", False) for i in range(1, 6)]
    if all(passed.values()):
        return "KEEP - all TSMOM validation gates passed; proceed to paper trading"
    if all(core):
        return "VALIDATE - core TSMOM gates pass; review secondary gates"
    if passed.get("V1") and passed.get("V2"):
        return "MARGINAL - gross+net positive but slip/OOS or robustness gates failed"
    return "CANCEL - daily TSMOM does not survive validation"


def format_tsmom_validation_report(
    gates: list[ValidationGate],
    verdict: str,
    annual: pd.DataFrame,
    wf_slices: pd.DataFrame,
    slip_stress: pd.DataFrame,
    lookback_stress_df: pd.DataFrame,
    bootstrap: dict[str, float],
    payoff: dict[str, float],
    exit_breakdown: pd.DataFrame,
    sides: dict[str, float],
) -> str:
    lines = [
        "=== Daily TSMOM Validation Report ===",
        "",
        f"Long gross: {sides['long_pnl']:+.1f} pts | Short gross: {sides['short_pnl']:+.1f} pts",
        "",
        "--- Paper-style metrics ---",
        f"Avg bps/trade: {bootstrap['mean_bps']:.2f}",
        f"Bootstrap 95% CI: [{bootstrap['ci_low']:.2f}, {bootstrap['ci_high']:.2f}]",
        f"P(bootstrap mean > 0): {bootstrap['p_positive']:.1%}",
        f"Win rate: {payoff['win_rate']:.1%}",
        f"Payoff ratio: {payoff['payoff_ratio']:.2f}",
        "",
        "--- Annual breakdown ---",
    ]
    for _, row in annual.iterrows():
        lines.append(
            f"  {int(row['year'])}: {int(row['trades'])} trades, "
            f"net {row['net_pnl']:+.1f} pts, avg {row['avg_bps']:+.2f} bps, "
            f"WR {row['win_rate']:.0%}"
        )

    lines.extend(["", "--- Walk-forward slices ---"])
    for _, row in wf_slices.iterrows():
        lines.append(
            f"  {row['slice']}: {int(row['trades'])} trades, "
            f"net {row['net_pnl']:+.1f} pts, avg {row['avg_bps']:+.2f} bps"
        )

    lines.extend(["", "--- Slippage stress ---"])
    for _, row in slip_stress.iterrows():
        lines.append(
            f"  slip {row['slippage_pts']:.1f}pt: net {row['net_pnl']:+.1f}, "
            f"gross {row['gross_pnl']:+.1f}, avg {row['avg_bps']:+.2f} bps"
        )

    lines.extend(["", "--- Lookback stress (9m / 12m / 18m) ---"])
    for _, row in lookback_stress_df.iterrows():
        lines.append(
            f"  {int(row['lookback_days'])}d: net {row['net_pnl']:+.1f}, "
            f"gross {row['gross_pnl']:+.1f}, avg {row['avg_bps']:+.2f} bps"
        )

    if not exit_breakdown.empty:
        lines.extend(["", "--- Exit reason breakdown ---"])
        for _, row in exit_breakdown.iterrows():
            lines.append(
                f"  {row['exit_reason']}: n={int(row['count'])}, net {row['net_pnl']:+.1f}, "
                f"avg {row['avg_bps']:+.2f} bps, WR {row['win_rate']:.0%}"
            )

    lines.extend(
        [
            "",
            "Gate          Status  Actual              Threshold",
            "------------------------------------------------------",
        ]
    )
    for g in gates:
        status = "PASS" if g.passed else "FAIL"
        lines.append(f"{g.gate_id} {g.name:<22} {status:<6} {g.actual:<19} {g.threshold}")
    lines.append("")
    lines.append(f"VERDICT: {verdict}")
    return "\n".join(lines)
