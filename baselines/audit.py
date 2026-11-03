"""Before/after KPIs on the starter's own data (L=7, CSL 0.95, K=250, h=0.2, p=3), one fix at a time."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from replenish.agent import ReplenishmentAgent
from replenish.data import SkuParams
from replenish.evaluate import sku_metrics
from replenish.policy import z_value
from replenish.sim import SimConfig, simulate_sku

from .starter_port import run_starter_baseline, starter_demand, starter_eoq, starter_static_rop

L, CSL, K, H, P = 7, 0.95, 250.0, 0.2, 3.0


class ReorderAt:
    """The starter's rule (order Q when inventory position <= ROP) inside our simulator."""

    def __init__(self, rop: float, q: int, mu: float):
        self.rop, self.q, self.mu = rop, q, mu

    def decide(self, obs):
        order = obs.ip <= self.rop
        return SimpleNamespace(action="ORDER" if order else "HOLD", qty=self.q if order else 0, forecast=self.mu)

    def learn(self, demand):
        pass


def starter_before_after() -> pd.DataFrame:
    df = starter_demand()
    train = df[df.split == "train"].demand.to_numpy(float)
    test = df[df.split == "test"].demand.to_numpy(float)
    rop, mu, sigma = starter_static_rop(train, L, CSL)
    q = int(max(1, round(starter_eoq(mu, K, H))))
    params = SkuParams("STARTER", unit_cost=1.0, holding_cost_per_day=H, stockout_cost=P,
                       lead_time_days=L, min_order_qty=q, service_level=CSL)
    config = SimConfig(order_cost=K)
    rows = []

    kpi = run_starter_baseline(test, rop, q, L=L, h=H, K=K, p=P).kpis()
    rows.append({"version": "Starter as shipped (its own sim and KPIs)", "fill_rate": kpi["fill_rate"],
                 "stockout_days": np.nan, "holding_cost": kpi["holding_cost"], "order_cost": kpi["order_cost"],
                 "stockout_cost": kpi["stockout_cost"], "total_cost": kpi["total_cost"]})

    def ours(label, policy):
        m = sku_metrics(simulate_sku("STARTER", test, params, rop, policy, config=config))
        rows.append({"version": label, "fill_rate": m["fill_rate"], "stockout_days": m["stockout_days"],
                     "holding_cost": m["holding_cost"], "order_cost": m["order_cost"],
                     "stockout_cost": m["stockout_cost"], "total_cost": m["relevant_cost"]})

    ours("Same policy, metrics fixed (H5 fill rate, H6 stockout charged once)", ReorderAt(rop, q, mu))
    rop_l1 = (L + 1) * mu + z_value(CSL) * np.sqrt(L + 1) * sigma
    ours("+ protection interval L+1 (H7)", ReorderAt(rop_l1, q, mu))
    ours("Our textbook agent P2: EWMA, sigma from forecast error (H1-H4, H7), MOQ = EOQ",
         ReplenishmentAgent("STARTER", params, train, defer=False, reflect=False))
    ours("Our full agent P3: + defer + calibrated reflect, MOQ = EOQ",
         ReplenishmentAgent("STARTER", params, train, defer=True, reflect=True))
    return pd.DataFrame(rows)
