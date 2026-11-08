"""Rolling features shared by offline training and online scoring.

The same function runs in both places so there is no training/serving skew. A feature at cycle t uses only
readings at cycles <= t of the same engine (checked in tests/test_features_model.py).

Each window's mean and standard deviation are computed directly from that window's values, not with pandas'
running-sum rolling, whose floating-point error depends on how much history came before. With running sums the
live scorer (which sees only the last `window` readings) disagreed with batch scoring on 4% of rows, by up to 1.7
predicted cycles, because tiny differences flipped tree splits (D-010). Direct computation makes the result
depend only on the window's own values.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view


def feature_names(sensors: list[str]) -> list[str]:
    return ["cycle", *[f"{s}_mean" for s in sensors], *[f"{s}_std" for s in sensors]]


def _window_stats(values: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]:
    """Trailing-window mean (min 1 value) and sample std (min 2 values, else 0) for each row of `values`."""
    padded = np.vstack([np.full((window - 1, values.shape[1]), np.nan), values])
    win = sliding_window_view(padded, window, axis=0)  # (rows, sensors, window)
    present = ~np.isnan(win)
    count = present.sum(axis=2)
    filled = np.where(present, win, 0.0)
    mean = filled.sum(axis=2) / count
    sq = np.where(present, (win - mean[..., None]) ** 2, 0.0).sum(axis=2)
    std = np.where(count >= 2, np.sqrt(sq / np.maximum(count - 1, 1)), 0.0)
    return mean, std


def build_features(readings: pd.DataFrame, sensors: list[str], window: int) -> pd.DataFrame:
    """Return one feature row per (engine_id, cycle) in `readings`, in the same order as the sorted input."""
    df = readings.sort_values(["engine_id", "cycle"]).reset_index(drop=True)
    means = np.empty((len(df), len(sensors)))
    stds = np.empty((len(df), len(sensors)))
    for _, idx in df.groupby("engine_id", sort=False).indices.items():
        m, s = _window_stats(df.loc[idx, sensors].to_numpy(dtype=float), window)
        means[idx], stds[idx] = m, s
    out = df[["engine_id", "cycle"]].copy()
    out[[f"{s}_mean" for s in sensors]] = means
    out[[f"{s}_std" for s in sensors]] = stds
    return out
