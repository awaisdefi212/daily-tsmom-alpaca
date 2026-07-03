# NAS100 Intraday Momentum — 3-Phase Refinement

> **SUPERSEDED / CANCELLED** — Intraday momentum was fully archived on user decision. See [STRATEGY_VERDICT.md](STRATEGY_VERDICT.md). This document records why Phases 1–3 were abandoned.

**Original status:** REMAIN intraday momentum (do not replace with ORB).

**Final outcome:** CANCEL — OOS failure, slippage cliff, and Phase 2 (90d lookback) gate failure led to full archive alongside ORB strategies.

## Phase 1 — Paper slippage proof (never completed)

1. Copy `data/paper_trade/paper_trade_log_template.csv` to `data/paper_trade/paper_trade_log.csv`
2. Paper trade **20 RTH sessions** using archived `config/archive/strategy_intraday_momentum_5m.yaml` rules
3. Log each trade: intended vs fill prices at entry and exit
4. Run gate:

```bash
python scripts/analyze_paper_slippage.py
```

**PASS:** avg round-trip slippage <= 1.0 pt (0.5 pt/side) over 20+ sessions  
**FAIL:** do not go live; edge may not survive your broker costs

**Abandoned:** strategy cancelled before Phase 1 was run.

## Phase 2 — 90-day lookback (completed — FAIL)

```bash
python scripts/validate_momentum.py --config config/archive/strategy_intraday_momentum_90d.yaml --phase2
```

**Result:** FAIL — OOS 2024-26 net -2,393; net at 1.0pt slip -915.

## Phase 3 — ES portfolio (skipped)

ES bid/ask data was never added. `validate_portfolio.py` returned SKIPPED.

## Original decision rule

```
Phase 1 PASS -> Phase 2 validation on 90d
Phase 2 PASS -> Phase 3 ES portfolio OR extended paper on 90d
Phase 1 FAIL -> cancel live deployment
```

**Actual path:** Phase 2 FAIL + user decision to fully cancel → all momentum configs archived.
