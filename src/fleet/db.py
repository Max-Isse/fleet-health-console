"""Postgres access: schema setup and the read/write repository used by the API.

All SQL is parameterised; no query is built from user input.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from fleet.config import ROOT, settings

SCHEMA_PATH = ROOT / "db" / "schema.sql"


def init_schema(conn: psycopg.Connection, path: Path = SCHEMA_PATH) -> None:
    conn.execute(path.read_text(encoding="utf-8"))
    conn.commit()


def connect(url: str | None = None) -> psycopg.Connection:
    return psycopg.connect(url or settings().database_url, row_factory=dict_row)


class Repository:
    """Read model for the API and GraphQL layer."""

    def __init__(self, pool: ConnectionPool):
        self.pool = pool

    @classmethod
    def from_url(cls, url: str | None = None) -> Repository:
        pool = ConnectionPool(
            url or settings().database_url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        return cls(pool)

    def _all(self, query: str | sql.Composed, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.pool.connection() as conn:
            return list(conn.execute(query, params).fetchall())

    def _one(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.pool.connection() as conn:
            return conn.execute(query, params).fetchone()

    def list_engines(self, band: str | None = None) -> list[dict[str, Any]]:
        rows = self._all(
            """
            SELECT * FROM (
                SELECT DISTINCT ON (engine_id) engine_id, cycle, rul_pred, band, model_version, scored_at
                FROM predictions ORDER BY engine_id, cycle DESC
            ) latest
            WHERE (%s::text IS NULL OR band = %s::text)
            ORDER BY rul_pred ASC, engine_id ASC
            """,
            (band, band),
        )
        return rows

    def engine_history(self, engine_id: int, sensors: list[str]) -> dict[str, Any] | None:
        predictions = self._all(
            "SELECT cycle, rul_pred, band FROM predictions WHERE engine_id = %s ORDER BY cycle", (engine_id,)
        )
        if not predictions:
            return None
        readings: list[dict[str, Any]] = []
        if sensors:
            query = sql.SQL("SELECT cycle, {} FROM readings WHERE engine_id = %s ORDER BY cycle").format(
                sql.SQL(", ").join(sql.Identifier(s) for s in sensors)
            )
            readings = self._all(query, (engine_id,))
        alerts = self.list_alerts(status="all", engine_id=engine_id)
        return {"engine_id": engine_id, "predictions": predictions, "readings": readings, "alerts": alerts}

    def list_alerts(self, status: str = "open", engine_id: int | None = None) -> list[dict[str, Any]]:
        return self._all(
            """
            SELECT id, engine_id, band, cycle, rul_pred, raised_at, acknowledged_by, acknowledged_at
            FROM alerts
            WHERE (%s = 'all'
                   OR (%s = 'open' AND acknowledged_at IS NULL)
                   OR (%s = 'acknowledged' AND acknowledged_at IS NOT NULL))
              AND (%s::int IS NULL OR engine_id = %s::int)
            ORDER BY (band = 'critical') DESC, raised_at DESC
            """,
            (status, status, status, engine_id, engine_id),
        )

    def acknowledge_alert(self, alert_id: int, user: str, when: datetime) -> dict[str, Any] | None:
        """Mark an alert acknowledged. Idempotent: acknowledging twice keeps the first acknowledgement."""
        with self.pool.connection() as conn:
            conn.execute(
                "UPDATE alerts SET acknowledged_by = %s, acknowledged_at = %s "
                "WHERE id = %s AND acknowledged_at IS NULL",
                (user, when, alert_id),
            )
            return conn.execute(
                "SELECT id, engine_id, band, cycle, rul_pred, raised_at, acknowledged_by, acknowledged_at "
                "FROM alerts WHERE id = %s",
                (alert_id,),
            ).fetchone()

    def pipeline_counts(self) -> dict[str, Any]:
        row = self._one(
            """
            SELECT (SELECT count(*) FROM readings)     AS readings,
                   (SELECT count(*) FROM predictions)  AS predictions,
                   (SELECT count(*) FROM dead_letters) AS dead_letters,
                   (SELECT count(*) FROM alerts WHERE acknowledged_at IS NULL) AS open_alerts,
                   (SELECT max(ingested_at) FROM readings) AS last_ingested_at
            """
        )
        return dict(row or {})

    def recent_dead_letters(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._all(
            "SELECT id, kafka_partition, kafka_offset, error, left(payload, 200) AS payload, received_at "
            "FROM dead_letters ORDER BY id DESC LIMIT %s",
            (limit,),
        )
