"""The daily agent log (T6), the scorecard, output files, charts, and the README results block.

Log text is rendered from DecisionRecord fields only, so the words can't drift from the numbers.
Text stays ASCII so it prints in any console and in redirected files.
"""

from __future__ import annotations

import math
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from .agent import DecisionRecord
from .config import MAX_COVER_DAYS
from .datagen import SKUS

# Reference palette (dataviz skill): categorical slots 1-3, critical status, neutrals.
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA, CRITICAL = "#2a78d6", "#eb6834", "#1baf7a", "#d03b3b"
VERBS = ("ORDER", "HOLD", "DEFER", "ALERT")


# ---------------------------------------------------------------- log

def _n(x: float) -> str:
    """Whole units from 100 up, one decimal below (and no trailing .0)."""
    return f"{x:.0f}" if abs(x) >= 100 else f"{x:.1f}".removesuffix(".0")


def rationale(rec: DecisionRecord) -> str:
    if rec.rule == "static":
        if rec.action == "ORDER":
            return f"IP={_n(rec.ip)} <= s={_n(rec.S)} (static: L*mu={_n(rec.mu_P)} + z*sqrt(L)*sigma_raw={_n(rec.ss)}) -> order Q={rec.qty}"
        return f"IP={_n(rec.ip)} > s={_n(rec.S)} (static reorder point)"
    if rec.rule == "clairvoyant":
        if rec.action == "ORDER":
            return f"IP={_n(rec.ip)} < actual demand through t+L={_n(rec.S)} -> order {rec.qty}"
        return f"IP={_n(rec.ip)} >= actual demand through t+L={_n(rec.S)}"

    if rec.action == "HOLD":
        cover = rec.ip / rec.forecast if rec.forecast > 0 else math.inf
        return f"IP={_n(rec.ip)} >= S={rec.S:.1f} (mu_P={_n(rec.mu_P)} + SS={_n(rec.ss)}) | {cover:.1f} days of cover"
    head = (f"IP={_n(rec.ip)} < S={rec.S:.1f} (mu_P={_n(rec.mu_P)} + SS={_n(rec.ss)}, "
            f"z={rec.z:.2f}, sigma_P={rec.sigma_P:.1f})")
    gap = f"gap {math.ceil(rec.gap - 1e-9)}" + (f", MOQ {rec.candidate} binds" if rec.moq_binds else "")
    if rec.capped:
        gap += f", capped at {MAX_COVER_DAYS} days of forecast = {rec.candidate}"
    if not rec.defer_enabled:
        return f"{head} | {gap} -> order {rec.qty} (defer test off)"
    cost_ok = rec.wait_cost < rec.hold_saved
    wait = (f"wait: +{rec.d_es:.2f}u short (${rec.wait_cost:.2f}) {'<' if cost_ok else '>='} "
            f"${rec.hold_saved:.2f} holding saved")
    if rec.action == "DEFER":
        tail = f", CSL_wait {rec.csl_wait:.3f} >= floor {rec.floor:.3f} -> defer"
    elif cost_ok:
        tail = f", but CSL_wait {rec.csl_wait:.3f} < floor {rec.floor:.3f} -> order"
    else:
        tail = " -> order"
    return f"{head} | {gap} | {wait}{tail}"


def log_lines(rec: DecisionRecord) -> list[str]:
    prefix = f"d{rec.day:03d} {rec.date} {rec.sku:<6}"
    lines = [f"{prefix} ALERT       {rec.alert}"] if rec.alert else []
    lines.append(f"{prefix} {rec.action:<5} {rec.qty:>4}  {rationale(rec)}")
    return lines


def daily_log(runs: dict) -> list[str]:
    """One line per SKU per day, days in order; an ALERT line comes right before that SKU's decision."""
    skus = list(runs)
    n_days = len(runs[skus[0]].decisions)
    return [line for t in range(n_days) for sku in skus for line in log_lines(runs[sku].decisions[t])]


def notable_lines(log: list[str], skip: int = 15, per_verb: int = 2) -> list[str]:
    """The first few lines of each verb after the opening stretch, in log order."""
    picked, counts = [], {v: 0 for v in VERBS}
    for line in log[skip:]:
        verb = line.split()[3]
        if counts.get(verb, per_verb) < per_verb:
            counts[verb] += 1
            picked.append(line)
    return picked


def scorecard(table: dict[str, dict]) -> list[str]:
    head = (f"{'SKU':<6} {'fill':>6} {'CSL':>6} {'so_days':>7} {'short':>6} {'POs':>4} {'defer':>5} "
            f"{'alert':>5} {'holding':>9} {'stockout':>9} {'relevant':>9}")
    lines = [head, "-" * len(head)]
    for sku, m in table.items():
        csl = "  n/a" if m["achieved_csl"] is None or math.isnan(m["achieved_csl"]) else f"{m['achieved_csl']:.3f}"
        lines.append(f"{sku:<6} {m['fill_rate']:>6.3f} {csl:>6} {m['stockout_days']:>7} {m['units_short']:>6.0f} "
                     f"{m['pos']:>4} {m['defers']:>5} {m['alerts']:>5} {m['holding_cost']:>9.2f} "
                     f"{m['stockout_cost']:>9.2f} {m['relevant_cost']:>9.2f}")
    return lines


def write_run_outputs(runs: dict, table: dict[str, dict], out_dir: str | Path) -> list[str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    log = daily_log(runs)
    (out / "agent_log.txt").write_text("\n".join(log + ["", *scorecard(table)]) + "\n", encoding="ascii")
    records = [{**asdict(r), "rationale": rationale(r)} for run in runs.values() for r in run.decisions]
    pd.DataFrame(records).sort_values(["day", "sku"], kind="stable").to_csv(out / "decisions.csv", index=False)
    pd.concat([run.frame() for run in runs.values()]).sort_values(["day", "sku"], kind="stable") \
        .to_csv(out / "ledger.csv", index=False)
    return log


# ---------------------------------------------------------------- charts

def _style(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=INK2, labelsize=9)


def _save(fig, path, close):
    import matplotlib.pyplot as plt
    if path is not None:
        fig.savefig(path, dpi=130, facecolor=SURFACE, bbox_inches="tight")
    if close:
        plt.close(fig)
    return fig


def plot_inventory_story(run, path=None, close=True):
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    g, recs = run.ledger, run.decisions
    x = np.arange(len(recs))
    ip = np.array([r.ip for r in recs])
    S = np.array([r.S for r in recs])
    ss = np.array([r.ss for r in recs])
    placed = np.flatnonzero(g["ordered"] > 0)
    arrived = np.flatnonzero(g["received"] > 0)
    deferred = [i for i, r in enumerate(recs) if r.action == "DEFER"]
    alerts = [i for i, r in enumerate(recs) if getattr(r, "alert", "")]

    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(11, 6.2), sharex=True, facecolor=SURFACE,
                                  gridspec_kw={"height_ratios": [3, 1.2], "hspace": 0.08})
    _style(ax)
    _style(ax2)
    for i in np.flatnonzero(g["short"] > 0):
        ax.axvspan(i - 0.5, i + 0.5, color=CRITICAL, alpha=0.13, lw=0)
    ax.fill_between(x, 0, np.maximum(ss, 0), step="mid", color=MUTED, alpha=0.18, lw=0)
    ax.step(x, S, where="mid", color=INK2, lw=1.2, ls="--")
    ax.step(x, ip, where="mid", color=ORANGE, lw=2)
    ax.plot(x, g["on_hand_end"], color=BLUE, lw=2)
    ax.scatter(placed, ip[placed], marker="^", s=55, color=AQUA, edgecolor=SURFACE, lw=1.5, zorder=5)
    ax.scatter(arrived, g["on_hand_start"][arrived] + g["received"][arrived], marker="o", s=45,
               color=AQUA, edgecolor=SURFACE, lw=1.5, zorder=5)
    if deferred:
        ax.scatter(deferred, ip[deferred], marker="D", s=40, facecolor=SURFACE, edgecolor=INK, lw=1.2, zorder=6)
    top = max(ip.max(), S.max(), g["on_hand_end"].max()) * 1.08
    for i in alerts:
        ax.annotate("ALERT", (i, top), ha="center", va="bottom", fontsize=7, color=INK2,
                    annotation_clip=False)
        ax.axvline(i, color=INK2, lw=0.8, ls=":")
    ax.set_ylim(min(0, ip.min()) * 1.1, top * 1.06)
    ax.set_ylabel("units", color=INK2, fontsize=9)
    archetype = SKUS.get(run.sku, {}).get("archetype", "")
    ax.set_title(f"{run.sku} ({archetype}): on hand, inventory position and order-up-to level S",
                 loc="left", color=INK, fontsize=12, pad=46)
    handles = [Line2D([], [], color=BLUE, lw=2, label="on hand (end of day)"),
               Line2D([], [], color=ORANGE, lw=2, label="inventory position"),
               Line2D([], [], color=INK2, lw=1.2, ls="--", label="S = mu_P + SS"),
               Patch(color=MUTED, alpha=0.3, label="safety stock"),
               Line2D([], [], marker="^", ls="", color=AQUA, markersize=8, label="PO placed"),
               Line2D([], [], marker="o", ls="", color=AQUA, markersize=7, label="PO received"),
               Patch(color=CRITICAL, alpha=0.25, label="stockout day")]
    if deferred:
        handles.append(Line2D([], [], marker="D", ls="", markerfacecolor=SURFACE, markeredgecolor=INK,
                              markersize=7, label="defer"))
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, 1.01), ncols=4, frameon=False,
              fontsize=8, labelcolor=INK2, borderaxespad=0)

    ax2.bar(x, g["demand"], width=0.7, color=MUTED, alpha=0.55, label="actual demand")
    ax2.plot(x, [r.forecast for r in recs], color=INK, lw=1.5, label="forecast at review")
    ax2.set_ylabel("units/day", color=INK2, fontsize=9)
    ax2.legend(loc="upper left", ncols=2, frameon=False, fontsize=8, labelcolor=INK2)
    ticks = x[::14]
    ax2.set_xticks(ticks)
    ax2.set_xticklabels([run.dates[i] for i in ticks], fontsize=8)
    return _save(fig, path, close)


def plot_policy_comparison(summary: pd.DataFrame, path=None, close=True):
    import matplotlib.pyplot as plt

    tot = summary[summary["sku"] == "TOTAL"].reset_index(drop=True)
    names = list(tot["policy"])[::-1]
    tot = tot.set_index("policy").loc[names]
    y = np.arange(len(names))
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), sharey=True, facecolor=SURFACE)
    for ax, metric, label in ((axes[0], "relevant_cost", "relevant cost, $ (holding + stockout + ordering)"),
                              (axes[1], "fill_rate", "fill rate")):
        _style(ax)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        ax.grid(axis="y", visible=False)
        mean, lo, hi = (tot[f"{metric}_{s}"].to_numpy() for s in ("mean", "p5", "p95"))
        for i, name in enumerate(names):
            colour = BLUE if name.startswith("P3 full") else INK2
            ax.plot([lo[i], hi[i]], [i, i], color=colour, lw=2, solid_capstyle="round")
            hollow = name.startswith("P4")
            ax.scatter(mean[i], i, s=60, zorder=3, color=SURFACE if hollow else colour,
                       edgecolor=colour, lw=1.8)
            fmt = f"{mean[i]:,.0f}" if metric == "relevant_cost" else f"{mean[i]:.3f}"
            ax.annotate(fmt, (hi[i], i), xytext=(6, 0), textcoords="offset points", va="center",
                        fontsize=8, color=INK2)
        ax.set_xlabel(label, color=INK2, fontsize=9)
    axes[0].set_yticks(y)
    axes[0].set_yticklabels(names, fontsize=9, color=INK)
    fig.suptitle("All SKUs over 200 demand paths: mean and 5th-95th percentile (P4 knows the future)",
                 x=0.01, ha="left", color=INK, fontsize=12)
    fig.tight_layout()
    return _save(fig, path, close)


def plot_frontier(sweep: pd.DataFrame, diag: dict[str, dict], path=None, close=True):
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    skus = list(diag)
    fig, axes = plt.subplots(1, len(skus), figsize=(4.0 * len(skus), 3.9), facecolor=SURFACE)
    axes = np.atleast_1d(axes)
    for ax, sku in zip(axes, skus):
        _style(ax)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        d = sweep[sweep["sku"] == sku].sort_values("service_level")
        ax.plot(d["fill_rate"], d["relevant_cost"], color=INK2, lw=1.5, marker="o", markersize=3.5)
        sl = diag[sku]["service_level"]
        star = min(max(diag[sku]["csl_star"], 0.5), 0.995)
        best = d.loc[d["relevant_cost"].idxmin()]
        # shapes as well as colours: the cheapest level and CSL* often land on the same point
        marks = ((best["service_level"], dict(marker="s", s=110, color=AQUA, edgecolor=SURFACE, zorder=3)),
                 (sl, dict(marker="o", s=70, color=BLUE, edgecolor=SURFACE, zorder=4)),
                 (star, dict(marker="D", s=95, facecolor="none", edgecolor=ORANGE, lw=2, zorder=5)))
        for level, style in marks:
            row = d.iloc[(d["service_level"] - level).abs().argmin()]
            ax.scatter(row["fill_rate"], row["relevant_cost"], **{"lw": 1.5, **style})
        ax.set_title(f"{sku}", loc="left", color=INK, fontsize=11, pad=18)
        ax.text(0, 1.02, f"configured {sl:.3g}   cheapest {best['service_level']:.3g}   "
                f"CSL* {diag[sku]['csl_star']:.2f}", transform=ax.transAxes, fontsize=8, color=INK2)
        ax.set_xlabel("fill rate", color=INK2, fontsize=9)
    axes[0].set_ylabel("mean relevant cost, $", color=INK2, fontsize=9)
    handles = [Line2D([], [], marker="o", ls="", color=BLUE, markersize=8, label="configured service level"),
               Line2D([], [], marker="s", ls="", color=AQUA, markersize=8, label="cheapest level in the sweep"),
               Line2D([], [], marker="D", ls="", markerfacecolor="none", markeredgecolor=ORANGE, markeredgewidth=2,
                      markersize=8, label="CSL* from cost parameters")]
    fig.legend(handles=handles, loc="lower center", ncols=3, frameon=False, fontsize=8, labelcolor=INK2,
               bbox_to_anchor=(0.5, -0.04))
    fig.suptitle("Service-level sweep, full agent: cost against fill rate (each dot is one service level)",
                 x=0.01, ha="left", color=INK, fontsize=12)
    fig.tight_layout()
    return _save(fig, path, close)


# ---------------------------------------------------------------- README results block

def _md_table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def results_markdown(single: dict, summary: pd.DataFrame, deltas: list[dict], diag: dict, mc_seeds: int) -> str:
    parts = []
    rows = [[name, f"{t['TOTAL']['fill_rate']:.3f}", str(t["TOTAL"]["stockout_days"]),
             f"{t['TOTAL']['units_short']:.0f}", f"{t['TOTAL']['holding_cost']:,.2f}",
             f"{t['TOTAL']['stockout_cost']:,.2f}", f"{t['TOTAL']['relevant_cost']:,.2f}", str(t["TOTAL"]["pos"])]
            for name, t in single.items()]
    parts.append("**Committed CSVs, all SKUs, 92 simulated days (K = 0)**\n\n" + _md_table(
        ["policy", "fill rate", "stockout days", "units short", "holding $", "stockout $", "relevant $", "POs"], rows))

    tot = summary[summary["sku"] == "TOTAL"]
    rows = [[r.policy, f"{r.fill_rate_mean:.3f} ({r.fill_rate_p5:.3f}-{r.fill_rate_p95:.3f})",
             f"{r.stockout_days_mean:.1f}", f"{r.relevant_cost_mean:,.0f} ({r.relevant_cost_p5:,.0f}-{r.relevant_cost_p95:,.0f})"]
            for r in tot.itertuples()]
    parts.append(f"**{mc_seeds} demand paths, all SKUs: mean (5th-95th percentile)**\n\n" + _md_table(
        ["policy", "fill rate", "stockout days", "relevant $"], rows))

    rows = [[f"{d['a']} vs {d['b']}", f"{d['mean_delta']:+,.0f}", f"{d['p5']:+,.0f} to {d['p95']:+,.0f}",
             f"{d['share_a_lower']:.0%}"] for d in deltas]
    parts.append("**Paired comparison on the same demand paths (relevant cost, all SKUs)**\n\n" + _md_table(
        ["comparison", "mean difference $", "5th-95th pct", "paths where P3 is cheaper"], rows))

    rows = [[sku, d["demand_class"], f"{d['alpha']:.1f}", str(d["lead_time_days"]), f"{d['service_level']:.2f}",
             f"{d['z']:.2f}", f"{d['sigma1_start']:.2f}", f"{d['ss_start']:.1f}", f"{d['S_start']:.1f}",
             f"{d['csl_star']:.3f}", d["verdict"], f"{d['predicted_fill_rate']:.3f}",
             f"{d['achieved_fill_rate']:.3f}"] for sku, d in diag.items()]
    parts.append("**Safety stock and the cost check, per SKU (full agent, first simulated day)**\n\n" + _md_table(
        ["SKU", "demand class", "alpha", "L", "SL", "z", "sigma_1", "SS", "S", "CSL*", "what the costs say",
         "predicted fill", "achieved fill"], rows))
    return "\n\n".join(parts) + "\n"


def update_readme(readme: str | Path, results: str | Path) -> None:
    """Replace the block between the results markers in README.md with outputs/results.md."""
    readme, start, end = Path(readme), "<!-- results:start -->", "<!-- results:end -->"
    text = readme.read_text(encoding="utf-8")
    before, _, rest = text.partition(start)
    _, _, after = rest.partition(end)
    block = Path(results).read_text(encoding="utf-8")
    readme.write_text(f"{before}{start}\n{block}{end}{after}", encoding="utf-8")
