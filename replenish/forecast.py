"""EWMA and naive forecasters, the out-of-sample error tracker, and demand classification (T2, T3)."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

from .config import ADI_CUTOFF, ALPHA_GRID, CV2_CUTOFF, ERROR_WINDOW, INIT_DAYS


class EWMA:
    kind = "ewma"

    def __init__(self, alpha: float, level: float):
        self.alpha = float(alpha)
        self.level = float(level)

    def update(self, demand: float) -> None:
        self.level = self.alpha * demand + (1 - self.alpha) * self.level


class Naive:
    """Tomorrow looks like today."""

    kind = "naive"
    alpha = None

    def __init__(self, level: float):
        self.level = float(level)

    def update(self, demand: float) -> None:
        self.level = float(demand)


def make_forecaster(kind: str, history: np.ndarray, alpha: float | None = None):
    init = np.asarray(history, float)[:INIT_DAYS]
    if kind == "naive":
        return Naive(init[-1])
    if kind == "ewma":
        return EWMA(alpha, init.mean())
    raise ValueError(f"unknown forecaster {kind!r}")


def warm_up(forecaster, history: np.ndarray) -> list[float]:
    """Run the forecaster over the warm-up after its first week.

    Every error is one-step-ahead: the forecast is read before the day's demand is seen.
    """
    errors = []
    for d in np.asarray(history, float)[INIT_DAYS:]:
        errors.append(d - forecaster.level)
        forecaster.update(d)
    return errors


def select_alpha(history: np.ndarray, grid=ALPHA_GRID) -> tuple[float, dict[float, float]]:
    """Pick the smoothing constant with the lowest one-step MSE over the warm-up (ties go to the smaller alpha)."""
    mse = {a: float(np.mean(np.square(warm_up(make_forecaster("ewma", history, a), history)))) for a in grid}
    return min(grid, key=lambda a: (mse[a], a)), mse


class ErrorTracker:
    """Trailing window of one-step forecast errors e_t = D_t - F_t."""

    def __init__(self, errors=(), window: int = ERROR_WINDOW):
        self.errors = deque((float(e) for e in errors), maxlen=window)

    def add(self, error: float) -> None:
        self.errors.append(float(error))

    def rmse(self) -> float:
        n = len(self.errors)
        return math.sqrt(sum(e * e for e in self.errors) / n) if n else 0.0

    def mad(self) -> float:
        n = len(self.errors)
        return sum(abs(e) for e in self.errors) / n if n else 0.0

    def tracking_signal(self) -> float:
        """Sum of errors over MAD. Positive means demand keeps beating the forecast."""
        mad = self.mad()
        return sum(self.errors) / mad if mad > 0 else 0.0


def tracking_signal_sd(alpha: float, n: int) -> float:
    """Spread of the tracking signal over n errors when an EWMA forecast is unbiased.

    EWMA telescopes: F_{t+1} = F_t + alpha*e_t, so the sum of n errors is (F_end - F_start)/alpha.
    For i.i.d. normal demand that gives sd(TS) = sqrt(pi * (1 - (1-alpha)^n) / (2*alpha)),
    about 3.9 for alpha = 0.1 over 28 days. A fixed +/-4 limit would fire on noise a third of the time.
    """
    return math.sqrt(math.pi * (1 - (1 - alpha) ** n) / (2 * alpha))


@dataclass(frozen=True)
class DemandClass:
    adi: float      # average days between nonzero demands
    cv2: float      # squared coefficient of variation of nonzero demand sizes
    label: str      # smooth | erratic | intermittent | lumpy


def classify_demand(history: np.ndarray) -> DemandClass:
    history = np.asarray(history, float)
    sizes = history[history > 0]
    if len(sizes) == 0:
        return DemandClass(math.inf, math.nan, "no demand")
    adi = len(history) / len(sizes)
    cv2 = float((sizes.std() / sizes.mean()) ** 2)
    if adi < ADI_CUTOFF:
        label = "smooth" if cv2 < CV2_CUTOFF else "erratic"
    else:
        label = "intermittent" if cv2 < CV2_CUTOFF else "lumpy"
    return DemandClass(adi, cv2, label)
