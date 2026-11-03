import numpy as np
import pandas as pd
import pytest

from replenish.config import INIT_DAYS
from replenish.data import SkuParams, aggregate_daily, load_dataset
from replenish.datagen import daily_demand, to_transactions, write_dataset
from replenish.forecast import (EWMA, ErrorTracker, classify_demand, make_forecaster, select_alpha,
                                tracking_signal_sd, warm_up)


def test_aggregate_sums_order_lines_and_fills_missing_days():
    sales = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-01", "2025-01-01", "2025-01-03", "2025-01-03"]),
        "sku": ["A", "A", "A", "B"],
        "qty_sold": [2, 3, 4, 1],
    })
    daily = aggregate_daily(sales, skus=["A", "B", "C"])
    assert list(daily.index.strftime("%Y-%m-%d")) == ["2025-01-01", "2025-01-02", "2025-01-03"]
    assert daily["A"].tolist() == [5, 0, 4]
    assert daily["B"].tolist() == [0, 0, 1]
    assert daily["C"].tolist() == [0, 0, 0]       # a SKU with no sales still gets a column


def test_transactions_round_trip_to_daily_demand():
    demand = daily_demand(seed=3, n_days=40)
    sales = to_transactions(demand, seed=3)
    assert (sales["qty_sold"] > 0).all()
    assert sales.groupby(["date", "sku"]).size().max() <= 4
    daily = aggregate_daily(sales.assign(date=pd.to_datetime(sales["date"])), skus=list(demand))
    for sku, series in demand.items():
        assert daily[sku].tolist() == series.tolist()


def test_load_dataset_from_written_csvs(tmp_path):
    write_dataset(tmp_path, seed=5)
    ds = load_dataset(tmp_path)
    assert ds.skus == ["SKU-A", "SKU-B", "SKU-C"]
    assert len(ds.demand) == 120
    assert ds.opening["SKU-B"] == 90


@pytest.mark.parametrize("field,value", [("lead_time_days", 0), ("min_order_qty", 0), ("service_level", 1.0)])
def test_params_validation(field, value):
    good = dict(sku="X", unit_cost=1.0, holding_cost_per_day=0.1, stockout_cost=1.0,
                lead_time_days=2, min_order_qty=1, service_level=0.9)
    with pytest.raises(ValueError):
        SkuParams(**{**good, field: value})


def test_ewma_update():
    f = EWMA(alpha=0.2, level=10)
    f.update(20)
    assert f.level == pytest.approx(12.0)


def test_warm_up_errors_are_one_step_ahead():
    history = np.array([10] * INIT_DAYS + [20, 20])
    f = make_forecaster("ewma", history, alpha=0.5)
    assert warm_up(f, history) == [10.0, 5.0]       # forecast 10 then 15, each read before the demand


def test_select_alpha_picks_lowest_mse():
    rng = np.random.default_rng(0)
    history = np.r_[np.full(14, 10.0), np.full(14, 30.0)] + rng.normal(0, 0.5, 28)
    alpha, mse = select_alpha(history)
    assert alpha == min(mse, key=mse.get)
    assert alpha == 0.5                              # a level shift favours the fastest alpha


def test_tracking_signal_sign_and_scale():
    tr = ErrorTracker([2, 2, 2, 2])
    assert tr.tracking_signal() == pytest.approx(4.0)
    assert ErrorTracker([1, -1, 1, -1]).tracking_signal() == pytest.approx(0.0)


@pytest.mark.parametrize("alpha", [0.1, 0.3, 0.5])
def test_tracking_signal_sd_matches_simulation_of_an_unbiased_forecast(alpha):
    rng = np.random.default_rng(42)
    signals = []
    for _ in range(400):
        f = EWMA(alpha, 50.0)
        tr = ErrorTracker()
        for d in rng.normal(50, 5, 200):        # long burn-in so the window sees a settled forecast
            tr.add(d - f.level)
            f.update(d)
        signals.append(tr.tracking_signal())
    assert np.std(signals) == pytest.approx(tracking_signal_sd(alpha, 28), rel=0.15)


def test_classify_demand():
    assert classify_demand(np.full(28, 40.0)).label == "smooth"
    sparse = np.array([0, 0, 3, 0, 0, 0, 4, 0, 0, 3] * 3, float)
    assert classify_demand(sparse).label == "intermittent"
    assert classify_demand(np.zeros(10)).label == "no demand"
