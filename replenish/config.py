"""Settled conventions (docs/BRIEF.md section 4). Change a convention here and nowhere else."""

WARMUP_DAYS = 28          # history used to fit the forecaster; the simulation starts on day 28
REVIEW_PERIOD = 1         # R: the agent reviews every day, so the protection interval is P = L + 1
INIT_DAYS = 7             # the EWMA level starts at the mean of the first week of warm-up
ERROR_WINDOW = 28         # trailing window for sigma_1 and the tracking signal
ALPHA_GRID = (0.1, 0.2, 0.3, 0.4, 0.5)

SIGMA_FLOOR_ABS = 0.5     # sigma_1 >= max(0.5, 10% of the forecast) so a calm stretch
SIGMA_FLOOR_REL = 0.10    # can't shrink safety stock to zero

DEFER_TOLERANCE = 0.02    # waiting may cost at most 2 points of cycle service level
MAX_COVER_DAYS = 30       # guardrail: no single PO above 30 days of forecast demand (unless the MOQ requires it)

TS_ALARM_SD = 3.0         # ALERT when |tracking signal| is beyond 3 sd of an unbiased forecast's TS
TS_CALM_SD = 1.0          # stand down once |TS| is back within 1 sd
CALM_DAYS = 7             # for this many days in a row
FAST_ALPHA = 0.5          # smoothing constant while the alarm is on

DEV_SEED0 = 1000          # Monte Carlo seeds used while designing the agent
TEST_SEED0 = 5000         # held-out seeds for the reported results

ADI_CUTOFF = 1.32         # Syntetos-Boylan demand classification
CV2_CUTOFF = 0.49
