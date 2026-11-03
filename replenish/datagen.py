"""Seeded synthetic data. Three SKU archetypes, each chosen to push a different branch of the agent."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import WARMUP_DAYS

N_DAYS = 120
START_DATE = "2025-01-01"
DATA_SEED = 7

# Cost rates are scaled up from real-world levels so the holding-vs-stockout trade-off
# shows up inside a 92-day simulation.
SKUS = {
    "SKU-A": dict(archetype="fast mover", unit_cost=4.00, holding_cost_per_day=0.02,
                  stockout_cost=1.50, lead_time_days=3, min_order_qty=60,
                  service_level=0.95, opening_stock=200),
    "SKU-B": dict(archetype="trend + promos", unit_cost=25.00, holding_cost_per_day=0.10,
                  stockout_cost=25.00, lead_time_days=7, min_order_qty=120,
                  service_level=0.98, opening_stock=90),
    "SKU-C": dict(archetype="intermittent", unit_cost=80.00, holding_cost_per_day=0.40,
                  stockout_cost=40.00, lead_time_days=10, min_order_qty=24,
                  service_level=0.98, opening_stock=30),
}
PARAM_COLUMNS = ["sku", "unit_cost", "holding_cost_per_day", "stockout_cost",
                 "lead_time_days", "min_order_qty", "service_level"]


def daily_demand(seed: int = DATA_SEED, n_days: int = N_DAYS) -> dict[str, np.ndarray]:
    """True daily demand per SKU. Monte Carlo runs call this with other seeds."""
    rng = np.random.default_rng(seed)
    t = np.arange(n_days)
    fast = 40 * (1 + 0.25 * np.sin(2 * np.pi * t / 7)) + rng.normal(0, 6, n_days)
    trend = np.linspace(12, 20, n_days)
    promo_days = rng.choice(np.arange(WARMUP_DAYS, n_days), size=6, replace=False)
    trend[promo_days] *= 2.5
    trend_promo = trend + rng.normal(0, 3, n_days)
    intermittent = rng.binomial(1, 0.35, n_days) * rng.integers(1, 7, n_days)
    series = {"SKU-A": fast, "SKU-B": trend_promo, "SKU-C": intermittent}
    return {sku: np.clip(np.rint(x), 0, None).astype(int) for sku, x in series.items()}


def to_transactions(demand: dict[str, np.ndarray], start: str = START_DATE,
                    seed: int = DATA_SEED) -> pd.DataFrame:
    """Split each SKU-day into 1-4 order lines; zero-demand days get no rows at all."""
    rng = np.random.default_rng(seed + 1)
    n_days = len(next(iter(demand.values())))
    dates = pd.date_range(start, periods=n_days, freq="D").strftime("%Y-%m-%d")
    rows = []
    for i, date in enumerate(dates):
        for sku, series in demand.items():
            qty = int(series[i])
            if qty == 0:
                continue
            lines = min(qty, int(rng.integers(1, 5)))
            cuts = np.sort(rng.choice(np.arange(1, qty), size=lines - 1, replace=False)) if lines > 1 else []
            for q in np.diff(np.concatenate(([0], cuts, [qty]))):
                rows.append((date, sku, int(q)))
    return pd.DataFrame(rows, columns=["date", "sku", "qty_sold"])


def write_dataset(out_dir: str | Path = "data", seed: int = DATA_SEED) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {name: out / f"{name}.csv" for name in ("sales", "inventory", "params")}
    to_transactions(daily_demand(seed), seed=seed).to_csv(paths["sales"], index=False)
    pd.DataFrame([(sku, spec["opening_stock"]) for sku, spec in SKUS.items()],
                 columns=["sku", "opening_stock"]).to_csv(paths["inventory"], index=False)
    pd.DataFrame([{"sku": sku, **{c: spec[c] for c in PARAM_COLUMNS[1:]}} for sku, spec in SKUS.items()],
                 columns=PARAM_COLUMNS).to_csv(paths["params"], index=False)
    return paths
