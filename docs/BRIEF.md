# Build brief: Inventory Replenishment Agent

You're building my graded project for SJSU's Applied AI course: an inventory replenishment agent. My classmates are building the same assignment with Claude and Codex, so the default version (EWMA, then z·σ·√L, then a reorder point, then a printed log) is what everyone else hands in. This brief describes a version that differs in what it does, not just how it looks: every decision traces back to its numbers, "wait" is decided by cost, the agent checks its own forecast, and the evaluation is honest. The required tasks come first. A grader with the rubric should find each one in under a minute. The program runs in Google Colab: a grader opens the notebook from the GitHub badge, chooses Runtime → Run all, and sees every output without touching anything.

First action: save this brief verbatim to `docs/BRIEF.md` and add this line to `CLAUDE.md`:
`Brief: docs/BRIEF.md (conventions, formulas, phases). Read it before editing simulation, policy or metrics code.`

## 1. Sources of truth

**Assignment** (the rubric wins any conflict):
- Data: `sales.csv` (`date,sku,qty_sold`), `inventory.csv` (`sku,opening_stock`), `params.csv` (`sku,unit_cost,holding_cost_per_day,stockout_cost,lead_time_days,min_order_qty,service_level`). 1–3 SKUs, 60–120 days.
- Tasks:
  - T1: Load and aggregate demand per day per SKU.
  - T2: EWMA forecast per SKU. Naive is allowed.
  - T3: Safety stock from forecast error and `service_level`.
  - T4: Each day, check projected inventory over lead time + review period, then either order (respecting `min_order_qty`) or wait (to save holding cost).
  - T5: Simulate the horizon with POs arriving after the lead time. Track stockouts, fill rate, and holding + stockout + order cost (fixed cost per PO is 0 or a constant).
  - T6: Print a daily agent log with the rationale for each action.
- Submission: GitHub link plus successful outputs.

**Starter notebook**: https://github.com/myrah/AAI2025/blob/dev/aai/InventoryReplenishmentAgent.ipynb
- Contents: one synthetic SKU, a RandomForest forecast, `InventorySim`, and a `ReplenishmentAgent` built from `Obs`, `Memory` and `tool_*` functions.
- Saved outputs: the baseline (s,Q) has total cost 22,159.83 at fill rate 0.948. The "agentic" policy has 22,535.83 at 0.950.
- Keep its agent vocabulary (`Obs`, `Memory`, tools, `decide`/`act`) so the grader sees continuity, and rebuild what's inside.

**Rubric**: `docs/rubric.docx`. Read it with the docx skill before planning. If it isn't there, ask me for it before Phase 2 ends.

**Target runtime**: Google Colab on the free CPU runtime. The rules are under Colab in §6. Local Python is only for your build-and-test loop.

## 2. The signature

Five features, each one shown in the README and the notebook:

1. **Audit trail.** Every daily decision is a `DecisionRecord`: state, forecast, σ, SS, S, the defer-test numbers, action, quantity. The log rationale is rendered from the record, so the words always match the numbers.
2. **Economic defer.** When the MOQ forces a large order to cover a small gap, the agent compares the expected shortage cost of waiting a day with the holding cost that waiting saves, within a service-level tolerance. Each SKU also gets a check of whether its `service_level` agrees with its own cost parameters.
3. **Reflect step.** The agent tracks bias with a tracking signal. When the signal crosses the alarm, the agent adapts and logs an ALERT.
4. **Starter audit.** Reproduce the starter's KPI table, test it for defects (§5), fix them, and show before/after.
5. **Honest evaluation.** Baselines, a clairvoyant reference, ablations and 200 demand seeds. Relevant cost is reported separately from purchase spend. A result where we lose is reported as a loss, with the reason.

## 3. Phases

Run them in order. Each one ends on its **Done when** line. Commit at the end of each phase.

**Phase 1: Recon** [docx]
1. Read the rubric.
2. Download the starter and run it unchanged in a throwaway venv (numpy, pandas, scipy, scikit-learn, matplotlib, pydantic).
3. Write `docs/COMPLIANCE.md` with one row per rubric line and per task T1–T6. Each row says where the item will live (file, function, output artifact) and its status.

*Done when:* every rubric line and T1–T6 has a row, and the starter's KPI table matches the saved outputs above (or the gap is explained).

**Phase 2: Design** [brainstorming, documentation-and-adrs]
1. Use brainstorming on the choices this brief leaves open: α grid, σ floor, defer tolerance and chart set. Treat §4 as settled.
2. Write `docs/DESIGN.md`. It covers event order, cost semantics, formulas, data archetypes, decision logic and metric definitions. It also includes a hand-worked 6-day trace for one SKU (L=2, one MOQ-bound order, one stockout) with every number computed by hand.
3. Stop and show me DESIGN.md.

*Done when:* I approve it. The hand trace becomes the first test fixture.

**Phase 3: Tracer bullet** [writing-plans, test-driven-development, incremental-implementation]
1. Write the plan.
2. Build one thin end-to-end path: one SKU, naive forecast, load → forecast → decide → simulate → log → metrics. Write the hand trace as the first **red** test.

*Done when:* `pytest` is green, including the hand trace, and `python -m replenish run` prints a log for that SKU.

**Phase 4: Full agent** [test-driven-development, property-based-testing]
1. Add the data generator and CSVs (§4.6), EWMA with the error tracker, safety stock, MOQ, the defer test, the reflect step, and all SKUs.
2. Write the invariant tests in §4.7.

*Done when:* the invariants pass under hypothesis with at least 200 examples each, and the log for the committed CSVs contains at least one ORDER, HOLD, DEFER and ALERT line. The synthetic data exists to exercise every branch. If a branch never fires, adjust that archetype and record why in DESIGN.md.

**Phase 5: Evaluation** [dataviz]
Build the baselines, Monte Carlo, service-level sweep and charts (§4.9).

*Done when:* `python -m replenish evaluate` writes `outputs/metrics.json`, `outputs/policy_comparison.csv` and `outputs/figures/*.png`, and every number in the README is read from those files.

**Phase 6: Starter audit** [systematic-debugging]
1. Port the starter's sim and KPI logic faithfully to `baselines/starter_port.py`.
2. Treat each item in §5 as a hypothesis. Write a test for it that runs on the port. If the test goes red, document the defect. If it stays green, drop the item.
3. Re-run the port with the fixes applied and record the before/after KPIs.

*Done when:* `docs/STARTER_AUDIT.md` lists only confirmed defects, each with the starter line, the evidence test, the fix and the KPI impact.

**Phase 7: Notebook and README** [dataviz, humanizer]
1. Build `notebooks/InventoryReplenishmentAgent.ipynb` with these parts:
   - A Colab badge and the setup cell described under Colab in §6.
   - A `!python -m pytest -q` cell, so the passing test run is part of the saved outputs.
   - T1–T6 in order, each under a heading that names the task.
   - A per-SKU safety-stock table that includes the CSL* diagnostic.
   - The first 15 log lines, plus notable lines covering each verb at least once.
   - The KPI table, the charts and the audit summary.
2. Run the notebook locally with `jupyter nbconvert --execute --inplace` as a quick check. The outputs that get submitted come from a Colab run in Phase 8.
3. Write the README in this order: results table and inventory chart first, then "How the agent decides", "What's different", "Starter audit", "Reproduce" (the Open in Colab badge first, then 4 local commands or fewer) and "Assumptions and limits".
4. Write `docs/DEFENSE.md`: 10 questions a grader might ask, each answered by citing our files. Examples: why σ comes from forecast error, why P = L+1, CSL vs fill rate, when deferring lowers cost, what the tracking signal does. I have to be able to explain every line I submit.

*Done when:* on a fresh local clone, the README commands reproduce every README number, and the local notebook run finishes without errors.

**Phase 8: Verify and ship** [verification-before-completion, code-simplification, git-workflow-and-versioning]
1. In a clean venv: install, run `pytest`, `run` and `evaluate`, and execute the notebook.
2. Do a simplification pass, then re-run all of the above.
3. Ask me before you create the GitHub repo or push. The repo has to be public so Colab can clone it.
4. Give me a short Colab checklist: open the notebook from the badge, choose Runtime → Run all on a fresh runtime, then File → Download .ipynb into `notebooks/`.
5. Check the downloaded notebook: every code cell has outputs, there are no errors, and the numbers match `outputs/metrics.json`. Then commit and push it.

*Done when:* every local check passes and its output is in your final message, the Colab-executed notebook is committed with all its outputs, and I have the repo URL.

## 4. Reference

### 4.1 One day, in order
Most off-by-one bugs come from this sequence, so pin it.
1. Receive the POs due today. Each one was placed on day t−L.
2. **Review.** The agent observes on-hand, on-order and backorders, and updates the forecast with demand through day t−1. It then decides. Any PO placed now is due on day t+L.
3. Demand D_t arrives and is filled from on-hand. Record filled and short units.
4. Book costs: holding on end-of-day on-hand, stockout cost on units that went short today, and order cost K for each PO placed today.

Decisions read **inventory position**: IP = on_hand + on_order − backorders. IP counts stock already in transit, so it never gets ordered twice.

The **protection interval** is P = L + R, with R = 1. Today's IP has to carry demand on days t through t+L, until tomorrow's order can land. `lead_time_days` must be at least 1.

`opening_stock` is on-hand at the start of the first simulated day, with nothing on order.

### 4.2 Costs
- Default to backorders (this matches the starter). Lost sales goes behind a flag.
- `stockout_cost` is charged once per unit short, on the day it goes short.
- `holding_cost_per_day` is charged per unit of end-of-day on-hand.
- Order cost is K per PO. Use K = 0 for the headline run, and also report K = 25.
- **Relevant cost** = holding + stockout + ordering, and policies are compared on it. Report purchase spend (unit_cost × units received) and ending-inventory value next to it, so a policy can't look cheap by running the shelf down at the end.

### 4.3 Forecast and error
- The first 28 days are **warm-up**. The simulation runs from day 29 on.
- Initialize the EWMA level at the warm-up mean. Pick α from {0.1, 0.2, 0.3, 0.4, 0.5} by the lowest one-step MSE over the warm-up.
- EWMA: F_{t+1} = α·D_t + (1−α)·F_t. Naive: F_{t+1} = D_t.
- σ₁ is the RMSE of the one-step-ahead errors e_t = D_t − F_t over the trailing 28 days, which makes it out-of-sample by construction. Floor σ₁ so a calm stretch can't zero out the safety stock.
- μ_P = F·P and σ_P = σ₁·√P. The L-day versions (μ_L, σ_L) follow the same pattern with L in place of P.
- At the end of warm-up, classify each SKU by ADI and the CV² of its nonzero demand (Syntetos–Boylan cut-offs 1.32 and 0.49), and log the class.

### 4.4 Decision
- z = Φ⁻¹(service_level). The `service_level` column is read as cycle service level (CSL).
- SS = z·σ_P and S = μ_P + SS.
- If IP ≥ S, the action is **HOLD**, and the log line shows days of cover.
- If IP < S, then gap = S − IP and Q = max(min_order_qty, ⌈gap⌉). Run the **defer** test:
  - CSL_wait = Φ((IP − μ_P)/σ_P).
  - ΔES = σ_P·G((IP − μ_P)/σ_P) − σ_L·G((IP − μ_L)/σ_L), where G(k) = φ(k) − k·(1 − Φ(k)) is the standard normal loss function. ΔES is the expected number of extra units short on day t+L, the one day that today's order covers and tomorrow's would not.
  - **DEFER** if stockout_cost·ΔES < holding_cost_per_day·Q **and** CSL_wait ≥ service_level − tolerance (default 0.02).
  - Otherwise, **ORDER** Q.
- Report-only diagnostic: CSL* = 1 − h·T/p, where T = max(R, Q̄/μ) is the expected order-cycle length in days and Q̄ is the mean order size. The reasoning: one more unit of S is carried for the whole cycle at cost h·T, and it avoids one unit short with probability P(stockout in the cycle), saving p.
  - Show CSL* next to `service_level` and flag gaps of more than 2 points.
  - When h·T ≥ p, say plainly that safety stock doesn't pay at these costs.
- Fill-rate check: the predicted fill rate is β ≈ 1 − σ_P·G(z)/Q̄. Compare it with the achieved fill rate. The notebook shows that hitting a CSL target and hitting a fill rate are different things.

### 4.5 Reflect
- Tracking signal TS = Σe / MAD, both over the trailing 28 days.
- When |TS| > 4, set α = 0.5 until |TS| < 2 for 7 days in a row, and log an ALERT with the numbers.
- Reflect is a flag, so it can be ablated.

### 4.6 Data
`replenish/datagen.py` is seeded and writes `data/*.csv` for 120 days. `sales.csv` is at transaction grain: each SKU-day's demand is split across 1–4 rows, and zero-demand days have no rows. That way, T1's aggregation (group, sum, reindex to the full calendar, fill with 0) has real work to do. Suggested archetypes:

| SKU | Archetype | Demand | unit_cost | h/day | stockout_cost | L | MOQ | SL | opening |
|---|---|---|---|---|---|---|---|---|---|
| SKU-A | fast mover | ~40/day, weekly ±25%, sd ~6 | 4.00 | 0.02 | 1.50 | 3 | 60 | 0.95 | 200 |
| SKU-B | trend + promos | 12→20/day, ~6 promo days ×2.5 | 25.00 | 0.10 | 25.00 | 7 | 120 | 0.98 | 90 |
| SKU-C | intermittent | P(demand)=0.35, size 1–6 | 80.00 | 0.40 | 40.00 | 10 | 24 | 0.98 | 30 |

Why these values:
- The CSL* diagnostic gets something to say for every SKU: CSL* ≈ 0.98 for A (SL 0.95, under-protected), ≈ 0.97 for B (aligned), ≈ 0.80 for C (over-protected).
- SKU-B opens below S, so the log shows a reaction on day 1.
- Cost rates are scaled up from real-world levels so that the holding-vs-stockout trade-off shows up within 92 days. The README says so.

State this assumption in the README: historical sales equal unconstrained demand (no censoring).

### 4.7 Invariants (tests)
- **Ledger.** For each SKU-day: on_hand_end = on_hand_start + received − filled, and filled + newly short = demand.
- **Timing.** Every PO arrives exactly L days after it's placed, and nothing arrives that wasn't ordered.
- **MOQ.** Every PO quantity is at least min_order_qty.
- **No leakage.** Future-shuffle test: permuting the demand after day t leaves every DecisionRecord through day t unchanged.
- **Metrics.** Fill rate is in [0, 1], the clairvoyant policy has zero stockouts, and the costs recompute exactly from the ledger.
- **Hand trace.** The simulation matches it to the cent.

### 4.8 Daily log
The log is fixed-width ASCII, one line per SKU per day, using the verbs ORDER / HOLD / DEFER / ALERT. Also write `outputs/agent_log.txt`, `outputs/decisions.csv` (every DecisionRecord field) and a per-SKU scorecard at the end. Format illustration:

```
d031 2025-02-01 SKU-B ORDER 120  IP=146 < S=151 (mu_P=118 + SS=33, z=2.05, sigma_P=16.1) | gap 5, MOQ 120 binds | wait: +0.26u short ($6.44) < $12.00 holding saved, but CSL_wait 0.959 < floor 0.960 -> order
d031 2025-02-01 SKU-A HOLD     0  IP=212 >= S=186 (mu_P=160 + SS=26) | 5.3 days of cover
d031 2025-02-01 SKU-C DEFER    0  IP=25 < S=26.8 (gap 2), MOQ 24 | wait: +0.05u short ($2.12) < $9.60 holding saved, CSL_wait 0.963 >= floor 0.960 -> defer
d032 2025-02-02 SKU-B ALERT       TS=+4.6 > 4 (forecast running low) -> alpha 0.20 -> 0.50 until |TS| < 2 for 7 days
```

### 4.9 Evaluation
- **Policies:**
  - P0: the starter port with fixed metrics (static s, Q = max(MOQ, EOQ)).
  - P1: naive-forecast agent.
  - P2: textbook EWMA agent (no defer, no reflect).
  - P3: full agent.
  - P4: **clairvoyant** reference (true future demand, zero SS). It's a reference point, not an optimum.
- **Ablations:** defer on/off, reflect on/off.
- **Monte Carlo:** 200 generator seeds. Report the mean and the 5th–95th percentile for fill rate, stockout days and relevant cost, per SKU and in total. Headline single-path numbers come from the committed CSVs.
- **Sweep:** service_level from 0.80 to 0.995 for P3. Plot relevant cost against fill rate for each SKU, and mark the configured SL, the empirical min-cost SL and CSL*.
- **Metrics:**
  - Fill rate: units filled from stock on the day demanded, divided by total demand.
  - Stockout days.
  - Achieved CSL: share of replenishment cycles with no stockout.
  - Forecast MAE and bias.
  - Average on-hand, turns and PO count.
  - Relevant cost, purchase spend and ending-inventory value.
- **Charts:**
  - Per-SKU inventory story: on-hand and IP lines, an S/SS band, markers from each PO placement to its arrival, and shaded stockout days, with forecast vs actual underneath.
  - Policy comparison with the Monte Carlo intervals.
  - Service-level frontier.

## 5. Starter-audit hypotheses
Confirm each one with a red test, or drop it.
- **H1.** `feat['ma7'] = feat['demand'].rolling(7).mean()` includes the same day's demand, so the RandomForest sees its own target.
- **H2.** `tool_forecast(i, L, series_pred)` averages the predictions for days i through i+L−1. Each of those predictions was built from actuals up to its own day, so decisions use future demand.
- **H3.** Safety stock uses `train['demand'].std()`, which measures demand variability (trend and seasonality included), not forecast error. The residual σ in the next cell is in-sample, so it understates the error.
- **H4.** `ROP_dyn` is computed, but `ReplenishmentAgent.decide` uses the static global `ROP`.
- **H5.** `kpis()` divides by Σ(sales + backlog), but backlog is a daily level, so a unit backordered for 5 days is counted 5 times. The positive-diff numerator also nets same-day clears against new shortages. Expect the fill rate to be biased upward.
- **H6.** `cost_stockout += p * backlog` runs every day, which charges per unit per day. The parameter is described as a penalty per unit short.
- **H7.** The ROP covers L days, but with daily review and the starter's event order, the exposure is L+1 days.

## 6. Working rules
- Check the local Python version first. If Python 3.11+ is missing, stop and tell me.
- Dependencies: numpy, pandas, scipy and matplotlib, plus pytest and hypothesis for tests.
- **Colab** (the target runtime):
  - A grader runs Runtime → Run all on a fresh runtime, and it finishes with no prompts, file uploads, Drive mounts, sign-ins or runtime restarts.
  - Use Colab's preinstalled numpy, pandas, scipy and matplotlib as they are. `requirements.txt` sets minimum versions (`>=`), and the setup cell installs only what's missing (for example `pip install -q hypothesis`). An exact pin that forces a reinstall brings up Colab's "restart runtime" prompt and stops Run all.
  - The setup cell runs the same way in Colab and locally, and re-running it changes nothing. In Colab (`'google.colab' in sys.modules`), it clones the repo into `/content` if the repo isn't there yet and changes into it. Locally, it uses the repo it's already in. It prints `sys.version` and the package versions, so the saved outputs record the environment.
  - Data comes from the committed CSVs or the seeded generator.
  - Charts display inline with `plt.show()` and are also saved to `outputs/figures/`.
  - Run all finishes in under 3 minutes. The Monte Carlo seed count and the sweep grid are constants at the top of the notebook, so they're easy to reduce.
- Seed everything. Two runs produce identical logs and metrics.
- The decision core is deterministic Python. Every number in prose is read from `outputs/`.
- Keep log text ASCII (write mu and sigma as words) so it prints in any console and in redirected files.
- Ask me before you create the GitHub repo, push, make the repo public, or change the assignment's CSV schemas.
- Package layout:
  - `replenish/`: data, datagen, forecast, policy, agent, sim, evaluate, report, cli
  - plus `baselines/`, `tests/`, `data/`, `outputs/`, `notebooks/`, `docs/`
  - CLI: `python -m replenish generate | run | evaluate`
- Stretch work, only after Phase 8 passes:
  - Croston-SBA forecast for intermittent SKUs.
  - Fill-rate target mode, which solves G(k) = (1−β)·Q̄/σ_P.
  - Day-of-week seasonal indices.
  - A `--narrate` flag that sends a week of DecisionRecords to Claude and gets back a 5-line buyer memo. Load the claude-api skill for the model and SDK. The deterministic log stays the source of truth. In Colab, the key is read from Colab Secrets (`google.colab.userdata`), and the flag skips cleanly when no key is set.
- When you finish, list the skills you used in one line.
