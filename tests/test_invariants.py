"""Properties that must hold for every policy on any demand path (docs/BRIEF.md 4.7)."""

import numpy as np
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from replenish.config import WARMUP_DAYS
from replenish.data import SkuParams
from replenish.evaluate import ABLATIONS, POLICIES, run_sku, sku_metrics
from replenish.sim import SimConfig

ALL = {**POLICIES, **ABLATIONS}
SETTINGS = settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@st.composite
def scenarios(draw, policies=tuple(ALL)):
    params = SkuParams(
        "X", unit_cost=draw(st.floats(0.5, 100)), holding_cost_per_day=draw(st.floats(0, 1)),
        stockout_cost=draw(st.floats(0, 50)), lead_time_days=draw(st.integers(1, 10)),
        min_order_qty=draw(st.integers(1, 80)), service_level=draw(st.floats(0.6, 0.995)))
    history = draw(st.lists(st.integers(0, 60), min_size=WARMUP_DAYS, max_size=WARMUP_DAYS))
    future = draw(st.lists(st.integers(0, 60), min_size=5, max_size=45))
    return dict(params=params, series=np.array(history + future, float), opening=draw(st.integers(0, 300)),
                policy=draw(st.sampled_from(policies)),
                config=SimConfig(order_cost=draw(st.sampled_from([0.0, 25.0])),
                                 shortage=draw(st.sampled_from(["backorder", "lost_sales"]))))


def simulate(s):
    return run_sku("X", s["series"], s["params"], s["opening"], ALL[s["policy"]], config=s["config"])


@SETTINGS
@given(scenarios())
def test_ledger_balances_every_day(s):
    g = simulate(s).ledger
    assert np.allclose(g["on_hand_end"], g["on_hand_start"] + g["received"] - g["shipped"])
    assert np.allclose(g["filled"] + g["short"], g["demand"])
    assert (g["on_hand_end"] >= 0).all() and (g["filled"] >= 0).all()
    cleared = g["shipped"] - g["filled"]
    prev = np.r_[0.0, g["backorders"][:-1]]
    if s["config"].shortage == "backorder":
        assert np.allclose(g["backorders"], prev - cleared + g["short"])
    else:
        assert (g["backorders"] == 0).all() and (cleared == 0).all()


@SETTINGS
@given(scenarios())
def test_every_po_arrives_exactly_lead_time_later_and_nothing_else_arrives(s):
    g = simulate(s).ledger
    L, H = s["params"].lead_time_days, len(g["day"])
    expected = np.zeros(H)
    for t in np.flatnonzero(g["ordered"] > 0):
        if t + L < H:
            expected[t + L] += g["ordered"][t]
    assert np.array_equal(g["received"], expected)
    on_order = np.array([g["ordered"][max(0, t - L + 1): t + 1].sum() for t in range(H)])
    assert np.array_equal(g["on_order_end"], on_order)


@SETTINGS
@given(scenarios())
def test_every_po_respects_moq(s):
    ordered = simulate(s).ledger["ordered"]
    assert (ordered[ordered > 0] >= s["params"].min_order_qty).all()


@SETTINGS
@given(scenarios())
def test_costs_recompute_from_the_ledger(s):
    run = simulate(s)
    g, p, K = run.ledger, s["params"], s["config"].order_cost
    m = sku_metrics(run)
    assert np.isclose(m["holding_cost"], p.holding_cost_per_day * g["on_hand_end"].sum())
    assert np.isclose(m["stockout_cost"], p.stockout_cost * g["short"].sum())
    assert np.isclose(m["order_cost"], K * (g["ordered"] > 0).sum())
    assert np.isclose(m["purchase_spend"], p.unit_cost * g["received"].sum())
    assert 0.0 <= m["fill_rate"] <= 1.0


@SETTINGS
@given(scenarios(policies=("P1 naive agent", "P2 EWMA textbook", "P3 full agent", "P0 starter (s,Q)")),
       st.data())
def test_no_leakage_changing_demand_from_day_t_leaves_decisions_through_day_t_unchanged(s, data):
    base = simulate(s)
    future_len = len(s["series"]) - WARMUP_DAYS
    t = data.draw(st.integers(0, future_len - 1))
    altered = s["series"].copy()
    altered[WARMUP_DAYS + t:] = data.draw(st.permutations(list(altered[WARMUP_DAYS + t:])))
    altered[WARMUP_DAYS + t] += data.draw(st.integers(1, 50))
    other = simulate({**s, "series": altered})
    assert [repr(r) for r in base.decisions[: t + 1]] == [repr(r) for r in other.decisions[: t + 1]]


@SETTINGS
@given(scenarios(policies=("P4 clairvoyant",)))
def test_clairvoyant_never_stocks_out_once_its_first_order_can_land(s):
    g = simulate(s).ledger
    L = s["params"].lead_time_days
    assert (g["short"][L:] == 0).all()
