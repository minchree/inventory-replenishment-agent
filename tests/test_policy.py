import math

import numpy as np
import pytest

from replenish.agent import StaticReorderPolicy
from replenish.data import SkuParams
from replenish.datagen import SKUS
from replenish.policy import (economic_csl, expected_shortage, normal_loss, norm_cdf, plan_order,
                              predicted_fill_rate, z_value)


def params(sku):
    spec = SKUS[sku]
    return SkuParams(sku, spec["unit_cost"], spec["holding_cost_per_day"], spec["stockout_cost"],
                     spec["lead_time_days"], spec["min_order_qty"], spec["service_level"])


def test_normal_functions_match_scipy():
    stats = pytest.importorskip("scipy.stats")
    for k in (-2.0, -0.5, 0.0, 0.7, 1.739, 2.5):
        assert norm_cdf(k) == pytest.approx(stats.norm.cdf(k), abs=1e-12)
        expected = stats.norm.pdf(k) - k * (1 - stats.norm.cdf(k))
        assert normal_loss(k) == pytest.approx(expected, abs=1e-12)
    assert z_value(0.95) == pytest.approx(stats.norm.ppf(0.95), abs=1e-9)


def test_normal_loss_at_zero_is_pdf_at_zero():
    assert normal_loss(0.0) == pytest.approx(1 / math.sqrt(2 * math.pi))


def test_expected_shortage_with_no_uncertainty_is_plain_gap():
    assert expected_shortage(ip=10, mu=14, sigma=0) == 4
    assert expected_shortage(ip=20, mu=14, sigma=0) == 0


def test_hold_example_from_brief():
    plan = plan_order(ip=212, level=40, sigma1=8, params=params("SKU-A"))
    assert plan.action == "HOLD"
    assert plan.S == pytest.approx(186.32, abs=0.01)


def test_order_example_from_brief_cost_says_wait_but_floor_says_order():
    plan = plan_order(ip=146, level=14.75, sigma1=16.1 / math.sqrt(8), params=params("SKU-B"))
    assert plan.action == "ORDER" and plan.qty == 120 and plan.moq_binds
    assert plan.S == pytest.approx(151.06, abs=0.01)
    assert plan.d_es == pytest.approx(0.2574, abs=1e-4)
    assert plan.wait_cost == pytest.approx(6.44, abs=0.01)
    assert plan.hold_saved == pytest.approx(12.00)
    assert plan.wait_cost < plan.hold_saved
    assert plan.csl_wait == pytest.approx(0.959, abs=5e-4) and plan.csl_wait < plan.floor


def test_defer_example_from_brief():
    plan = plan_order(ip=25, level=1.225, sigma1=1.95, params=params("SKU-C"))
    assert plan.action == "DEFER" and plan.qty == 0
    assert plan.S == pytest.approx(26.76, abs=0.01)
    assert plan.wait_cost == pytest.approx(2.12, abs=0.01)
    assert plan.hold_saved == pytest.approx(9.60)
    assert plan.csl_wait == pytest.approx(0.9626, abs=1e-3)


def test_defer_switched_off_orders_instead():
    plan = plan_order(ip=25, level=1.225, sigma1=1.95, params=params("SKU-C"), defer=False)
    assert plan.action == "ORDER" and plan.qty == 24


def test_order_quantity_is_gap_when_gap_exceeds_moq():
    plan = plan_order(ip=0, level=40, sigma1=8, params=params("SKU-A"), defer=False)
    assert plan.qty == math.ceil(plan.S) and plan.qty > 60 and not plan.moq_binds


def test_economic_csl_matches_brief_table():
    assert economic_csl(params("SKU-A"), mean_demand=40, mean_order=60)[0] == pytest.approx(0.98)
    assert economic_csl(params("SKU-B"), mean_demand=16, mean_order=120)[0] == pytest.approx(0.97)
    assert economic_csl(params("SKU-C"), mean_demand=1.225, mean_order=24)[0] == pytest.approx(0.804, abs=1e-3)


def test_over_ordering_guardrail_caps_an_order_at_30_days_of_forecast():
    # a broken sigma (bad data) would otherwise ask for 600+ units of a SKU selling 10 a day
    plan = plan_order(ip=0, level=10, sigma1=200, params=params("SKU-A"), defer=False)
    assert plan.action == "ORDER" and plan.capped and plan.qty == 300


def test_guardrail_never_cuts_an_order_below_the_moq():
    # 30 days at 0.5/day is 15 units, below the MOQ of 24: the cap binds but the MOQ wins
    plan = plan_order(ip=0, level=0.5, sigma1=5, params=params("SKU-C"), defer=False)
    assert plan.capped and plan.qty == 24


def test_alpha_can_be_fixed_instead_of_chosen():
    from replenish.agent import ReplenishmentAgent
    history = np.random.default_rng(0).normal(20, 3, 28)
    assert ReplenishmentAgent("X", params("SKU-A"), history, alpha=0.3).forecaster.alpha == 0.3
    assert ReplenishmentAgent("X", params("SKU-A"), history).forecaster.alpha in (0.1, 0.2, 0.3, 0.4, 0.5)


def test_static_policy_eoq_is_capped_when_holding_cost_is_near_zero():
    # found by hypothesis: sqrt(2*K*mu/h) overflows to infinity for h ~ 1e-311
    p = SkuParams("X", 1.0, 2.2e-311, 0.0, 1, 1, 0.75)
    policy = StaticReorderPolicy("X", p, np.full(28, 10.0), order_cost=25.0)
    assert policy.q == 3650


def test_predicted_fill_rate_is_below_one_and_rises_with_order_size():
    small = predicted_fill_rate(sigma_P=16, z=1.645, mean_order=60)
    big = predicted_fill_rate(sigma_P=16, z=1.645, mean_order=600)
    assert 0 < small < big < 1
