"""Feature definition shared by daily model training and inference."""

from statistics import mean, pstdev

from .replay.models import ResearchError

LOOKBACK_SESSIONS = 20
FEATURE_NAMES = (
    "openToClose", "closeReturn1", "closeReturn5", "closeReturn20",
    "rangeOverOpen", "closeVolatility20", "volumeRatio20",
)


def daily_features(window):
    """Compute the seven features from T-20 through T, inclusive."""
    if len(window) != LOOKBACK_SESSIONS + 1:
        raise ResearchError("DAILY_LEARNING_INVALID_LOOKBACK")
    today = window[-1]
    returns = [right.closed / left.closed - 1 for left, right in zip(window, window[1:])]
    return (
        today.closed / today.opened - 1,
        returns[-1],
        today.closed / window[-6].closed - 1,
        today.closed / window[0].closed - 1,
        (today.high - today.low) / today.opened,
        pstdev(returns),
        today.volume / mean(bar.volume for bar in window[:-1]),
    )
