# Questions a grader might ask

Each answer points at the file that backs it. Numbers come from `outputs/metrics.json` (held-out seeds 5000-5199) unless noted.

## 1. Why does safety stock come from forecast error instead of the spread of demand?

Safety stock covers what the forecast can't predict. If demand follows a trend or a weekly pattern and the forecast tracks it, that part of the variation is already in mu_P, and counting it again in sigma double-protects. `ReplenishmentAgent.sigma1` uses the RMSE of out-of-sample one-step errors over the last 28 days (`replenish/forecast.py`, `ErrorTracker`). `test_h3_a_forecastable_series_gets_less_safety_stock` shows the difference: a ramp and a shuffled copy have identical standard deviations, the starter gives them the same safety stock, and our agent gives the ramp less than half.

## 2. Why is the protection interval L + 1 and not L?

The agent reviews at the start of the day, before demand, and a PO placed today arrives on day t+L. If it doesn't order today, the next chance is tomorrow, and that order lands on t+L+1. So today's inventory position has to cover days t through t+L, which is L+1 days. `docs/DESIGN.md` walks through the event order, and `test_h7_known_constant_demand_never_stocks_out_once_orders_can_land` shows the starter's L-day reorder point stocking out even when demand is constant and known exactly.

## 3. The service level for SKU-B is 0.98. Why is its fill rate only 0.960 on the committed data?

Cycle service level and fill rate measure different things. CSL is the chance that a replenishment cycle has no stockout at all. Fill rate is the share of units served from the shelf. The normal model predicts a fill rate of 0.999 for SKU-B's target, but SKU-B has promo days at 2.5 times normal demand, which the normal model doesn't expect. On the committed data (`outputs/ledger.csv`), five of its six stockout days fall on a promo day or within three days after one (the 45-unit days on 03-13, 03-17 and 04-14). The sixth, on 03-08, followed a deferral (question 4). The notebook prints predicted and achieved fill side by side for each SKU.

## 4. When does deferring an order lower cost?

When the minimum order quantity forces a large order to cover a small gap. Waiting a day saves holding cost on the whole order (h times Q) and risks the extra units short on day t+L, priced as p times dES (`replenish/policy.py`, `plan_order`). Across the test seeds, defer saves $56 per path on SKU-C, where an order of 24 covers about 15 days, and is cheaper on 82% of paths. On SKU-B it costs $139 per path on average. The log has a concrete case: on 2025-03-01 SKU-B deferred because the model priced waiting at $2.28 against $12 of holding saved. The order placed the next day arrived one day after a 4-unit stockout on 2025-03-08, which cost $100. Three days after the deferral, the tracking signal showed the forecast had been running low, so the normal model understated the risk.

## 5. What does the tracking signal do, and why 3 standard deviations instead of the textbook +/-4?

TS is the sum of the last 28 forecast errors divided by their mean absolute deviation. A large positive value means demand keeps beating the forecast. For EWMA, the sum of n errors telescopes to (F_end - F_start) / alpha, so for an unbiased forecast sd(TS) = sqrt(pi * (1 - (1-alpha)^n) / (2 * alpha)), about 3.9 for alpha = 0.1 and n = 28. A fixed limit of 4 sits about one standard deviation out and fires on noise about a third of the time. In the first version it raised 11 ALERTs on the committed data and cost $461 per path on the dev seeds. The agent now alerts beyond 3 sd (11.6 here). `test_tracking_signal_sd_matches_simulation_of_an_unbiased_forecast` checks the formula against simulation, and `docs/DESIGN.md` has the iteration table.

## 6. Why is the reflect step switched off for SKU-C?

SKU-C had demand on only 6 of its 28 warm-up days, so the Syntetos-Boylan check classifies it as intermittent (ADI 4.67 against the 1.32 cut-off). Most of its forecast errors are the zero days themselves, so the tracking signal measures how sparse demand is, not whether the forecast is biased. When reflect ran on SKU-C in the first version, it pushed alpha to 0.5 and the forecast chased single days.

## 7. What is CSL*, and why doesn't the agent just use it?

CSL* = 1 - h*T/p is the service level the cost parameters imply, where T is the order-cycle length in days (`economic_csl`). It comes from marginal analysis: one more unit of S is held for the whole cycle and avoids one unit short with probability P(stockout in the cycle). In the service-level sweep (`outputs/sl_sweep.csv`) it picked SKU-A's cheapest level exactly (0.98) and pointed the right way for SKU-C (0.85, cheapest at 0.80). It was wrong for SKU-B (0.97, cheapest 0.995) because of the promo tail. It stays a report-only diagnostic because a service level often encodes things the cost columns don't, such as a customer contract, and because the assignment defines `service_level` as an input.

## 8. How do you know nothing in the decisions looks at future demand?

Three ways. The simulator calls `decide` before the day's demand and `learn` after it (`replenish/sim.py`). The property test `test_no_leakage_changing_demand_from_day_t_leaves_decisions_through_day_t_unchanged` changes the demand from day t onward on 200 random paths and checks that every decision record through day t is identical. And `test_h1` and `test_h2` show that the starter's RandomForest features and `tool_forecast` both fail this property.

## 9. Why compare policies on relevant cost instead of total spend?

Every policy buys roughly the same units over the run, so purchase spend mostly reflects timing: a policy that ends with an empty shelf has bought less. Relevant cost (holding + stockout + ordering) is what the policy controls. Purchase spend and ending inventory value are still reported in `outputs/policy_comparison.csv`, so the difference is visible.

## 10. Your full agent doesn't beat the textbook EWMA agent. Isn't that a problem?

Across the 200 held-out paths, P3 costs $130 more than P2 on average, with a 5th-95th percentile range of -$312 to +$870, and is cheaper on 48% of paths. That is a tie, and the README says so. The ablations show where each feature helps and hurts: defer pays on the intermittent, high-MOQ SKU and loses on the promo SKU, and reflect is silent on SKU-A and costs $89 per path on SKU-B. Both features were designed on separate dev seeds (1000-1199) and frozen before the test run, so the numbers aren't tuned to the seeds they're reported on. The full agent does beat the starter's policy by $10,825 per path and the naive-forecast agent by $1,291 per path (cheaper on 100% and 96% of paths).
