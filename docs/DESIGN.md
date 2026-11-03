# Design

The brief (`docs/BRIEF.md`) fixes the conventions. This file records how they were implemented, the choices the brief left open, where the implementation departs from the brief and why, and the hand-worked trace that became the first test.

## One simulated day

Each SKU is simulated on its own, day by day, in this order:

1. POs due today arrive (each was placed on day t-L).
2. The agent reviews. It sees on-hand, on-order and backorders and computes inventory position IP = on_hand + on_order - backorders. Its forecast has been updated with demand through day t-1 only. Any PO it places is due on day t+L.
3. Demand arrives. Backorders are served first, then today's demand. Units that can't be served are short.
4. Costs are booked: holding on end-of-day on-hand, the stockout cost once per unit short, and K per PO placed.

Because the review happens before demand and a PO placed today lands on day t+L, today's IP has to cover demand on days t through t+L until tomorrow's order can arrive. That is L+1 days, so the protection interval is P = L + R with R = 1.

`opening_stock` is on-hand at the start of the first simulated day (day 28), with nothing on order.

## Costs

- `stockout_cost` is charged once per unit short, on the day it goes short. The starter charged it again every day a unit stayed backordered (H6 in the audit).
- `holding_cost_per_day` is charged per unit of end-of-day on-hand.
- K, the fixed cost per PO, is 0 for the headline run. `evaluate` also reports K = 25.
- Policies are compared on relevant cost = holding + stockout + ordering. Purchase spend and ending-inventory value are reported next to it, so a policy can't look cheap by ending the run with an empty shelf.
- Backorders are the default. `--shortage lost_sales` switches to lost sales.

## Forecast and error

- Warm-up is days 0 to 27. The EWMA level starts at the mean of the first week, then runs through days 7 to 27. This departs slightly from the brief, which says to start at the warm-up mean. Starting from the first week keeps every warm-up error out-of-sample, since no error is measured against a level that already saw that day.
- alpha is chosen from {0.1, 0.2, 0.3, 0.4, 0.5} by the lowest one-step MSE over those 21 warm-up days. Ties go to the smaller alpha. All three SKUs pick 0.1.
- sigma_1 is the RMSE of the trailing 28 one-step errors, floored at max(0.5, 10% of the forecast). Without the floor, a run of calm days would shrink safety stock toward zero.
- mu_P = F * P and sigma_P = sigma_1 * sqrt(P). The sqrt(P) scaling assumes errors are independent from day to day.
- Each SKU is classified on its warm-up history by ADI and CV^2 of nonzero demand (Syntetos-Boylan cut-offs 1.32 and 0.49). SKU-A and SKU-B are smooth; SKU-C is intermittent.

## Decision

- z = inverse normal CDF of `service_level`, read as cycle service level. SS = z * sigma_P and S = mu_P + SS.
- IP >= S: HOLD.
- IP < S: the candidate order is Q = max(min_order_qty, ceil(S - IP)). Before ordering, the agent prices waiting one day:
  - CSL_wait = Phi((IP - mu_P) / sigma_P) is the cycle service level it would accept by waiting.
  - dES = sigma_P * G((IP - mu_P)/sigma_P) - sigma_L * G((IP - mu_L)/sigma_L), with G the standard normal loss function, is the expected number of extra units short on day t+L. That is the one day today's order covers and tomorrow's would not.
  - DEFER when stockout_cost * dES < holding_cost_per_day * Q and CSL_wait >= service_level - 0.02. Otherwise ORDER Q.
- Over-ordering guardrail, added for the rubric: no single PO exceeds 30 days of forecast demand unless the MOQ alone requires it (`MAX_COVER_DAYS`). On the committed data and every Monte Carlo path it never binds, and all results are identical with and without it. It is there for a bad data point or a broken forecast, and the log says when it trims an order.
- alpha is chosen on the warm-up by default. `ReplenishmentAgent(alpha=...)`, `python -m replenish run --alpha 0.3` and the `ALPHA` constant in the notebook fix it instead.
- The defer tolerance (0.02) was left open by the brief. Two points of cycle service level is the most the agent may give up for one day of holding cost.
- Cost check, report-only: CSL* = 1 - h * T / p, where T = max(R, mean order / mean demand) is the order-cycle length in days. One more unit of S is carried for the whole cycle and avoids a unit short with probability P(stockout in the cycle). The diagnostic never changes `service_level`.

## Reflect step

The brief asked for an ALERT when |tracking signal| > 4, with alpha raised to 0.5 until |TS| < 2 for 7 days. Two changes came out of the ablations below. Both are in the code and tested.

1. The alarm threshold is calibrated instead of fixed. EWMA updates as F_{t+1} = F_t + alpha * e_t, so the sum of the last n errors equals (F_end - F_start) / alpha. For an unbiased forecast on i.i.d. demand, that gives sd(TS) = sqrt(pi * (1 - (1-alpha)^n) / (2 * alpha)). With alpha = 0.1 and n = 28 this is about 3.9, so a fixed limit of 4 fires on pure noise roughly a third of the time. The agent now raises an ALERT when |TS| exceeds 3 sd of that no-bias distribution (11.6 at alpha = 0.1) and stands down after |TS| stays within 1 sd for 7 days. `test_tracking_signal_sd_matches_simulation_of_an_unbiased_forecast` checks the formula against simulation.
2. Reflect is off for intermittent and lumpy demand. Most of SKU-C's errors are zero-demand days, so its tracking signal measures sparsity, not bias.

### Iterations (dev seeds 1000-1199)

Every change was judged on the 200 dev seeds, and the reported results use the held-out seeds 5000-5199, which played no part in any choice. Differences are P3 full agent minus the named policy, in mean relevant cost per path, all SKUs, with the share of paths where P3 was cheaper.

| version | vs P2 textbook | vs P3 without reflect | vs P3 without defer |
|---|---|---|---|
| v1: fixed +/-4 alarm, reflect on every SKU | +$518 (9%) | +$461 (12%) | +$77 (62%) |
| v2: reflect off for intermittent; alarm needs 5 of last 7 errors with the same sign | +$106 (42%) | +$49 (32%) | +$74 (62%) |
| v3: calibrated 3-sd alarm (persistence rule dropped) | +$87 (50%) | +$30 (32%) | +$71 (62%) |

The full tables are in `docs/iterations/`. v3 is the frozen design. Tuning further on the same seeds would fit the agent to those seeds, so the defer rule stays as the brief specified, even though it loses money on SKU-B (see the README).

## Data

`replenish/datagen.py` writes 120 days for three SKUs from seed 7. `sales.csv` is at order-line grain: each SKU-day is split into 1 to 4 rows, and days without demand have no rows, so the T1 aggregation has real work to do.

| SKU | archetype | demand | h/day | p | L | MOQ | SL | opening |
|---|---|---|---|---|---|---|---|---|
| SKU-A | fast mover | ~40/day, weekly +/-25%, sd 6 | 0.02 | 1.50 | 3 | 60 | 0.95 | 200 |
| SKU-B | trend + promos | 12 to 20/day, 6 promo days at 2.5x in the simulated window, sd 3 | 0.10 | 25.00 | 7 | 120 | 0.98 | 90 |
| SKU-C | intermittent | demand on 35% of days, size 1 to 6 | 0.40 | 40.00 | 10 | 24 | 0.98 | 30 |

Cost rates are scaled up from real-world levels so holding and stockouts trade off within 92 days. Historical sales are treated as unconstrained demand. SKU-B opens below S, so the log reacts on day 1. Its 90 units of opening stock barely cover the first 7-day lead time (about 91 units of expected demand), so on some demand paths it stocks out in week one whatever the policy does. That is why even the clairvoyant policy averages a little over one stockout day across the test seeds.

## Metrics

- Fill rate: units filled from stock on the day they were demanded, divided by total demand.
- Achieved CSL: share of replenishment cycles (one arrival to the next) with no stockout. The stretch before the first arrival depends only on opening stock and isn't counted.
- Stockout days: days with any unit short.
- Forecast MAE and bias use the forecast the agent held at each review.

## Hand-worked trace

`tests/test_hand_trace.py` pins this to the cent. L = 2, MOQ = 20, SL = 0.95, h = 0.10, p = 2.00, unit cost 5, opening stock 25, defer off. The forecast is fixed at 10/day with sigma_1 = 2, so S = 10 * 3 + 1.6449 * 2 * sqrt(3) = 35.698.

| day | received | on hand at review | on order | backorders | IP | decision | demand | filled | short | end on hand | holding | stockout |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 25 | 0 | 0 | 25 | ORDER 20 (need 11, MOQ binds), due day 2 | 12 | 12 | 0 | 13 | 1.30 | 0 |
| 1 | 0 | 13 | 20 | 0 | 33 | ORDER 20 (need 3, MOQ binds), due day 3 | 16 | 13 | 3 | 0 | 0.00 | 6.00 |
| 2 | 20 | 20 | 20 | 3 | 37 | HOLD | 14 | 14 | 0 | 3 | 0.30 | 0 |
| 3 | 20 | 23 | 0 | 0 | 23 | ORDER 20 (need 13), due day 5 | 11 | 11 | 0 | 12 | 1.20 | 0 |
| 4 | 0 | 12 | 20 | 0 | 32 | ORDER 20 (need 4, MOQ binds), due day 6 | 8 | 8 | 0 | 4 | 0.40 | 0 |
| 5 | 20 | 24 | 20 | 0 | 44 | HOLD | 10 | 10 | 0 | 14 | 1.40 | 0 |

On day 2 the 20 units that arrive first clear the 3 backordered units, leaving 17 for that day's demand of 14. Totals: holding $4.60, stockout $6.00, relevant cost $10.60, fill rate 68/71 = 0.958, one stockout day, 4 POs, 60 units received ($300 of purchases) and 20 still on order.
