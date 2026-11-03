"""Load and validate the three assignment CSVs, and aggregate sales to a gap-free daily demand table (T1)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SkuParams:
    sku: str
    unit_cost: float
    holding_cost_per_day: float
    stockout_cost: float
    lead_time_days: int
    min_order_qty: int
    service_level: float

    def __post_init__(self):
        if self.lead_time_days < 1:
            raise ValueError(f"{self.sku}: lead_time_days must be >= 1, got {self.lead_time_days}")
        if self.min_order_qty < 1:
            raise ValueError(f"{self.sku}: min_order_qty must be >= 1, got {self.min_order_qty}")
        if not 0 < self.service_level < 1:
            raise ValueError(f"{self.sku}: service_level must be in (0, 1), got {self.service_level}")
        for name in ("unit_cost", "holding_cost_per_day", "stockout_cost"):
            if getattr(self, name) < 0:
                raise ValueError(f"{self.sku}: {name} must be >= 0")

    def with_service_level(self, service_level: float) -> "SkuParams":
        return replace(self, service_level=service_level)


@dataclass
class Dataset:
    demand: pd.DataFrame            # index: every calendar date, columns: SKUs, values: units demanded
    params: dict[str, SkuParams]
    opening: dict[str, int]

    @property
    def skus(self) -> list[str]:
        return list(self.params)

    def series(self, sku: str) -> np.ndarray:
        return self.demand[sku].to_numpy(dtype=float)

    @property
    def dates(self) -> list[str]:
        return [d.strftime("%Y-%m-%d") for d in self.demand.index]


def _require(df: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"{name} is missing columns {missing}; found {list(df.columns)}")


def read_sales(path: str | Path) -> pd.DataFrame:
    sales = pd.read_csv(path)
    _require(sales, ["date", "sku", "qty_sold"], "sales.csv")
    sales["date"] = pd.to_datetime(sales["date"])
    sales["sku"] = sales["sku"].astype(str)
    if (sales["qty_sold"] < 0).any():
        raise ValueError("sales.csv has negative qty_sold")
    return sales


def aggregate_daily(sales: pd.DataFrame, skus: list[str] | None = None) -> pd.DataFrame:
    """Sum order lines per day per SKU, then reindex to the full calendar so missing days read as 0."""
    daily = sales.groupby(["date", "sku"])["qty_sold"].sum().unstack("sku", fill_value=0)
    calendar = pd.date_range(sales["date"].min(), sales["date"].max(), freq="D", name="date")
    columns = list(skus) if skus is not None else sorted(daily.columns)
    daily = daily.reindex(index=calendar, columns=columns, fill_value=0)
    daily.columns.name = "sku"
    return daily.astype(int)


def read_params(path: str | Path) -> dict[str, SkuParams]:
    df = pd.read_csv(path)
    cols = ["sku", "unit_cost", "holding_cost_per_day", "stockout_cost",
            "lead_time_days", "min_order_qty", "service_level"]
    _require(df, cols, "params.csv")
    return {str(r.sku): SkuParams(str(r.sku), float(r.unit_cost), float(r.holding_cost_per_day),
                                  float(r.stockout_cost), int(r.lead_time_days), int(r.min_order_qty),
                                  float(r.service_level))
            for r in df.itertuples(index=False)}


def read_inventory(path: str | Path) -> dict[str, int]:
    df = pd.read_csv(path)
    _require(df, ["sku", "opening_stock"], "inventory.csv")
    return {str(r.sku): int(r.opening_stock) for r in df.itertuples(index=False)}


def load_dataset(data_dir: str | Path = "data") -> Dataset:
    data_dir = Path(data_dir)
    params = read_params(data_dir / "params.csv")
    opening = read_inventory(data_dir / "inventory.csv")
    missing = set(params) - set(opening)
    if missing:
        raise ValueError(f"inventory.csv has no opening_stock for {sorted(missing)}")
    demand = aggregate_daily(read_sales(data_dir / "sales.csv"), skus=list(params))
    return Dataset(demand=demand, params=params, opening={s: opening[s] for s in params})
