"""Integration tests against a real Postgres: redelivery must not change the database."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from fleet.scorer import RawMessage, process_batch
from tests.conftest import make_event

pytestmark = pytest.mark.db

TABLES = ["readings", "predictions", "alerts", "dead_letters"]


def snapshot(conn) -> dict[str, list]:
    out = {}
    for t in TABLES:
        cols = {
            "readings": "engine_id, cycle, s11",
            "predictions": "engine_id, cycle, round(rul_pred::numeric, 6), band",
            "alerts": "engine_id, band, cycle",
            "dead_letters": "kafka_partition, kafka_offset, error",
        }[t]
        out[t] = conn.execute(f"SELECT {cols} FROM {t} ORDER BY 1, 2, 3").fetchall()  # noqa: S608
    return out


def messages(df: pd.DataFrame, start_offset: int = 0) -> list[RawMessage]:
    return [
        RawMessage(
            "engine-telemetry", int(r.engine_id) % 6, start_offset + i, json.dumps(make_event(row)).encode()
        )
        for i, (r, (_, row)) in enumerate(zip(df.itertuples(), df.iterrows(), strict=True))
    ]


def test_redelivered_batch_changes_nothing(db_conn, small_model, train_small: pd.DataFrame) -> None:
    batch = messages(train_small[train_small["cycle"] <= 150])
    batch.append(RawMessage("engine-telemetry", 0, 99999, b"{not json"))
    first = process_batch(db_conn, batch, small_model)
    assert first.valid == len(batch) - 1 and len(first.dead_letters) == 1
    before = snapshot(db_conn)
    process_batch(db_conn, batch, small_model)  # crash before offset commit -> Kafka redelivers
    assert snapshot(db_conn) == before


def test_incremental_batches_equal_one_big_batch(db_conn, small_model, train_small: pd.DataFrame) -> None:
    """Scoring cycle by cycle (live) must give the same predictions as scoring everything at once."""
    msgs = messages(train_small)
    for cycle in sorted(train_small["cycle"].unique()):
        process_batch(
            db_conn, [m for m, c in zip(msgs, train_small["cycle"], strict=True) if c == cycle], small_model
        )
    incremental = snapshot(db_conn)

    db_conn.execute("TRUNCATE readings, predictions, alerts, dead_letters")
    db_conn.commit()
    process_batch(db_conn, msgs, small_model)
    assert snapshot(db_conn) == incremental


def test_alerts_raised_once_per_band(db_conn, small_model, train_small: pd.DataFrame) -> None:
    msgs = messages(train_small)
    for chunk in range(0, len(msgs), 37):
        process_batch(db_conn, msgs[chunk : chunk + 37], small_model)
    rows = db_conn.execute("SELECT engine_id, band, count(*) AS n FROM alerts GROUP BY 1, 2").fetchall()
    assert rows, "engines run to failure in the training data, so alerts must fire"
    assert all(r["n"] == 1 for r in rows)
    engines_with_critical = {r["engine_id"] for r in rows if r["band"] == "critical"}
    assert engines_with_critical == set(train_small["engine_id"])
