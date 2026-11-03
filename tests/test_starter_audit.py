"""Starter audit (docs/STARTER_AUDIT.md). Each hypothesis is a property that a sound replenishment agent has.

Every test runs twice: on the faithful port of the starter (expected to fail, so it's a strict xfail and
the suite goes red if the starter ever passes) and on our implementation (must pass).
"""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from baselines.starter_port import (StarterAgent, StarterInventorySim, run_starter_baseline, starter_demand,
                                    starter_eoq, starter_features, starter_static_rop, starter_tool_forecast)
from replenish.agent import ReplenishmentAgent
from replenish.config import REVIEW_PERIOD, WARMUP_DAYS
from replenish.data import SkuParams
from replenish.evaluate import POLICIES, run_sku, sku_metrics
from replenish.policy import plan_order, z_value
from replenish.sim import simulate_sku


def both(reason):
    return ["ours", pytest.param("starter", marks=pytest.mark.xfail(strict=True, reason=reason))]


PARAMS = SkuParams("X", unit_cost=1.0, holding_cost_per_day=0.2, stockout_cost=3.0,
                   lead_time_days=7, min_order_qty=1, service_level=0.95)


class NeverOrders:
    def decide(self, obs):
        return SimpleNamespace(action="HOLD", qty=0, forecast=0.0)

    def learn(self, demand):
        pass


class KnownDemand:
    """Our decision rule with the forecast known exactly (sigma = 0)."""

    def __init__(self, params, level):
        self.params, self.level = params, level

    def decide(self, obs):
        plan = plan_order(obs.ip, self.level, 0.0, self.params, defer=False)
        return SimpleNamespace(action=plan.action, qty=plan.qty, forecast=self.level)

    def learn(self, demand):
        pass


def test_port_reproduces_the_starter_kpis():
    df = starter_demand()
    rop, mu, _ = starter_static_rop(df[df.split == "train"].demand)
    assert rop == pytest.approx(154.64017658908963)
    q = starter_eoq(mu)
    assert q == pytest.approx(214.19411961844534)
    kpi = run_starter_baseline(df[df.split == "test"].demand.to_numpy(), rop, q).kpis()
    assert kpi["fill_rate"] == pytest.approx(0.9480356502240941)
    assert kpi["total_cost"] == pytest.approx(22159.830022202197)


@pytest.mark.parametrize("impl", both("H1: ma7 = rolling(7).mean() includes the same day's demand"))
def test_h1_the_forecast_for_day_t_does_not_see_day_t(impl):
    series = np.arange(WARMUP_DAYS + 20, dtype=float)
    t = WARMUP_DAYS + 10
    bumped = series.copy()
    bumped[t] += 100
    if impl == "starter":
        a = starter_features(pd.Series(series)).drop(columns="demand").iloc[t]
        b = starter_features(pd.Series(bumped)).drop(columns="demand").iloc[t]
        assert a.equals(b)
    else:
        spec = POLICIES["P3 full agent"]
        a = run_sku("X", series, PARAMS, 50, spec).decisions[t - WARMUP_DAYS]
        b = run_sku("X", bumped, PARAMS, 50, spec).decisions[t - WARMUP_DAYS]
        assert repr(a) == repr(b)


@pytest.mark.parametrize("impl", both("H2: tool_forecast averages predictions for days i..i+L-1, built from later actuals"))
def test_h2_todays_decision_ignores_demand_after_today(impl):
    rng = np.random.default_rng(1)
    series = rng.integers(5, 25, WARMUP_DAYS + 30).astype(float)
    i = 12                               # index into the simulated window
    later = series.copy()
    later[WARMUP_DAYS + i + 3] += 200    # three days after the review
    if impl == "starter":
        def forecast_dl(s):
            sim = pd.Series(s[WARMUP_DAYS:])
            preds = starter_features(sim)[["lag1", "ma7"]].mean(axis=1)   # stand-in for the RandomForest
            return starter_tool_forecast(i, 7, preds, default_mu=10.0)
        assert forecast_dl(series) == forecast_dl(later)
    else:
        spec = POLICIES["P3 full agent"]
        a = run_sku("X", series, PARAMS, 50, spec).decisions[i]
        b = run_sku("X", later, PARAMS, 50, spec).decisions[i]
        assert repr(a) == repr(b)


@pytest.mark.parametrize("impl", both("H3: safety stock uses the std of raw demand, not forecast error"))
def test_h3_a_forecastable_series_gets_less_safety_stock(impl):
    rng = np.random.default_rng(2)
    ramp = np.linspace(10, 40, WARMUP_DAYS) + rng.normal(0, 1, WARMUP_DAYS)
    shuffled = rng.permutation(ramp)     # same values, same spread, no pattern to learn
    L, z = PARAMS.lead_time_days, z_value(PARAMS.service_level)
    if impl == "starter":
        ss = [starter_static_rop(h, L, PARAMS.service_level)[0] - L * np.mean(h) for h in (ramp, shuffled)]
    else:
        P = L + REVIEW_PERIOD
        ss = [z * ReplenishmentAgent("X", PARAMS, h, reflect=False).sigma1() * np.sqrt(P) for h in (ramp, shuffled)]
    assert ss[0] < 0.5 * ss[1]


@pytest.mark.parametrize("impl", both("H4: decide() triggers on the static global ROP; the forecast only sizes the order"))
def test_h4_a_much_higher_forecast_triggers_an_order(impl):
    if impl == "starter":
        agent = StarterAgent(ROP=100)
        low = agent.decide(on_hand=120, pipeline=0, backlog=0, forecast_DL=10)[0]
        high = agent.decide(on_hand=120, pipeline=0, backlog=0, forecast_DL=1000)[0]
        assert (low, high) == ("noop", "order_to_S")
    else:
        low = plan_order(120, level=10 / 8, sigma1=1, params=PARAMS).action
        high = plan_order(120, level=1000 / 8, sigma1=1, params=PARAMS).action
        assert (low, high) == ("HOLD", "ORDER")


@pytest.mark.parametrize("impl", both("H5: kpis() divides by the backlog level summed over days"))
def test_h5_fill_rate_is_units_filled_over_units_demanded(impl):
    demand = [10, 10, 10, 10, 10]        # empty shelf, nothing ordered: true fill rate is 0
    if impl == "starter":
        sim = StarterInventorySim(L=2, h=0.2, K=0.0, p=3.0, init_on_hand=0)
        for d in demand:
            sim.step(d)
        fill = sim.kpis()["fill_rate"]
    else:
        fill = sku_metrics(simulate_sku("X", demand, PARAMS, 0, NeverOrders()))["fill_rate"]
    assert fill == pytest.approx(0.0)


@pytest.mark.parametrize("impl", both("H6: cost_stockout += p * backlog every day the unit stays short"))
def test_h6_a_unit_short_costs_p_once(impl):
    demand = [1, 0, 0, 0, 0]
    if impl == "starter":
        sim = StarterInventorySim(L=2, h=0.2, K=0.0, p=3.0, init_on_hand=0)
        for d in demand:
            sim.step(d)
        cost = sim.cost_stockout
    else:
        cost = sku_metrics(simulate_sku("X", demand, PARAMS, 0, NeverOrders()))["stockout_cost"]
    assert cost == pytest.approx(3.0)


@pytest.mark.parametrize("impl", both("H7: ROP covers L days, but with daily review the exposure is L+1"))
def test_h7_known_constant_demand_never_stocks_out_once_orders_can_land(impl):
    L, d, opening = 2, 10, 21
    demand = [d] * 30
    if impl == "starter":
        rop = L * d                       # starter formula with sigma = 0
        sim = run_starter_baseline(demand, rop, q=30, L=L, K=0.0, init_on_hand=opening)
        backlog = np.array([s["backlog"] for s in sim.state_log])
        assert (backlog[L:] == 0).all()
    else:
        params = SkuParams("X", 1.0, 0.2, 3.0, lead_time_days=L, min_order_qty=30, service_level=0.95)
        run = simulate_sku("X", demand, params, opening, KnownDemand(params, d))
        assert (run.ledger["short"][L:] == 0).all()
