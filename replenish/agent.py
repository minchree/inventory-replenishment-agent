"""The replenishment agent and the two reference policies that share its interface.

Every policy exposes decide(obs) -> DecisionRecord and learn(demand). The simulator calls
decide at the daily review (before demand) and learn after the day's demand is known, so a
decision on day t can only see demand through day t-1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .config import CALM_DAYS, DEFER_TOLERANCE, FAST_ALPHA, REVIEW_PERIOD, TS_ALARM_SD, TS_CALM_SD
from .data import SkuParams
from .forecast import (ErrorTracker, classify_demand, make_forecaster, select_alpha, tracking_signal_sd,
                       warm_up)
from .policy import NAN, plan_order, sigma_floor, z_value


@dataclass(frozen=True)
class Obs:
    """What the agent sees at its review: state after today's receipts, before today's demand."""
    t: int                  # index into the simulated horizon
    day: int                # absolute day number in the dataset (warm-up included)
    date: str
    on_hand: float
    on_order: float
    backorders: float

    @property
    def ip(self) -> float:
        return self.on_hand + self.on_order - self.backorders


@dataclass
class Memory:
    base_alpha: float | None
    fast_mode: bool = False
    calm_days: int = 0
    alerts: int = 0
    last_action: str | None = None


@dataclass
class DecisionRecord:
    """One review, with every number the rationale quotes. The log text is rendered from this."""
    day: int
    date: str
    sku: str
    rule: str               # agent | static | clairvoyant
    action: str             # HOLD | ORDER | DEFER
    qty: int
    on_hand: float
    on_order: float
    backorders: float
    ip: float
    forecast: float
    alpha: float
    sigma1: float
    tracking_signal: float
    mu_P: float
    sigma_P: float
    z: float
    ss: float
    S: float
    gap: float = 0.0
    candidate: int = 0
    moq_binds: bool = False
    capped: bool = False
    csl_wait: float = NAN
    d_es: float = NAN
    wait_cost: float = NAN
    hold_saved: float = NAN
    floor: float = NAN
    defer_enabled: bool = False
    alert: str = ""


class ReplenishmentAgent:
    """Perceive -> forecast -> plan -> act -> reflect, once per day."""

    rule = "agent"

    def __init__(self, sku: str, params: SkuParams, history: np.ndarray, *, forecaster: str = "ewma",
                 alpha: float | None = None, defer: bool = True, reflect: bool = True,
                 tolerance: float = DEFER_TOLERANCE):
        """alpha=None picks the smoothing constant from the warm-up; a number fixes it."""
        history = np.asarray(history, float)
        self.sku, self.params = sku, params
        self.defer, self.reflect, self.tolerance = defer, reflect, tolerance
        if forecaster != "ewma":
            alpha, self.alpha_mse = None, {}
        elif alpha is None:
            alpha, self.alpha_mse = select_alpha(history)
        else:
            self.alpha_mse = {}
        self.forecaster = make_forecaster(forecaster, history, alpha)
        self.tracker = ErrorTracker(warm_up(self.forecaster, history))
        self.memory = Memory(base_alpha=alpha)
        self.demand_class = classify_demand(history)
        self.z = z_value(params.service_level)

    def sigma1(self) -> float:
        return max(self.tracker.rmse(), sigma_floor(self.forecaster.level))

    def decide(self, obs: Obs) -> DecisionRecord:
        alert = self._reflect()
        level, s1 = self.forecaster.level, self.sigma1()
        plan = plan_order(obs.ip, level, s1, self.params, defer=self.defer,
                          tolerance=self.tolerance, z=self.z)
        self.memory.last_action = plan.action
        alpha = self.forecaster.alpha if self.forecaster.alpha is not None else NAN
        return DecisionRecord(
            day=obs.day, date=obs.date, sku=self.sku, rule=self.rule, action=plan.action, qty=plan.qty,
            on_hand=obs.on_hand, on_order=obs.on_order, backorders=obs.backorders, ip=obs.ip,
            forecast=level, alpha=alpha, sigma1=s1, tracking_signal=self.tracker.tracking_signal(),
            mu_P=plan.mu_P, sigma_P=plan.sigma_P, z=plan.z, ss=plan.ss, S=plan.S, gap=plan.gap,
            candidate=plan.candidate, moq_binds=plan.moq_binds, capped=plan.capped, csl_wait=plan.csl_wait,
            d_es=plan.d_es, wait_cost=plan.wait_cost, hold_saved=plan.hold_saved, floor=plan.floor,
            defer_enabled=self.defer, alert=alert)

    def learn(self, demand: float) -> None:
        self.tracker.add(demand - self.forecaster.level)
        self.forecaster.update(demand)

    @property
    def reflect_active(self) -> bool:
        """Reflect only on smooth or erratic demand: on intermittent demand most errors are the
        zero days themselves, so the tracking signal measures sparsity, not bias."""
        return (self.reflect and self.memory.base_alpha is not None
                and self.demand_class.label in ("smooth", "erratic"))

    def _reflect(self) -> str:
        """Watch forecast bias; speed the forecast up while it's biased, then stand down."""
        m = self.memory
        if not self.reflect_active:
            return ""
        ts = self.tracker.tracking_signal()
        sd = tracking_signal_sd(self.forecaster.alpha, len(self.tracker.errors))
        if not m.fast_mode:
            if abs(ts) <= TS_ALARM_SD * sd:
                return ""
            m.fast_mode, m.calm_days, m.alerts = True, 0, m.alerts + 1
            self.forecaster.alpha = FAST_ALPHA
            direction = "running low" if ts > 0 else "running high"
            return (f"TS={ts:+.2f} beyond {TS_ALARM_SD:.0f} sd of an unbiased forecast (+/-{TS_ALARM_SD * sd:.1f}),"
                    f" forecast {direction} -> alpha {m.base_alpha:.2f} -> {FAST_ALPHA:.2f}")
        m.calm_days = m.calm_days + 1 if abs(ts) < TS_CALM_SD * sd else 0
        if m.calm_days < CALM_DAYS:
            return ""
        m.fast_mode = False
        self.forecaster.alpha = m.base_alpha
        return (f"TS={ts:+.2f} within {TS_CALM_SD:.0f} sd (+/-{TS_CALM_SD * sd:.1f}) for {CALM_DAYS} days"
                f" -> alpha back to {m.base_alpha:.2f}")


class StaticReorderPolicy:
    """P0, the starter's static (s, Q) run through our simulator.

    s = L*mu + z*sqrt(L)*sigma_raw from warm-up demand (as in the starter); Q = max(MOQ, EOQ).
    """

    rule = "static"

    def __init__(self, sku: str, params: SkuParams, history: np.ndarray, order_cost: float = 0.0):
        history = np.asarray(history, float)
        self.sku, self.params = sku, params
        self.mu, self.sigma = float(history.mean()), float(history.std(ddof=1))
        L = params.lead_time_days
        self.z = z_value(params.service_level)
        self.mu_L, self.sigma_L = L * self.mu, math.sqrt(L) * self.sigma
        self.s = self.mu_L + self.z * self.sigma_L
        h = params.holding_cost_per_day
        eoq = math.sqrt(2 * order_cost * self.mu / h) if order_cost > 0 and h > 0 else 0.0
        # EOQ grows without bound as h -> 0; past a year of demand it means nothing, so cap it there
        self.q = max(params.min_order_qty, math.ceil(min(eoq, 365 * self.mu)))

    def decide(self, obs: Obs) -> DecisionRecord:
        order = obs.ip <= self.s
        return DecisionRecord(
            day=obs.day, date=obs.date, sku=self.sku, rule=self.rule, action="ORDER" if order else "HOLD",
            qty=self.q if order else 0, on_hand=obs.on_hand, on_order=obs.on_order, backorders=obs.backorders,
            ip=obs.ip, forecast=self.mu, alpha=NAN, sigma1=self.sigma, tracking_signal=NAN,
            mu_P=self.mu_L, sigma_P=self.sigma_L, z=self.z, ss=self.z * self.sigma_L, S=self.s,
            gap=max(self.s - obs.ip, 0.0))

    def learn(self, demand: float) -> None:
        pass


class ClairvoyantPolicy:
    """P4, a reference point: knows the true demand of the next P days and carries no safety stock."""

    rule = "clairvoyant"

    def __init__(self, sku: str, params: SkuParams, future: np.ndarray):
        self.sku, self.params = sku, params
        self.future = np.asarray(future, float)

    def decide(self, obs: Obs) -> DecisionRecord:
        P = self.params.lead_time_days + REVIEW_PERIOD
        S = float(self.future[obs.t: obs.t + P].sum())
        gap = S - obs.ip
        order = gap > 0
        need = math.ceil(gap - 1e-9) if order else 0
        qty = max(self.params.min_order_qty, need) if order else 0
        return DecisionRecord(
            day=obs.day, date=obs.date, sku=self.sku, rule=self.rule, action="ORDER" if order else "HOLD",
            qty=qty, on_hand=obs.on_hand, on_order=obs.on_order, backorders=obs.backorders, ip=obs.ip,
            forecast=float(self.future[obs.t]), alpha=NAN, sigma1=0.0, tracking_signal=NAN,
            mu_P=S, sigma_P=0.0, z=NAN, ss=0.0, S=S, gap=max(gap, 0.0), moq_binds=order and qty > need)

    def learn(self, demand: float) -> None:
        pass
