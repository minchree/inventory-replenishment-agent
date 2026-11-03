# Assignment checklist

Where each rubric line and checklist item lives. "Notebook" means `notebooks/InventoryReplenishmentAgent.ipynb`, run in Colab with Runtime > Run all.

## Rubric (30 points)

| rubric line | where it lives |
|---|---|
| Design clarity: agent role (what it optimizes, inputs, outputs) | `docs/DESIGN_DOCUMENT.md` (Goal, Inputs and outputs); shown in the notebook after setup |
| Guardrails: respects min_order_qty | `plan_order` (Q = max(MOQ, ...)); MOQ invariant in `tests/test_invariants.py` |
| Guardrails: accounts for lead time | protection interval P = L + 1 and inventory position; timing invariant; `test_h7` |
| Guardrails: uses service level for safety stock | SS = z(service_level) * sigma_P in `plan_order`; notebook T3 |
| Guardrails: prevents unrealistic over-ordering | inventory position (no double ordering), order-up-to S only, 30-days-of-cover cap (`MAX_COVER_DAYS`); `test_over_ordering_guardrail_caps_an_order_at_30_days_of_forecast` |
| Guardrails: holding vs stockout trade-off | priced DEFER rule; CSL* check; `docs/TRADE_OFFS.md` |
| Metrics, ethics and trust: defines stockouts, fill rate, total cost | `docs/DESIGN_DOCUMENT.md` (Metrics); `sku_metrics` in `replenish/evaluate.py` |
| Connects decisions to customer trust and cost responsibility | `docs/DESIGN_DOCUMENT.md` (Ethics and trust) |
| Transparency via daily logs | every action logged with its numbers: notebook T6, `outputs/agent_log.txt`, `outputs/decisions.csv` |
| Functionality: loads sales, inventory and params CSVs | `replenish/data.py` (`load_dataset`); notebook T1 |
| Aggregates demand per SKU per day | `aggregate_daily` (order lines summed, missing days filled with 0); notebook T1 |
| EWMA or naive forecast, implemented correctly | `replenish/forecast.py`; EWMA math tests; notebook T2 |
| Forecast updates daily | `ReplenishmentAgent.learn` after each day's demand; leakage invariant |
| Safety stock from forecast error and service_level | `ReplenishmentAgent.sigma1` (RMSE of one-step errors), `plan_order`; notebook T3 |
| Projects inventory over lead time | IP compared with S = mu_P + SS over L + 1 days; dES projects shortage on day t+L |
| Places orders when appropriate | ORDER / HOLD / DEFER in `plan_order`; notebook T4 |
| Simulates day by day | `replenish/sim.py`; notebook T5 |
| Receives POs after lead time | pipeline in `simulate_sku`; timing invariant on 200 random scenarios |
| Clear daily agent log with rationale | `replenish/report.py`; notebook T6 |
| Evaluation: stockouts, fill rate, total cost | `sku_metrics`; notebook T5 and evaluation section |
| Baseline comparison | P0 starter (s,Q) and P1 naive-forecast agent, plus P2 textbook EWMA, two ablations and a clairvoyant reference, on the committed data and 200 demand paths |
| Trade-off reflection | `docs/TRADE_OFFS.md`, shown in the notebook after the service-level sweep |
| Code quality: organized structure | package `replenish/` split by concern; `baselines/`; `tests/` |
| Parameterized (alpha, service level, lead time) | `params.csv` for service level and lead time; `--alpha` / `ALPHA` / `ReplenishmentAgent(alpha=...)`; constants in `replenish/config.py` |
| Clear variable names, comments on major steps | module docstrings describe each step; `docs/DESIGN.md` |
| Easy to run | Colab badge, then Runtime > Run all; locally `pip install -r requirements.txt` and `python -m replenish run` |
| Scaling note (deployment, monitoring, reliability, cost controls) | `docs/SCALING.md`, shown at the end of the notebook |

## Submission checklist

| item | where |
|---|---|
| sales.csv (60-120 days, 1-3 SKUs) | `data/sales.csv`: 120 days, 3 SKUs, order-line grain |
| inventory.csv (opening stock per SKU) | `data/inventory.csv` |
| params.csv (costs, lead time, service level, min order qty) | `data/params.csv` |
| Design document (1 page or less): goal, inputs and outputs, guardrails, metrics, ethics and trust | `docs/DESIGN_DOCUMENT.md` |
| Working code: loads CSVs, aggregates, EWMA, safety stock, projects over lead time, MOQ, receives after lead time, prints log, runs without errors | notebook sections T1-T6; 39 passing tests |
| Evaluation: stockouts, fill rate, total cost, baseline, trade-offs | notebook evaluation section; `outputs/metrics.json`; `docs/TRADE_OFFS.md` |
| Scaling note (half a page or less) | `docs/SCALING.md` |
| GitHub link and successful outputs | the repository URL; notebook executed in Colab with every output saved |
