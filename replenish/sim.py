"""Day-by-day simulation with a lead-time pipeline and a cost ledger (T5).

One day, in order (docs/BRIEF.md 4.1):
  1. receive POs due today
  2. review: the policy sees on-hand, on-order, backorders and may place a PO due on day t+L
  3. demand arrives; backorders are served first, then today's demand; record filled and short
  4. book costs: holding on end-of-day on-hand, stockout cost once per unit short, K per PO
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .agent import DecisionRecord, Obs
from .data import SkuParams

LEDGER_FIELDS = ("day", "on_hand_start", "received", "demand", "shipped", "filled", "short",
                 "backorders", "on_hand_end", "on_order_end", "ordered",
                 "holding_cost", "stockout_cost", "order_cost", "purchase_cost")


@dataclass(frozen=True)
class SimConfig:
    order_cost: float = 0.0         # K, fixed cost per PO
    shortage: str = "backorder"     # backorder | lost_sales

    def __post_init__(self):
        if self.shortage not in ("backorder", "lost_sales"):
            raise ValueError(f"shortage must be 'backorder' or 'lost_sales', got {self.shortage!r}")


@dataclass
class SkuRun:
    sku: str
    params: SkuParams
    ledger: dict[str, np.ndarray]
    decisions: list[DecisionRecord]
    dates: list[str]
    policy: object = field(default=None, repr=False)

    def frame(self) -> pd.DataFrame:
        df = pd.DataFrame(self.ledger)
        df.insert(1, "date", self.dates)
        df.insert(2, "sku", self.sku)
        df["action"] = [r.action for r in self.decisions]
        return df


def simulate_sku(sku: str, demand: np.ndarray, params: SkuParams, opening: float, policy, *,
                 start_day: int = 0, dates: list[str] | None = None,
                 config: SimConfig = SimConfig()) -> SkuRun:
    demand = np.asarray(demand, float)
    dates = list(dates) if dates is not None else [f"day {start_day + t}" for t in range(len(demand))]
    L = params.lead_time_days
    h, p, c = params.holding_cost_per_day, params.stockout_cost, params.unit_cost
    pipeline: dict[int, int] = {}
    on_hand, backorders = float(opening), 0.0
    cols = {f: [] for f in LEDGER_FIELDS}
    decisions = []

    for t, d in enumerate(demand):
        on_hand_start = on_hand
        received = pipeline.pop(t, 0)
        on_hand += received

        obs = Obs(t=t, day=start_day + t, date=dates[t], on_hand=on_hand,
                  on_order=float(sum(pipeline.values())), backorders=backorders)
        rec = policy.decide(obs)
        decisions.append(rec)
        ordered = int(rec.qty) if rec.action == "ORDER" else 0
        if ordered > 0:
            pipeline[t + L] = pipeline.get(t + L, 0) + ordered

        cleared = min(on_hand, backorders)
        on_hand -= cleared
        backorders -= cleared
        filled = min(on_hand, d)
        on_hand -= filled
        short = d - filled
        if config.shortage == "backorder":
            backorders += short
        policy.learn(d)

        for name, value in (("day", start_day + t), ("on_hand_start", on_hand_start), ("received", received),
                            ("demand", d), ("shipped", cleared + filled), ("filled", filled), ("short", short),
                            ("backorders", backorders), ("on_hand_end", on_hand),
                            ("on_order_end", sum(pipeline.values())), ("ordered", ordered),
                            ("holding_cost", h * on_hand), ("stockout_cost", p * short),
                            ("order_cost", config.order_cost if ordered else 0.0),
                            ("purchase_cost", c * received)):
            cols[name].append(value)

    ledger = {k: np.asarray(v, float) for k, v in cols.items()}
    return SkuRun(sku, params, ledger, decisions, dates, policy)
