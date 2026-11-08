"""Kafka consumer that validates, stores and scores telemetry.

Delivery guarantee: at-least-once from Kafka, made effectively-once in Postgres.

1. Poll a batch with auto-commit off.
2. Validate each message against the contract; invalid ones become dead letters (never block the partition).
3. In ONE database transaction: upsert readings, dead letters, predictions and alerts. Every write is keyed on a
   natural key, so replaying the same messages leaves the database unchanged.
4. Only after the transaction commits, publish dead letters to the DLQ topic and commit the Kafka offsets.

If the process dies between steps 3 and 4 the batch is redelivered (to this consumer or, after a rebalance,
to another one) and the upserts absorb it. The consumer keeps no in-memory state: rolling-window history is read
back from Postgres, so any consumer in the group can take over any partition.
"""

from __future__ import annotations

import json
import logging
import signal
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd
import psycopg
from pydantic import ValidationError

from fleet.config import config, settings
from fleet.data import COLUMNS
from fleet.model import RulModel, risk_band
from fleet.schemas import TelemetryEvent

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RawMessage:
    topic: str
    partition: int
    offset: int
    value: bytes | None


@dataclass
class BatchResult:
    valid: int = 0
    dead_letters: list[dict[str, Any]] = field(default_factory=list)
    predictions: int = 0
    alerts_raised: int = 0


def parse(msg: RawMessage) -> tuple[TelemetryEvent | None, str | None]:
    try:
        payload = json.loads(msg.value or b"")
        return TelemetryEvent.model_validate(payload), None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, f"not valid JSON: {exc}"
    except ValidationError as exc:
        return None, f"contract violation: {exc.error_count()} error(s): {exc.errors()[0]['msg']}"


READING_COLS = [c for c in COLUMNS] + ["event_id", "produced_at", "kafka_partition", "kafka_offset"]
_INSERT_READING = (
    f"INSERT INTO readings ({', '.join(READING_COLS)}) "  # noqa: S608 - fixed column list
    f"VALUES ({', '.join(['%s'] * len(READING_COLS))}) ON CONFLICT (engine_id, cycle) DO NOTHING"
)


def process_batch(conn: psycopg.Connection, messages: list[RawMessage], model: RulModel) -> BatchResult:
    """Validate, store and score one batch inside a single transaction. Safe to call twice on the same batch."""
    result = BatchResult()
    events: list[tuple[TelemetryEvent, RawMessage]] = []
    for msg in messages:
        event, error = parse(msg)
        if event is None:
            payload = (msg.value or b"").decode("utf-8", errors="replace")
            result.dead_letters.append(
                {
                    "topic": msg.topic,
                    "partition": msg.partition,
                    "offset": msg.offset,
                    "error": error,
                    "payload": payload,
                }
            )
        else:
            events.append((event, msg))
    result.valid = len(events)

    with conn.transaction():
        if events:
            rows = [
                (*[e.flat()[c] for c in COLUMNS], e.event_id, e.produced_at, m.partition, m.offset)
                for e, m in events
            ]
            with conn.cursor() as cur:
                cur.executemany(_INSERT_READING, rows)
        if result.dead_letters:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO dead_letters (topic, kafka_partition, kafka_offset, error, payload) "
                    "VALUES (%(topic)s, %(partition)s, %(offset)s, %(error)s, %(payload)s) "
                    "ON CONFLICT (topic, kafka_partition, kafka_offset) DO NOTHING",
                    result.dead_letters,
                )
        if events:
            result.predictions, result.alerts_raised = _score(conn, events, model)
    return result


def _score(
    conn: psycopg.Connection, events: list[tuple[TelemetryEvent, RawMessage]], model: RulModel
) -> tuple[int, int]:
    batch_min: dict[int, int] = {}
    for e, _ in events:
        batch_min[e.engine_id] = min(batch_min.get(e.engine_id, e.cycle), e.cycle)
    engines = list(batch_min)
    # Pull just enough history for the rolling window before the earliest new cycle of each engine.
    from_cycles = [batch_min[e] - model.window + 1 for e in engines]
    rows = conn.execute(
        f"SELECT {', '.join(COLUMNS)} FROM readings r "  # noqa: S608 - fixed column list
        "JOIN unnest(%s::int[], %s::int[]) AS t(eid, from_cycle) "
        "ON r.engine_id = t.eid AND r.cycle >= t.from_cycle",
        (engines, from_cycles),
    ).fetchall()
    history = pd.DataFrame(rows, columns=COLUMNS)
    scored = model.predict_frame(history)
    scored = scored[scored["cycle"] >= scored["engine_id"].map(batch_min)]
    scored["band"] = scored["rul_pred"].map(risk_band)

    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO predictions (engine_id, cycle, rul_pred, band, model_version) VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (engine_id, cycle) DO UPDATE SET rul_pred = EXCLUDED.rul_pred, band = EXCLUDED.band, "
            "model_version = EXCLUDED.model_version",
            [
                (int(r.engine_id), int(r.cycle), float(r.rul_pred), r.band, model.version)
                for r in scored.itertuples(index=False)
            ],
        )
    # First cycle at which each engine entered each non-healthy band raises one alert.
    firsts = (
        scored[scored["band"] != "healthy"]
        .sort_values("cycle")
        .groupby(["engine_id", "band"], as_index=False)
        .first()
    )
    raised = 0
    for r in firsts.itertuples(index=False):
        cur = conn.execute(
            "INSERT INTO alerts (engine_id, band, cycle, rul_pred) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (engine_id, band) DO NOTHING",
            (int(r.engine_id), r.band, int(r.cycle), float(r.rul_pred)),
        )
        raised += cur.rowcount
    return len(scored), raised


def next_offsets(messages: list[RawMessage]) -> dict[tuple[str, int], int]:
    """Offset to commit per (topic, partition): one past the highest offset processed in the batch."""
    out: dict[tuple[str, int], int] = {}
    for m in messages:
        key = (m.topic, m.partition)
        out[key] = max(out.get(key, 0), m.offset + 1)
    return out


# A commit can fail because the group rebalanced while the batch was being processed. The batch is already in
# Postgres, so this is safe to skip: the partition's new owner re-reads from the last committed offset and the
# upserts absorb the repeat (D-002, D-011).
REBALANCE_ERRORS = {"ILLEGAL_GENERATION", "UNKNOWN_MEMBER_ID", "REBALANCE_IN_PROGRESS"}


def commit_offsets(consumer: Any, messages: list[RawMessage]) -> bool:  # pragma: no cover - needs a broker
    from confluent_kafka import KafkaException, TopicPartition

    offsets = [TopicPartition(t, p, o) for (t, p), o in next_offsets(messages).items()]
    try:
        consumer.commit(offsets=offsets, asynchronous=False)
        return True
    except KafkaException as exc:
        if exc.args[0].name() in REBALANCE_ERRORS:
            log.warning(
                "offset commit skipped during rebalance (%s); batch will be redelivered", exc.args[0].name()
            )
            return False
        raise


def run(max_idle_polls: int | None = None) -> None:  # pragma: no cover - exercised by docker compose
    from confluent_kafka import Consumer, Producer

    from fleet import db
    from fleet import model as model_mod

    cfg = config()["kafka"]
    model = model_mod.load()
    conn = db.connect()
    db.init_schema(conn)
    consumer = Consumer(
        {
            "bootstrap.servers": settings().kafka_bootstrap,
            "group.id": cfg["consumer_group"],
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
            "partition.assignment.strategy": "cooperative-sticky",
        }
    )
    dlq = Producer(
        {"bootstrap.servers": settings().kafka_bootstrap, "enable.idempotence": True, "acks": "all"}
    )
    stopping = False

    def _stop(*_: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    consumer.subscribe(
        [cfg["telemetry_topic"]],
        on_assign=lambda c, ps: log.info("assigned %s", [p.partition for p in ps]),
        on_revoke=lambda c, ps: log.info("revoked %s", [p.partition for p in ps]),
    )
    idle = 0
    try:
        while not stopping:
            batch = consumer.consume(num_messages=cfg["poll_batch_size"], timeout=cfg["poll_timeout_s"])
            messages = []
            for m in batch:
                if m.error():
                    log.warning("kafka error: %s", m.error())
                    continue
                messages.append(RawMessage(m.topic(), m.partition(), m.offset(), m.value()))
            if not messages:
                idle += 1
                if max_idle_polls is not None and idle >= max_idle_polls:
                    break
                continue
            idle = 0
            result = process_batch(conn, messages, model)
            for d in result.dead_letters:
                dlq.produce(
                    cfg["dead_letter_topic"],
                    value=d["payload"].encode(),
                    headers={"error": d["error"][:500], "source_offset": f"{d['partition']}:{d['offset']}"},
                )
            dlq.flush(10)
            if not commit_offsets(consumer, messages):
                continue
            log.info(
                "batch: %s valid, %s dead letters, %s scored, %s alerts at %s",
                result.valid,
                len(result.dead_letters),
                result.predictions,
                result.alerts_raised,
                datetime.now().isoformat(timespec="seconds"),
            )
    finally:
        consumer.close()
        conn.close()
