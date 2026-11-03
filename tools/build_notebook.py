"""Build notebooks/InventoryReplenishmentAgent.ipynb from source.

    python tools/build_notebook.py --repo minchree/inventory-replenishment-agent
"""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat as nbf

NOTEBOOK = Path(__file__).resolve().parents[1] / "notebooks" / "InventoryReplenishmentAgent.ipynb"


def cells(repo: str) -> list:
    md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
    name = repo.split("/")[1]
    badge = (f"[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)]"
             f"(https://colab.research.google.com/github/{repo}/blob/main/notebooks/InventoryReplenishmentAgent.ipynb)")
    return [
        md(f"""{badge}

# Inventory replenishment agent

Every day, for three SKUs, this agent forecasts demand with EWMA, sets safety stock from its own forecast error, compares inventory position with an order-up-to level over the lead time plus one review day, and then orders, holds, or defers. Deferring is priced: the agent waits only when the expected shortage cost of waiting is below the holding cost it saves. It also watches its own forecast for bias and logs an ALERT when it adapts.

Run it with **Runtime > Run all**. The first cell clones [the repository](https://github.com/{repo}), and everything else comes from the package in `replenish/`. After the one-page design document, the sections follow the assignment tasks T1 to T6, then the evaluation and trade-offs, the audit of the course starter notebook, the test suite, and the scaling note."""),
        code(f"""# Setup: works in Colab and locally, and re-running it changes nothing.
import importlib.util, os, subprocess, sys

REPO_URL = "https://github.com/{repo}.git"
IN_COLAB = "google.colab" in sys.modules
if IN_COLAB:
    target = "/content/{name}"
    if not os.path.isdir(target):
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, target], check=True)
    os.chdir(target)
elif os.path.basename(os.getcwd()) == "notebooks":
    os.chdir("..")
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())

# Colab already has numpy, pandas, scipy and matplotlib; install only what's missing.
missing = [m for m in ("hypothesis", "pytest") if importlib.util.find_spec(m) is None]
if missing:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *missing], check=True)

import matplotlib, numpy, pandas, scipy, hypothesis, pytest
print("Python", sys.version.split()[0], "| in Colab:", IN_COLAB, "| cwd:", os.getcwd())
for mod in (numpy, pandas, scipy, matplotlib, hypothesis, pytest):
    print(f"  {{mod.__name__:<11}} {{mod.__version__}}")"""),
        code("""# Knobs. Service levels and lead times live in data/params.csv.
ALPHA = None         # EWMA smoothing constant; None picks it per SKU on the warm-up, e.g. 0.3 fixes it
MC_SEEDS = 200       # demand paths per policy (held-out seeds 5000+); lower it for a faster run
SWEEP_SEEDS = 100    # demand paths per service level in the sweep

import json
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from IPython.display import Image, Markdown, display

from replenish import report
from replenish.config import WARMUP_DAYS
from replenish.data import load_dataset, read_sales
from replenish.evaluate import HEADLINE, POLICIES, diagnostics, evaluate_all, metrics_table, run_dataset

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)
pd.set_option("display.float_format", lambda x: f"{x:,.3f}")"""),
        code("""# The one-page design document: goal, inputs and outputs, guardrails, metrics, ethics and trust
display(Markdown(open("docs/DESIGN_DOCUMENT.md", encoding="utf-8").read()))"""),

        md("""## T1. Load and aggregate demand per day per SKU

`data/sales.csv` is at order-line grain: a SKU-day can have up to four rows, and a day with no demand has no row at all. Aggregation sums the lines per day and SKU, then reindexes to the full calendar so missing days read as zero (`replenish/data.py`)."""),
        code("""sales = read_sales("data/sales.csv")
print(f"sales.csv: {len(sales)} order lines, {sales['date'].nunique()} dates, SKUs {sorted(sales['sku'].unique())}")
print("most lines on one SKU-day:", sales.groupby(["date", "sku"]).size().max())
display(sales.head(6))

ds = load_dataset("data")
print("\\nparams.csv"); display(pd.read_csv("data/params.csv"))
print("inventory.csv"); display(pd.read_csv("data/inventory.csv"))
print(f"daily demand table: {ds.demand.shape[0]} days x {ds.demand.shape[1]} SKUs; "
      f"zero-demand days per SKU: {(ds.demand == 0).sum().to_dict()}")
display(ds.demand.head(8))"""),

        md(f"""## T2. EWMA forecast per SKU

The first {28} days are warm-up. The EWMA level starts at the mean of the first week and runs through days 7 to 27, so every warm-up error is one step ahead. alpha is picked from 0.1 to 0.5 by the lowest one-step MSE. Each SKU is also classified by how often and how evenly it sells (Syntetos-Boylan ADI and CV²), which decides whether the reflect step can trust its tracking signal."""),
        code("""runs = run_dataset(ds, {**POLICIES[HEADLINE], "alpha": ALPHA})
rows = []
for sku, run in runs.items():
    agent = run.policy
    rows.append({"sku": sku, "chosen alpha": agent.memory.base_alpha,
                 **{f"MSE a={a}": m for a, m in agent.alpha_mse.items()},
                 "demand class": agent.demand_class.label, "ADI": agent.demand_class.adi,
                 "CV2": agent.demand_class.cv2, "reflect active": agent.reflect_active})
display(pd.DataFrame(rows).set_index("sku"))

fig, axes = plt.subplots(1, 3, figsize=(14, 3), sharey=False)
for ax, (sku, run) in zip(axes, runs.items()):
    ax.bar(range(len(run.decisions)), run.ledger["demand"], color="#898781", alpha=0.55, label="actual")
    ax.plot([r.forecast for r in run.decisions], color="#0b0b0b", lw=1.5, label="forecast at review")
    ax.set_title(sku, loc="left"); ax.set_xlabel("simulated day")
axes[0].legend(frameon=False, fontsize=8)
plt.tight_layout(); plt.show()"""),

        md("""## T3. Safety stock from forecast error and service level

With L the lead time and one review day, the protection interval is P = L + 1. Then:

- sigma_1 = RMSE of the last 28 one-step forecast errors (floored at max(0.5, 10% of the forecast))
- sigma_P = sigma_1 × √P, mu_P = forecast × P
- SS = z × sigma_P with z from `service_level`, and S = mu_P + SS

The last columns check the service level against the cost parameters. CSL* = 1 − h·T/p, where T is the order-cycle length. It is report-only. The predicted fill rate is what the normal model expects at this target; the achieved fill rate is what the simulation delivered."""),
        code("""diag = diagnostics(runs)
display(pd.DataFrame(diag).T[["demand_class", "alpha", "lead_time_days", "service_level", "z", "sigma1_start",
                               "sigma_P_start", "mu_P_start", "ss_start", "S_start", "mean_order", "cycle_days",
                               "csl_star", "verdict", "predicted_fill_rate", "achieved_fill_rate"]])"""),

        md("""## T4. The daily decision: order, hold or defer

At each review the agent compares inventory position (on hand + on order − backorders) with S.

- **HOLD** when IP ≥ S.
- Below S, the order would be Q = max(MOQ, ⌈S − IP⌉). Before placing it, the agent prices waiting one day. Waiting saves h × Q of holding cost and risks dES extra units short on day t+L (from the normal loss function), at p per unit. It **DEFERs** only if waiting is cheaper and the cycle service level it accepts stays within 2 points of the target. Otherwise it **ORDERs**.
- **ALERT** lines in the T6 log come from the reflect step, when the tracking signal moves beyond 3 standard deviations of what an unbiased forecast would produce.

Three real decisions from this run, with the numbers behind them:"""),
        code("""recs = [r for run in runs.values() for r in run.decisions]
examples = [next(r for r in recs if r.action == "HOLD"),
            next(r for r in recs if r.action == "ORDER" and r.moq_binds),
            next(r for r in recs if r.action == "DEFER")]
cols = ["day", "date", "sku", "action", "qty", "ip", "forecast", "sigma1", "mu_P", "ss", "S", "candidate",
        "csl_wait", "d_es", "wait_cost", "hold_saved", "floor"]
display(pd.DataFrame([{c: getattr(r, c) for c in cols} for r in examples]).set_index("day"))
for r in examples:
    print(report.log_lines(r)[-1])"""),

        md("""## T5. Simulate the horizon: stockouts, fill rate and cost

POs arrive exactly L days after they are placed. Costs: holding on end-of-day stock, the stockout cost once per unit short, and the order cost per PO (0 here; the evaluation also runs 25). The charts show on hand, inventory position, S, safety stock, orders placed and received, deferrals, ALERTs and stockout days."""),
        code("""table = metrics_table(runs)
cols = ["demand", "fill_rate", "achieved_csl", "stockout_days", "units_short", "pos", "defers", "alerts", "capped",
        "holding_cost", "stockout_cost", "order_cost", "relevant_cost", "purchase_spend", "ending_value",
        "avg_on_hand", "avg_inventory_value", "turns", "forecast_mae", "forecast_bias"]
display(pd.DataFrame(table).T[cols])
for sku, run in runs.items():
    report.plot_inventory_story(run, close=False)
    plt.show()"""),

        md("""## T6. Daily agent log

One line per SKU per day. Every rationale is rendered from the numbers in the decision record, so the text and the numbers always agree. The same log is saved to `outputs/agent_log.txt`, and every field is saved to `outputs/decisions.csv`."""),
        code("""log = report.write_run_outputs(runs, table, "outputs")
print("\\n".join(log))
print()
print("\\n".join(report.scorecard(table)))"""),

        md(f"""## Evaluation: baselines, ablations and 200 demand paths

One 92-day path is an anecdote, so every policy also runs on fresh demand paths from the same generator. The policies:

- P0 is the course starter's static (s,Q), run through this simulator with its metrics fixed.
- P1 uses a naive forecast.
- P2 is the textbook EWMA agent, with no defer and no reflect.
- P3 is the full agent.
- P4 knows the future and carries no safety stock. It's a reference point, not an optimum.

Two ablations switch off defer and reflect one at a time. The design was settled on dev seeds 1000-1199; these results use held-out seeds 5000 and up."""),
        code("""res = evaluate_all(ds, "outputs", mc_seeds=MC_SEEDS, sweep_seeds=SWEEP_SEEDS)
comp = res["comparison"]
print("Committed CSVs, all SKUs:")
display(comp[comp.sku == "TOTAL"].set_index("policy")[["fill_rate", "stockout_days", "units_short", "holding_cost",
                                                     "stockout_cost", "relevant_cost", "pos"]])
print(f"{MC_SEEDS} demand paths, all SKUs (mean, 5th and 95th percentile):")
display(res["summary"][res["summary"].sku == "TOTAL"].set_index("policy"))
print("Paired comparison of relevant cost on the same paths:")
display(pd.DataFrame(res["deltas"]))
display(Image("outputs/figures/policy_comparison.png"))"""),
        code("""# Where each signature feature pays and where it costs, per SKU (P3 minus the ablation, same paths)
mc = res["mc"]
def per_sku(other):
    a = mc[mc.policy == HEADLINE].set_index(["seed", "sku"]).relevant_cost
    b = mc[mc.policy == other].set_index(["seed", "sku"]).relevant_cost
    d = (a - b).groupby("sku")
    return pd.DataFrame({"mean $ difference": d.mean(), "share of paths P3 cheaper": d.apply(lambda s: (s < 0).mean())})
for other in ("P3 without defer", "P3 without reflect", "P2 EWMA textbook"):
    print(f"P3 full agent minus {other}:")
    display(per_sku(other))"""),
        md("""### Service-level sweep

The full agent is run at service levels from 0.80 to 0.995, plus each SKU's CSL*, and mean cost is plotted against fill rate. If CSL* is a good guide, the cheapest level in the sweep should sit near it."""),
        code("""sweep = res["sweep"]
best = sweep.loc[sweep.groupby("sku").relevant_cost.idxmin()].set_index("sku")
print(pd.DataFrame({"configured": {s: d["service_level"] for s, d in res["diagnostics"].items()},
                    "CSL*": {s: d["csl_star"] for s, d in res["diagnostics"].items()},
                    "cheapest in sweep": best.service_level}).to_string())
display(Image("outputs/figures/sl_frontier.png"))"""),
        code("""# Trade-off reflection: inventory vs service
display(Markdown(open("docs/TRADE_OFFS.md", encoding="utf-8").read()))"""),

        md("""## Audit of the course starter notebook

The starter was ported line for line to `baselines/starter_port.py`. Each suspected defect became a property test that runs on both the port (expected to fail, strict xfail) and this agent (must pass). All seven were confirmed; details are in `docs/STARTER_AUDIT.md`. The table below re-runs the starter's own data and parameters, fixing one thing at a time."""),
        code("""from baselines.audit import starter_before_after
display(starter_before_after().set_index("version"))"""),

        md("""## Tests

The suite covers the hand-worked 6-day trace in `docs/DESIGN.md`, the worked examples from the brief, data loading, and the forecast maths. Hypothesis checks six invariants on 200 random scenarios each: the stock ledger balances, POs arrive exactly L days later, MOQ is respected, costs recompute from the ledger, no decision sees future demand, and the clairvoyant policy never stocks out once its first order can land. The `xfail` lines are the starter defects, failing as expected."""),
        code("""out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rx", "--color=no", "-p", "no:cacheprovider"],
                     capture_output=True, text=True)
print(out.stdout[-6000:])
print("pytest exit code:", out.returncode)"""),
        code("""# Scaling note: deployment, monitoring, reliability, cost controls
display(Markdown(open("docs/SCALING.md", encoding="utf-8").read()))"""),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="GitHub owner/name, used for the clone URL and the badge")
    args = parser.parse_args()
    nb = nbf.v4.new_notebook()
    nb.cells = cells(args.repo)
    nb.metadata = {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                   "language_info": {"name": "python"}, "colab": {"provenance": []}}
    NOTEBOOK.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(nb, NOTEBOOK)
    print(f"wrote {NOTEBOOK}")


if __name__ == "__main__":
    main()
