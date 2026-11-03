"""Faithful port of the course starter's logic for the audit (docs/STARTER_AUDIT.md).

Source: github.com/myrah/AAI2025, aai/InventoryReplenishmentAgent.ipynb (dev branch). Arithmetic and
control flow follow the starter line for line. Two substitutions keep the port light:
pydantic's Obs becomes plain arguments, and scipy's norm.ppf becomes statistics.NormalDist.
"""

from __future__ import annotations

from collections import deque
from statistics import NormalDist

import numpy as np
import pandas as pd


def starter_demand() -> pd.DataFrame:
    """Cell 1: the starter's synthetic series (2024-01-01..2025-06-30, rng seed 7) and its train/test split."""
    rng = np.random.default_rng(7)
    idx = pd.date_range(pd.Timestamp("2024-01-01"), pd.Timestamp("2025-06-30"), freq="D")
    n = len(idx)
    weekly = 10 + 4 * np.sin(2 * np.pi * idx.day_of_week / 7)
    yearly = 5 + 3 * np.sin(2 * np.pi * idx.day_of_year / 365)
    trend = np.linspace(0, 8, n)
    promos = np.zeros(n)
    promo_days = rng.choice(n, size=20, replace=False)
    promos[promo_days] = rng.integers(10, 30, size=20)
    noise = rng.normal(0, 2, n)
    demand = np.maximum(0, (weekly + yearly + trend + promos + noise).round())
    df = pd.DataFrame({"date": idx, "demand": demand})
    df["split"] = np.where(df["date"] < pd.Timestamp("2024-04-01"), "train", "test")
    return df


def starter_static_rop(train_demand, L: int = 7, csl: float = 0.95) -> tuple[float, float, float]:
    """Cell 2: ROP = L*mu + z*sqrt(L)*sigma, with sigma = std of raw training demand."""
    mu = float(np.mean(train_demand))
    sigma = float(pd.Series(train_demand).std(ddof=1))
    z = NormalDist().inv_cdf(csl)
    return L * mu + z * np.sqrt(L) * sigma, mu, sigma


def starter_eoq(mu: float, K: float = 250.0, h: float = 0.2) -> float:
    """Cell 2: EOQ = sqrt(2*K*D/h) with annual demand and annual holding cost."""
    return float(np.sqrt((2 * K * mu * 365) / (h * 365)))


def starter_features(demand: pd.Series) -> pd.DataFrame:
    """Cell 3: the features fed to the RandomForest (lag1, lag7, ma7)."""
    feat = pd.DataFrame({"demand": demand})
    feat["lag1"] = feat["demand"].shift(1)
    feat["lag7"] = feat["demand"].shift(7)
    feat["ma7"] = feat["demand"].rolling(7).mean()
    return feat


def starter_tool_forecast(current_idx, horizon, series_pred, default_mu):
    """Cell 5, verbatim: average of the next `horizon` predictions."""
    window = series_pred[current_idx: current_idx + horizon]
    if len(window) == 0:
        return default_mu * horizon
    return float(np.maximum(0, window.mean()) * horizon)


class StarterInventorySim:
    """Cell 4, verbatim apart from the pandas import."""

    def __init__(self, L, h, K, p, init_on_hand):
        self.L, self.h, self.K, self.p = L, h, K, p
        self.on_hand = init_on_hand
        self.pipeline = deque(maxlen=L)
        for _ in range(L):
            self.pipeline.append(0)
        self.backlog = 0
        self.cost_holding = 0.0
        self.cost_order = 0.0
        self.cost_stockout = 0.0
        self.orders_log = []
        self.state_log = []

    def step(self, demand, order_qty=0, date=None):
        arriving = self.pipeline.popleft()
        self.on_hand += arriving
        self.pipeline.append(0)

        available = self.on_hand
        sales = min(available, demand + self.backlog)
        self.on_hand -= sales
        self.backlog = demand + self.backlog - sales

        if order_qty > 0:
            self.pipeline[-1] += order_qty
            self.cost_order += self.K + 0 * order_qty
            self.orders_log.append({"date": date, "qty": order_qty})

        self.cost_holding += self.h * max(self.on_hand, 0)
        self.cost_stockout += self.p * self.backlog

        self.state_log.append({"date": date, "on_hand": self.on_hand, "backlog": self.backlog,
                               "arrivals": arriving, "sales": sales})

    def inventory_position(self):
        return self.on_hand + sum(self.pipeline) - self.backlog

    def kpis(self):
        log = pd.DataFrame(self.state_log)
        fill_rate = 1 - (log["backlog"].diff().clip(lower=0).sum() / (log["sales"] + log["backlog"]).sum())
        return {"fill_rate": fill_rate, "holding_cost": self.cost_holding, "order_cost": self.cost_order,
                "stockout_cost": self.cost_stockout,
                "total_cost": self.cost_holding + self.cost_order + self.cost_stockout}


class StarterAgent:
    """Cell 6: decide() compares inventory position with the static global ROP, passed in here."""

    def __init__(self, ROP, S_buffer=1.2):
        self.ROP = ROP
        self.S_buffer = S_buffer

    def decide(self, on_hand, pipeline, backlog, forecast_DL):
        inv_pos = on_hand + pipeline - backlog
        S = self.ROP + self.S_buffer * forecast_DL
        action = "order_to_S" if inv_pos <= self.ROP else "noop"
        return action, int(round(max(0, S - inv_pos)))


def run_starter_baseline(demand, rop, q, L=7, h=0.2, K=250.0, p=3.0, init_on_hand=None) -> StarterInventorySim:
    """Cell 4's baseline loop: order Q whenever inventory position <= ROP."""
    sim = StarterInventorySim(L, h, K, p, rop if init_on_hand is None else init_on_hand)
    for d in demand:
        order = int(max(1, round(q))) if sim.inventory_position() <= rop else 0
        sim.step(d, order_qty=order)
    return sim
