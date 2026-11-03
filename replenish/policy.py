"""Safety stock, the order-up-to level, the priced defer test, and the cost diagnostics (T3, T4).

Scalar normal functions use math.erf instead of scipy so a 200-seed Monte Carlo stays fast.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

from .config import DEFER_TOLERANCE, MAX_COVER_DAYS, REVIEW_PERIOD, SIGMA_FLOOR_ABS, SIGMA_FLOOR_REL
from .data import SkuParams

_SQRT2 = math.sqrt(2.0)
_SQRT2PI = math.sqrt(2.0 * math.pi)
NAN = float("nan")


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT2PI


def normal_loss(k: float) -> float:
    """Standard normal loss G(k) = E[(Z - k)+] = phi(k) - k * (1 - Phi(k))."""
    return norm_pdf(k) - k * (1.0 - norm_cdf(k))


def z_value(service_level: float) -> float:
    return NormalDist().inv_cdf(service_level)


def expected_shortage(ip: float, mu: float, sigma: float) -> float:
    """E[(D - ip)+] for D ~ Normal(mu, sigma)."""
    if sigma <= 0:
        return max(mu - ip, 0.0)
    return sigma * normal_loss((ip - mu) / sigma)


def sigma_floor(level: float) -> float:
    return max(SIGMA_FLOOR_ABS, SIGMA_FLOOR_REL * level)


@dataclass(frozen=True)
class Plan:
    action: str                 # HOLD | ORDER | DEFER
    qty: int
    mu_P: float
    sigma_P: float
    z: float
    ss: float
    S: float
    gap: float = 0.0
    candidate: int = 0          # what an order would be: max(MOQ, ceil(gap)), within the cap
    moq_binds: bool = False
    capped: bool = False        # the over-ordering guardrail trimmed the order
    csl_wait: float = NAN
    d_es: float = NAN
    wait_cost: float = NAN
    hold_saved: float = NAN
    floor: float = NAN


def plan_order(ip: float, level: float, sigma1: float, params: SkuParams, *, defer: bool = True,
               tolerance: float = DEFER_TOLERANCE, z: float | None = None,
               max_cover_days: float = MAX_COVER_DAYS) -> Plan:
    """One review: compare inventory position with S over the protection interval P = L + R.

    Below S, the agent prices waiting one more day. The order it would place today lands on
    day t+L; tomorrow's would land on t+L+1. So waiting exposes day t+L, and the expected extra
    units short is ES over P days minus ES over L days.

    Guardrails: the order never goes below min_order_qty, and never above max_cover_days of
    forecast demand unless the MOQ alone requires it.
    """
    L = params.lead_time_days
    P = L + REVIEW_PERIOD
    z = z_value(params.service_level) if z is None else z
    mu_P, sigma_P = level * P, sigma1 * math.sqrt(P)
    ss = z * sigma_P
    S = mu_P + ss
    if ip >= S:
        return Plan("HOLD", 0, mu_P, sigma_P, z, ss, S)

    gap = S - ip
    need = math.ceil(gap - 1e-9)
    cap = max(params.min_order_qty, math.ceil(max_cover_days * level))
    q = min(max(params.min_order_qty, need), cap)
    mu_L, sigma_L = level * L, sigma1 * math.sqrt(L)
    csl_wait = norm_cdf((ip - mu_P) / sigma_P) if sigma_P > 0 else float(ip >= mu_P)
    d_es = expected_shortage(ip, mu_P, sigma_P) - expected_shortage(ip, mu_L, sigma_L)
    wait_cost = params.stockout_cost * d_es
    hold_saved = params.holding_cost_per_day * q
    floor = params.service_level - tolerance
    wait = defer and wait_cost < hold_saved and csl_wait >= floor
    return Plan("DEFER" if wait else "ORDER", 0 if wait else q, mu_P, sigma_P, z, ss, S,
                gap=gap, candidate=q, moq_binds=q > need, capped=q < need, csl_wait=csl_wait, d_es=d_es,
                wait_cost=wait_cost, hold_saved=hold_saved, floor=floor)


def economic_csl(params: SkuParams, mean_demand: float, mean_order: float) -> tuple[float, float]:
    """CSL* = 1 - h*T/p, with T = max(R, Qbar/mu) the order-cycle length in days.

    One more unit of S is carried for the whole cycle (cost h*T) and avoids one unit short with
    probability P(stockout in the cycle) (saves p). Report-only: it never overrides service_level.
    """
    T = max(REVIEW_PERIOD, mean_order / mean_demand) if mean_demand > 0 else math.inf
    if params.stockout_cost <= 0:
        return 0.0, T
    return 1.0 - params.holding_cost_per_day * T / params.stockout_cost, T


def predicted_fill_rate(sigma_P: float, z: float, mean_order: float) -> float:
    """Fill rate implied by a CSL target: 1 - expected units short per cycle / units per cycle."""
    if mean_order <= 0:
        return NAN
    return 1.0 - sigma_P * normal_loss(z) / mean_order
