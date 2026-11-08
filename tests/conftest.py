from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from fleet.config import config
from fleet.data import SENSORS, SETTINGS, read_cmapss

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def train_small() -> pd.DataFrame:
    return read_cmapss(FIXTURES / "train_FD001_engines1-4.txt")


@pytest.fixture(scope="session")
def small_model(train_small: pd.DataFrame):
    from fleet.model import train

    cfg = json.loads(json.dumps(config()))
    cfg["model"]["params"]["max_iter"] = 50
    return train(train_small, cfg)


def make_event(row: pd.Series) -> dict:
    return {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "engine_id": int(row["engine_id"]),
        "cycle": int(row["cycle"]),
        "produced_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
        "settings": {s: float(row[s]) for s in SETTINGS},
        "sensors": {s: float(row[s]) for s in SENSORS},
    }


@pytest.fixture
def db_conn():
    """A clean Postgres schema per test. Skips locally when no database is configured."""
    url = os.environ.get("FLEET_TEST_DATABASE_URL")
    if not url:
        pytest.skip("set FLEET_TEST_DATABASE_URL to run database tests")
    from fleet import db

    conn = db.connect(url)
    conn.execute("DROP TABLE IF EXISTS readings, predictions, alerts, dead_letters CASCADE")
    db.init_schema(conn)
    yield conn
    conn.close()
