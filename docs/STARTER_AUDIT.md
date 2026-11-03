# Starter audit

The course starter notebook (`starter/InventoryReplenishmentAgent.ipynb`, from myrah/AAI2025) was run unchanged first. Its saved outputs reproduce exactly: the baseline (s,Q) costs 22,159.83 at fill rate 0.948, and the "agentic" policy costs 22,535.83 at 0.950, so the starter's own agent loses to its baseline.

`baselines/starter_port.py` ports the starter's logic line for line, apart from two substitutions: plain arguments replace pydantic's `Obs`, and `statistics.NormalDist` replaces scipy's `norm.ppf`. `test_port_reproduces_the_starter_kpis` checks that the port gives the same ROP, EOQ and KPI table as the notebook.

Each hypothesis below became a property that a sound agent should have. `tests/test_starter_audit.py` runs every property twice: on the port, where it is a strict xfail (the suite fails if the starter ever passes), and on our code, where it must pass. All seven were confirmed. None were dropped.

| | defect in the starter | evidence test | fix in this repo |
|---|---|---|---|
| H1 | `feat['ma7'] = feat['demand'].rolling(7).mean()` includes the same day's demand, so the RandomForest feature for day t contains its own target. | `test_h1_the_forecast_for_day_t_does_not_see_day_t`: bumping demand on day t changes the starter's features for day t. | The forecast used at day t's review is updated only through day t-1 (`ReplenishmentAgent.learn` runs after demand). |
| H2 | `tool_forecast(i, L, series_pred)` averages predictions for days i to i+L-1, and each prediction was built from actuals up to its own day, so decisions use future demand. | `test_h2_todays_decision_ignores_demand_after_today`: changing demand three days ahead changes the starter's forecast_DL. A stand-in predictor on the same features replaces the RandomForest. | Flat EWMA forecast from the current level; the property test `test_no_leakage...` checks this on random paths for every policy. |
| H3 | Safety stock uses `train['demand'].std()`, which is demand variability (trend and weekly pattern included), not forecast error. The residual sigma in the next cell is in-sample. | `test_h3_a_forecastable_series_gets_less_safety_stock`: a ramp and a shuffled copy of it have the same std, so the starter gives them identical safety stock. Ours gives the ramp less than half. | sigma_1 = RMSE of out-of-sample one-step errors over the trailing 28 days. |
| H4 | `ROP_dyn` is computed, but `ReplenishmentAgent.decide` triggers on the static global `ROP`. The forecast only sizes the order. | `test_h4_a_much_higher_forecast_triggers_an_order`: a 100x larger forecast at the same IP still returns `noop`. | S = mu_P + SS is recomputed from the forecast at every review, and the trigger is IP < S. |
| H5 | `kpis()` divides by sum(sales + backlog), where backlog is a daily level, so a unit backordered for 5 days is counted 5 times. The numerator nets same-day clears against new shortages. | `test_h5_fill_rate_is_units_filled_over_units_demanded`: an empty shelf for 5 days has a true fill rate of 0; the starter reports 0.733. | Fill rate = units filled from stock on the day demanded / total demand. |
| H6 | `cost_stockout += p * backlog` runs every day, so the penalty is per unit per day, while the parameter is described as a penalty per unit short. | `test_h6_a_unit_short_costs_p_once`: one unit short for 5 days costs 5p in the starter. | Stockout cost is charged once per unit, on the day it goes short. |
| H7 | ROP covers L days of demand, but with daily review the order placed tomorrow lands one day later, so the exposure is L+1 days. | `test_h7_known_constant_demand_never_stocks_out_once_orders_can_land`: with constant, perfectly known demand and sigma = 0, the starter still stocks out. | Protection interval P = L + 1. |

## Before and after, on the starter's own data

Same data (rng seed 7, test window 2024-04-01 to 2025-06-30), same parameters (L = 7, CSL 0.95, K = 250 per PO, h = 0.2, p = 3, Q = EOQ = 214), one fix at a time. Produced by `baselines/audit.py`.

| version | fill rate | stockout days | holding | ordering | stockout | total |
|---|---|---|---|---|---|---|
| Starter as shipped (its own sim and KPIs) | 0.948 | | 9,301.29 | 11,000 | 1,858.54 | 22,159.83 |
| Same policy, metrics fixed (H5, H6) | 0.945 | 32 | 9,301.29 | 11,000 | 1,550.75 | 21,852.04 |
| + protection interval L+1 (H7) | 0.979 | 15 | 10,672.06 | 11,000 | 582.11 | 22,254.18 |
| Our textbook agent P2 (H1-H4, H7 fixed), MOQ = EOQ | 0.996 | 3 | 11,752.20 | 11,000 | 102.24 | 22,854.44 |
| Our full agent P3, MOQ = EOQ | 0.996 | 3 | 11,623.80 | 11,000 | 102.24 | 22,726.04 |

The fixes raise fill rate from 0.945 to 0.996 and cut stockout days from 32 to 3, and total cost goes up. The cost check explains why. With h = 0.2 per day, p = 3 per unit and orders of 214 units against mean demand of 20.5 a day, an order cycle lasts about 10.5 days, so CSL* = 1 - 0.2 * 10.5 / 3 = 0.30. At these costs, a 95% service target buys protection that costs more than the stockouts it prevents. The starter's per-day stockout charge hid this by inflating the stockout term. With honest accounting, the cheapest policy would carry very little safety stock, and the notebook shows the CSL* check that flags it.

H1 and H2 affect the starter's RandomForest agent, whose apparent forecast accuracy is inflated by the leak. Measuring that would mean re-running the RandomForest, which this repo doesn't depend on, so the table above covers H3 to H7.
