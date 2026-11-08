from __future__ import annotations

import numpy as np
import pandas as pd

from fleet.config import config
from fleet.features import build_features, feature_names
from fleet.model import risk_band, rul_target

SENSORS = config()["model"]["sensors"]
WINDOW = config()["model"]["window"]


def test_features_use_only_past_readings(train_small: pd.DataFrame) -> None:
    """Changing a future reading must not change any earlier feature row (no look-ahead leakage)."""
    base = build_features(train_small, SENSORS, WINDOW)
    tampered = train_small.copy()
    future = (tampered["engine_id"] == 1) & (tampered["cycle"] > 50)
    tampered.loc[future, SENSORS] *= 10
    after = build_features(tampered, SENSORS, WINDOW)
    past = (base["engine_id"] == 1) & (base["cycle"] <= 50)
    pd.testing.assert_frame_equal(base[past], after[past])


def test_features_do_not_mix_engines(train_small: pd.DataFrame) -> None:
    both = build_features(train_small, SENSORS, WINDOW)
    alone = build_features(train_small[train_small["engine_id"] == 2], SENSORS, WINDOW)
    np.testing.assert_allclose(
        both[both["engine_id"] == 2][feature_names(SENSORS)].to_numpy(),
        alone[feature_names(SENSORS)].to_numpy(),
    )


def test_online_features_match_offline(train_small: pd.DataFrame) -> None:
    """Online scoring sees only the last `window` readings; its feature must equal the offline one."""
    offline = build_features(train_small, SENSORS, WINDOW)
    engine = train_small[train_small["engine_id"] == 3]
    t = 120
    tail = engine[(engine["cycle"] > t - WINDOW) & (engine["cycle"] <= t)]
    online = build_features(tail, SENSORS, WINDOW).iloc[-1]
    expected = offline[(offline["engine_id"] == 3) & (offline["cycle"] == t)].iloc[0]
    np.testing.assert_allclose(
        online[feature_names(SENSORS)].astype(float), expected[feature_names(SENSORS)].astype(float)
    )


def test_rul_target_is_capped_and_reaches_zero(train_small: pd.DataFrame) -> None:
    y = rul_target(train_small, cap=125)
    assert y.max() == 125
    assert (y.groupby(train_small["engine_id"]).min() == 0).all()


def test_risk_bands() -> None:
    bands = {"critical_below": 20, "warning_below": 50}
    assert risk_band(5, bands) == "critical"
    assert risk_band(20, bands) == "warning"
    assert risk_band(49.9, bands) == "warning"
    assert risk_band(50, bands) == "healthy"


def test_model_predictions_are_bounded(small_model, train_small: pd.DataFrame) -> None:
    scored = small_model.predict_frame(train_small)
    assert len(scored) == len(train_small)
    assert scored["rul_pred"].between(0, small_model.cap).all()
    # Predicted RUL should fall as engines age.
    first, last = (
        scored.groupby("engine_id")["rul_pred"].first(),
        scored.groupby("engine_id")["rul_pred"].last(),
    )
    assert (last < first).all()
