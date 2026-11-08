"""Train, evaluate, save and load the remaining-useful-life (RUL) model.

The model is deliberately simple (gradient-boosted trees on rolling sensor statistics). This repository is about
getting a model into a live, governed data product; the modelling depth lives in cmapss-predictive-maintenance.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from fleet.config import config, settings
from fleet.features import build_features, feature_names

log = logging.getLogger(__name__)


def rul_target(df: pd.DataFrame, cap: int) -> pd.Series:
    """Piecewise-linear RUL: cycles left until the engine's last recorded cycle, capped at `cap`."""
    last = df.groupby("engine_id")["cycle"].transform("max")
    return (last - df["cycle"]).clip(upper=cap)


def risk_band(rul_pred: float, bands: dict[str, int] | None = None) -> str:
    bands = bands or config()["risk_bands"]
    if rul_pred < bands["critical_below"]:
        return "critical"
    if rul_pred < bands["warning_below"]:
        return "warning"
    return "healthy"


@dataclass
class RulModel:
    estimator: HistGradientBoostingRegressor
    sensors: list[str]
    window: int
    cap: int
    version: str

    def predict_frame(self, readings: pd.DataFrame) -> pd.DataFrame:
        """Score every (engine_id, cycle) in `readings`. Returns engine_id, cycle, rul_pred."""
        feats = build_features(readings, self.sensors, self.window)
        pred = self.estimator.predict(feats[feature_names(self.sensors)])
        out = feats[["engine_id", "cycle"]].copy()
        out["rul_pred"] = np.clip(pred, 0.0, float(self.cap))
        return out


def train(train_df: pd.DataFrame, cfg: dict[str, Any] | None = None) -> RulModel:
    cfg = cfg or config()
    m = cfg["model"]
    feats = build_features(train_df, m["sensors"], m["window"])
    y = rul_target(train_df.sort_values(["engine_id", "cycle"]).reset_index(drop=True), m["rul_cap"])
    est = HistGradientBoostingRegressor(random_state=cfg["seed"], **m["params"])
    est.fit(feats[feature_names(m["sensors"])], y)
    return RulModel(est, list(m["sensors"]), int(m["window"]), int(m["rul_cap"]), m["version"])


def evaluate(model: RulModel, test_df: pd.DataFrame, true_rul: pd.Series) -> dict[str, float]:
    """RMSE at each test engine's last observed cycle against NASA's true RUL (capped like the target)."""
    scored = model.predict_frame(test_df)
    last = scored.loc[scored.groupby("engine_id")["cycle"].idxmax()].set_index("engine_id")["rul_pred"]
    truth = true_rul.loc[last.index].clip(upper=model.cap)
    rmse = float(np.sqrt(np.mean((last - truth) ** 2)))
    baseline = float(np.sqrt(np.mean((truth.mean() - truth) ** 2)))
    return {
        "rmse_last_cycle": round(rmse, 2),
        "rmse_mean_baseline": round(baseline, 2),
        "n_engines": int(len(last)),
    }


def model_path() -> Path:
    return settings().artifacts_dir / "rul_model.joblib"


def save(model: RulModel, metrics: dict[str, float]) -> Path:
    path = model_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    meta = {"version": model.version, "metrics": metrics}
    (path.parent / "model_metrics.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    log.info("saved model %s to %s: %s", model.version, path, metrics)
    return path


def load() -> RulModel:
    return joblib.load(model_path())  # noqa: S301 - artifact produced by this pipeline, not user input
