"""The 6-day hand-worked trace from docs/DESIGN.md: L=2, two MOQ-bound orders, one stockout.

Forecast is pinned at 10/day with sigma_1 = 2 and the defer test off, so every number is checkable by hand:
S = mu_P + z*sigma_P = 10*3 + 1.6449*2*sqrt(3) = 35.698.
"""

from types import SimpleNamespace

import numpy as np
import pytest

from replenish.data import SkuParams
from replenish.evaluate import sku_metrics
from replenish.policy import plan_order
from replenish.sim import simulate_sku

PARAMS = SkuParams("TRACE", unit_cost=5.0, holding_cost_per_day=0.10, stockout_cost=2.0,
                   lead_time_days=2, min_order_qty=20, service_level=0.95)
DEMAND = [12, 16, 14, 11, 8, 10]


class FixedForecast:
    def __init__(self):
        self.reviews = []

    def decide(self, obs):
        plan = plan_order(obs.ip, 10.0, 2.0, PARAMS, defer=False)
        self.reviews.append((obs.ip, plan.action, plan.qty, round(plan.S, 3)))
        return SimpleNamespace(action=plan.action, qty=plan.qty, forecast=10.0)

    def learn(self, demand):
        pass


@pytest.fixture(scope="module")
def trace():
    policy = FixedForecast()
    run = simulate_sku("TRACE", DEMAND, PARAMS, opening=25, policy=policy)
    return policy, run


def test_reviews_match_hand_trace(trace):
    policy, _ = trace
    assert policy.reviews == [
        (25.0, "ORDER", 20, 35.698),   # gap 10.7 -> need 11, MOQ 20 binds; due day 2
        (33.0, "ORDER", 20, 35.698),   # 13 on hand + 20 on order; need 3, MOQ binds; due day 3
        (37.0, "HOLD", 0, 35.698),     # 20 received; 20 on order; 3 backordered
        (23.0, "ORDER", 20, 35.698),   # due day 5
        (32.0, "ORDER", 20, 35.698),   # 12 + 20 on order; due day 6 (after the horizon)
        (44.0, "HOLD", 0, 35.698),
    ]


def test_ledger_matches_hand_trace(trace):
    _, run = trace
    g = run.ledger
    assert g["received"].tolist() == [0, 0, 20, 20, 0, 20]
    assert g["filled"].tolist() == [12, 13, 14, 11, 8, 10]
    assert g["short"].tolist() == [0, 3, 0, 0, 0, 0]
    assert g["backorders"].tolist() == [0, 3, 0, 0, 0, 0]
    assert g["on_hand_end"].tolist() == [13, 0, 3, 12, 4, 14]
    assert g["on_order_end"].tolist() == [20, 40, 20, 20, 40, 20]


def test_costs_and_metrics_match_hand_trace(trace):
    _, run = trace
    m = sku_metrics(run)
    assert m["holding_cost"] == pytest.approx(4.60)       # 0.1 * (13 + 0 + 3 + 12 + 4 + 14)
    assert m["stockout_cost"] == pytest.approx(6.00)      # 3 units short, $2 each, charged once
    assert m["relevant_cost"] == pytest.approx(10.60)
    assert m["purchase_spend"] == pytest.approx(300.0)    # 60 units received at $5
    assert m["fill_rate"] == pytest.approx(68 / 71)
    assert m["stockout_days"] == 1
    assert m["pos"] == 4
    assert np.isclose(m["on_order_end"], 20)
