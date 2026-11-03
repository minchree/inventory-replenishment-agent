"""Metrics, the policy line-up, Monte Carlo, the service-level sweep, and per-SKU diagnostics."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .agent import ClairvoyantPolicy, ReplenishmentAgent, StaticReorderPolicy
from .config import TEST_SEED0, TS_ALARM_SD, WARMUP_DAYS
from .data import Dataset, SkuParams
from .datagen import daily_demand
from .policy import economic_csl, predicted_fill_rate
from .sim import SimConfig, SkuRun, simulate_sku

NAN = float("nan")

POLICIES = {
    "P0 starter (s,Q)": dict(kind="static"),
    "P1 naive agent": dict(kind="agent", forecaster="naive", defer=False, reflect=False),
    "P2 EWMA textbook": dict(kind="agent", forecaster="ewma", defer=False, reflect=False),
    "P3 full agent": dict(kind="agent", forecaster="ewma", defer=True, reflect=True),
    "P4 clairvoyant": dict(kind="clairvoyant"),
}
ABLATIONS = {
    "P3 without defer": dict(kind="agent", forecaster="ewma", defer=False, reflect=True),
    "P3 without reflect": dict(kind="agent", forecaster="ewma", defer=True, reflect=False),
}
HEADLINE = "P3 full agent"
SL_GRID = (0.80, 0.85, 0.90, 0.925, 0.95, 0.96, 0.97, 0.98, 0.99, 0.995)
ADDITIVE = ("demand", "filled", "units_short", "stockout_days", "holding_cost", "stockout_cost",
            "order_cost", "relevant_cost", "purchase_spend", "ending_value", "avg_inventory_value", "pos",
            "defers", "alerts", "capped", "cycles")
MC_METRICS = ("fill_rate", "stockout_days", "relevant_cost", "achieved_csl", "holding_cost",
              "stockout_cost", "order_cost", "avg_on_hand", "pos")


# ---------------------------------------------------------------- running policies

def build_policy(spec: dict, sku: str, params: SkuParams, history: np.ndarray, future: np.ndarray,
                 order_cost: float = 0.0):
    kind = spec["kind"]
    if kind == "agent":
        return ReplenishmentAgent(sku, params, history, forecaster=spec["forecaster"], alpha=spec.get("alpha"),
                                  defer=spec["defer"], reflect=spec["reflect"])
    if kind == "static":
        return StaticReorderPolicy(sku, params, history, order_cost)
    if kind == "clairvoyant":
        return ClairvoyantPolicy(sku, params, future)
    raise ValueError(f"unknown policy kind {kind!r}")


def run_sku(sku: str, series: np.ndarray, params: SkuParams, opening: float, spec: dict, *,
            config: SimConfig = SimConfig(), dates: list[str] | None = None) -> SkuRun:
    """Warm up on the first WARMUP_DAYS, then simulate the rest."""
    series = np.asarray(series, float)
    history, future = series[:WARMUP_DAYS], series[WARMUP_DAYS:]
    policy = build_policy(spec, sku, params, history, future, config.order_cost)
    return simulate_sku(sku, future, params, opening, policy, start_day=WARMUP_DAYS,
                        dates=dates[WARMUP_DAYS:] if dates is not None else None, config=config)


def run_policy(demand: dict[str, np.ndarray], params: dict[str, SkuParams], opening: dict[str, float],
               spec: dict, *, config: SimConfig = SimConfig(), dates: list[str] | None = None,
               service_level: float | dict[str, float] | None = None) -> dict[str, SkuRun]:
    runs = {}
    for sku, p in params.items():
        if service_level is not None:
            p = p.with_service_level(service_level[sku] if isinstance(service_level, dict) else service_level)
        runs[sku] = run_sku(sku, demand[sku], p, opening[sku], spec, config=config, dates=dates)
    return runs


def run_dataset(ds: Dataset, spec: dict, **kwargs) -> dict[str, SkuRun]:
    return run_policy({s: ds.series(s) for s in ds.skus}, ds.params, ds.opening, spec,
                      dates=ds.dates, **kwargs)


# ---------------------------------------------------------------- metrics

def achieved_csl(short: np.ndarray, arrivals: np.ndarray) -> tuple[float, int]:
    """Share of replenishment cycles (arrival to next arrival) with no stockout.

    The stretch before the first arrival depends only on opening stock, so it isn't counted.
    """
    if len(arrivals) == 0:
        return NAN, 0
    bounds = list(arrivals) + [len(short)]
    ok = [not (short[a:b] > 0).any() for a, b in zip(bounds[:-1], bounds[1:])]
    return float(np.mean(ok)), len(ok)


def sku_metrics(run: SkuRun) -> dict:
    g, p = run.ledger, run.params
    demand, filled = float(g["demand"].sum()), float(g["filled"].sum())
    csl, cycles = achieved_csl(g["short"], np.flatnonzero(g["received"] > 0))
    forecast = np.array([r.forecast for r in run.decisions], float)
    err = g["demand"] - forecast
    orders = g["ordered"][g["ordered"] > 0]
    avg_on_hand = float(g["on_hand_end"].mean())
    holding, stockout, ordering = (float(g[k].sum()) for k in ("holding_cost", "stockout_cost", "order_cost"))
    return {
        "demand": demand,
        "filled": filled,
        "fill_rate": filled / demand if demand > 0 else 1.0,
        "units_short": float(g["short"].sum()),
        "stockout_days": int((g["short"] > 0).sum()),
        "achieved_csl": csl,
        "cycles": cycles,
        "holding_cost": holding,
        "stockout_cost": stockout,
        "order_cost": ordering,
        "relevant_cost": holding + stockout + ordering,
        "purchase_spend": float(g["purchase_cost"].sum()),
        "ending_on_hand": float(g["on_hand_end"][-1]),
        "ending_value": float(g["on_hand_end"][-1] * p.unit_cost),
        "on_order_end": float(g["on_order_end"][-1]),
        "pos": int(len(orders)),
        "units_ordered": float(orders.sum()),
        "mean_order": float(orders.mean()) if len(orders) else NAN,
        "avg_on_hand": avg_on_hand,
        "avg_inventory_value": avg_on_hand * p.unit_cost,     # working capital tied up in stock
        "turns": float(g["shipped"].sum() / avg_on_hand) if avg_on_hand > 0 else NAN,
        "forecast_mae": float(np.abs(err).mean()),
        "forecast_bias": float(err.mean()),
        "defers": sum(r.action == "DEFER" for r in run.decisions),
        "alerts": sum(bool(getattr(r, "alert", "")) for r in run.decisions),
        "capped": sum(bool(getattr(r, "capped", False)) for r in run.decisions),
    }


def total_metrics(by_sku: dict[str, dict]) -> dict:
    tot = {k: sum(m[k] for m in by_sku.values()) for k in ADDITIVE}
    tot["fill_rate"] = tot["filled"] / tot["demand"] if tot["demand"] else 1.0
    good = sum(m["achieved_csl"] * m["cycles"] for m in by_sku.values() if m["cycles"])
    tot["achieved_csl"] = good / tot["cycles"] if tot["cycles"] else NAN
    tot["avg_on_hand"] = sum(m["avg_on_hand"] for m in by_sku.values())
    return tot


def metrics_table(runs: dict[str, SkuRun]) -> dict[str, dict]:
    by_sku = {sku: sku_metrics(run) for sku, run in runs.items()}
    return {**by_sku, "TOTAL": total_metrics(by_sku)}


def comparison_frame(tables: dict[str, dict[str, dict]]) -> pd.DataFrame:
    rows = [{"policy": name, "sku": sku, **m} for name, table in tables.items() for sku, m in table.items()]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- Monte Carlo and sweep

def monte_carlo(seeds, policies: dict[str, dict], params: dict[str, SkuParams], opening: dict[str, float],
                config: SimConfig = SimConfig()) -> pd.DataFrame:
    rows = []
    for seed in seeds:
        demand = daily_demand(seed)
        for name, spec in policies.items():
            for sku, m in metrics_table(run_policy(demand, params, opening, spec, config=config)).items():
                rows.append({"seed": seed, "policy": name, "sku": sku, **{k: m.get(k, NAN) for k in MC_METRICS}})
    return pd.DataFrame(rows)


def summarize(mc: pd.DataFrame, metrics=("fill_rate", "stockout_days", "relevant_cost")) -> pd.DataFrame:
    g = mc.groupby(["policy", "sku"], sort=False)
    cols = {}
    for m in metrics:
        cols[f"{m}_mean"] = g[m].mean()
        cols[f"{m}_p5"] = g[m].quantile(0.05)
        cols[f"{m}_p95"] = g[m].quantile(0.95)
    return pd.DataFrame(cols).reset_index()


def paired_delta(mc: pd.DataFrame, a: str, b: str, metric: str = "relevant_cost", sku: str = "TOTAL") -> dict:
    """Seed-by-seed comparison of policy a against policy b on the same demand paths."""
    x = mc[(mc.policy == a) & (mc.sku == sku)].set_index("seed")[metric]
    y = mc[(mc.policy == b) & (mc.sku == sku)].set_index("seed")[metric]
    d = (x - y).dropna()
    return {"a": a, "b": b, "metric": metric, "mean_delta": float(d.mean()),
            "p5": float(d.quantile(0.05)), "p95": float(d.quantile(0.95)),
            "share_a_lower": float((d < 0).mean()), "seeds": int(len(d))}


def service_level_sweep(seeds, params: dict[str, SkuParams], opening: dict[str, float], grid=SL_GRID,
                        extra: dict[str, list[float]] | None = None, spec: dict = POLICIES[HEADLINE],
                        config: SimConfig = SimConfig()) -> pd.DataFrame:
    rows = []
    for seed in seeds:
        demand = daily_demand(seed)
        for sku, p in params.items():
            levels = sorted(set(grid) | set((extra or {}).get(sku, [])))
            for sl in levels:
                m = sku_metrics(run_sku(sku, demand[sku], p.with_service_level(sl), opening[sku], spec, config=config))
                rows.append({"sku": sku, "service_level": sl, "seed": seed, "fill_rate": m["fill_rate"],
                             "relevant_cost": m["relevant_cost"], "stockout_days": m["stockout_days"]})
    df = pd.DataFrame(rows)
    return df.groupby(["sku", "service_level"], as_index=False)[["fill_rate", "relevant_cost", "stockout_days"]].mean()


# ---------------------------------------------------------------- diagnostics

def diagnostics(runs: dict[str, SkuRun]) -> dict[str, dict]:
    """Safety-stock table per SKU, plus the CSL* check of service_level against the cost parameters."""
    out = {}
    for sku, run in runs.items():
        agent, p = run.policy, run.params
        m = sku_metrics(run)
        mean_demand = float(run.ledger["demand"].mean())
        mean_order = m["mean_order"] if m["pos"] else float(p.min_order_qty)
        csl_star, cycle_days = economic_csl(p, mean_demand, mean_order)
        first = run.decisions[0]
        sigma_P = float(np.mean([r.sigma_P for r in run.decisions]))
        doesnt_pay = p.holding_cost_per_day * cycle_days >= p.stockout_cost
        if doesnt_pay:
            verdict = "safety stock does not pay at these costs"
        elif csl_star > p.service_level + 0.02:
            verdict = "costs favour more protection"
        elif csl_star < p.service_level - 0.02:
            verdict = "costs favour less protection"
        else:
            verdict = "aligned"
        out[sku] = {
            "demand_class": agent.demand_class.label,
            "adi": agent.demand_class.adi,
            "cv2": agent.demand_class.cv2,
            "alpha": agent.memory.base_alpha,
            "lead_time_days": p.lead_time_days,
            "service_level": p.service_level,
            "z": agent.z,
            "sigma1_start": first.sigma1,
            "mu_P_start": first.mu_P,
            "sigma_P_start": first.sigma_P,
            "ss_start": first.ss,
            "S_start": first.S,
            "mean_order": mean_order,
            "cycle_days": cycle_days,
            "csl_star": csl_star,
            "gap_pts": (csl_star - p.service_level) * 100,
            "flag": abs(csl_star - p.service_level) > 0.02,
            "verdict": verdict,
            "predicted_fill_rate": predicted_fill_rate(sigma_P, agent.z, mean_order),
            "achieved_fill_rate": m["fill_rate"],
            "achieved_csl": m["achieved_csl"],
        }
    return out


# ---------------------------------------------------------------- everything, written to outputs/

def _clean(obj):
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        return None if math.isnan(obj) or math.isinf(obj) else round(float(obj), 6)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def evaluate_all(ds: Dataset, out_dir: str | Path = "outputs", mc_seeds: int = 200, sweep_seeds: int = 100,
                 seed0: int = TEST_SEED0, log=print) -> dict:
    from . import report

    out = Path(out_dir)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    lineup = {**POLICIES, **ABLATIONS}

    log("single path (committed CSVs) ...")
    single = {name: metrics_table(run_dataset(ds, spec)) for name, spec in lineup.items()}
    single_k25 = {name: metrics_table(run_dataset(ds, spec, config=SimConfig(order_cost=25.0)))
                  for name, spec in POLICIES.items()}
    headline_runs = run_dataset(ds, POLICIES[HEADLINE])
    diag = diagnostics(headline_runs)

    log(f"Monte Carlo over {mc_seeds} demand seeds ...")
    seeds = range(seed0, seed0 + mc_seeds)
    mc = monte_carlo(seeds, lineup, ds.params, ds.opening)
    mc_k25 = monte_carlo(seeds, POLICIES, ds.params, ds.opening, config=SimConfig(order_cost=25.0))
    summary, summary_k25 = summarize(mc), summarize(mc_k25)
    deltas = [paired_delta(mc, HEADLINE, "P2 EWMA textbook"),
              paired_delta(mc, HEADLINE, "P3 without defer"),
              paired_delta(mc, HEADLINE, "P3 without reflect"),
              paired_delta(mc, HEADLINE, "P0 starter (s,Q)"),
              paired_delta(mc, HEADLINE, "P1 naive agent")]

    log(f"service-level sweep over {sweep_seeds} seeds ...")
    extra = {sku: [min(max(d["csl_star"], 0.5), 0.995)] for sku, d in diag.items()}
    sweep = service_level_sweep(range(seed0, seed0 + sweep_seeds), ds.params, ds.opening, extra=extra)

    comparison = comparison_frame(single)
    comparison.to_csv(out / "policy_comparison.csv", index=False)
    comparison_frame(single_k25).to_csv(out / "policy_comparison_k25.csv", index=False)
    mc.to_csv(out / "monte_carlo.csv", index=False)
    summary.to_csv(out / "mc_summary.csv", index=False)
    summary_k25.to_csv(out / "mc_summary_k25.csv", index=False)
    sweep.to_csv(out / "sl_sweep.csv", index=False)

    metrics = {
        "config": {"warmup_days": WARMUP_DAYS, "mc_seeds": mc_seeds, "sweep_seeds": sweep_seeds,
                   "seed0": seed0, "ts_alarm_sd": TS_ALARM_SD, "headline_policy": HEADLINE},
        "single_path": single,
        "single_path_k25": single_k25,
        "diagnostics": diag,
        "monte_carlo": summary.to_dict(orient="records"),
        "monte_carlo_k25": summary_k25.to_dict(orient="records"),
        "paired_deltas": deltas,
        "sl_sweep": sweep.to_dict(orient="records"),
    }
    (out / "metrics.json").write_text(json.dumps(_clean(metrics), indent=2), encoding="utf-8")

    log("figures ...")
    for sku, run in headline_runs.items():
        report.plot_inventory_story(run, out / "figures" / f"inventory_{sku}.png")
    report.plot_policy_comparison(summary, out / "figures" / "policy_comparison.png")
    report.plot_frontier(sweep, diag, out / "figures" / "sl_frontier.png")
    (out / "results.md").write_text(report.results_markdown(single, summary, deltas, diag, mc_seeds),
                                    encoding="utf-8")
    log(f"wrote {out}")
    return {"single": single, "single_k25": single_k25, "diagnostics": diag, "mc": mc, "summary": summary,
            "summary_k25": summary_k25, "deltas": deltas, "sweep": sweep, "headline_runs": headline_runs,
            "comparison": comparison}
