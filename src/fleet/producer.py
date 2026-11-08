"""Replay NASA C-MAPSS test engines into Kafka as a live telemetry stream.

Each tick sends the next cycle for every engine that still has data, keyed by engine_id so per-engine order is
kept within a partition. The producer is idempotent (acks=all, enable.idempotence) so broker retries cannot
duplicate messages.

SYNTHETIC fault injection (rates in configs/config.yaml): a small share of messages is malformed, to exercise
the dead-letter path, and a small share is deliberately sent twice, to exercise consumer-side deduplication.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from fleet.config import config, settings
from fleet.data import SENSORS, SETTINGS, read_split

log = logging.getLogger(__name__)


def to_event(row: pd.Series, rng: np.random.Generator) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "event_id": str(uuid.UUID(int=int(rng.integers(0, 2**63)) << 64 | int(rng.integers(0, 2**63)))),
        "engine_id": int(row["engine_id"]),
        "cycle": int(row["cycle"]),
        "produced_at": datetime.now(UTC).isoformat(),
        "settings": {s: float(row[s]) for s in SETTINGS},
        "sensors": {s: float(row[s]) for s in SENSORS},
    }


def corrupt(event: dict[str, Any], rng: np.random.Generator) -> bytes:
    """Return one of several realistic malformed payloads (SYNTHETIC)."""
    kind = int(rng.integers(0, 4))
    bad = json.loads(json.dumps(event))
    if kind == 0:
        return b'{"engine_id": ' + str(event["engine_id"]).encode() + b", truncated"
    if kind == 1:
        del bad["sensors"]["s11"]
    elif kind == 2:
        bad["cycle"] = -1
    else:
        bad["sensors"]["s7"] = float("nan")
    return json.dumps(bad).encode()


def plan(test_df: pd.DataFrame, cfg: dict[str, Any], seed: int) -> list[list[tuple[str, bytes]]]:
    """Build the full replay as a list of ticks; each tick is a list of (key, payload)."""
    rng = np.random.default_rng(seed)
    rp = cfg["replay"]
    ticks: list[list[tuple[str, bytes]]] = []
    for _, frame in test_df.sort_values(["cycle", "engine_id"]).groupby("cycle", sort=True):
        tick: list[tuple[str, bytes]] = []
        for _, row in frame.iterrows():
            event = to_event(row, rng)
            key = str(event["engine_id"])
            u = rng.random()
            if u < rp["malformed_rate"]:
                tick.append((key, corrupt(event, rng)))
                tick.append((key, json.dumps(event).encode()))  # the engine re-sends a good reading
            else:
                tick.append((key, json.dumps(event).encode()))
                if u < rp["malformed_rate"] + rp["duplicate_rate"]:
                    tick.append((key, json.dumps(event).encode()))
        ticks.append(tick)
    return ticks


def create_topics() -> None:
    from confluent_kafka.admin import AdminClient, NewTopic

    k = config()["kafka"]
    admin = AdminClient({"bootstrap.servers": settings().kafka_bootstrap})
    futures = admin.create_topics(
        [
            NewTopic(k["telemetry_topic"], num_partitions=k["partitions"], replication_factor=1),
            NewTopic(k["dead_letter_topic"], num_partitions=1, replication_factor=1),
        ]
    )
    for name, fut in futures.items():
        try:
            fut.result()
            log.info("created topic %s", name)
        except Exception as exc:  # noqa: BLE001 - TOPIC_ALREADY_EXISTS is expected on re-runs
            if "TOPIC_ALREADY_EXISTS" not in str(exc):
                raise
            log.info("topic %s already exists", name)


def run(ticks_per_second: float | None = None) -> None:  # pragma: no cover - exercised by docker compose
    from confluent_kafka import Producer

    cfg = config()
    tps = ticks_per_second or cfg["replay"]["ticks_per_second"]
    producer = Producer(
        {
            "bootstrap.servers": settings().kafka_bootstrap,
            "enable.idempotence": True,
            "acks": "all",
            "linger.ms": 20,
            "compression.type": "lz4",
        }
    )
    failures = 0

    def on_delivery(err: object, _msg: object) -> None:
        nonlocal failures
        if err is not None:
            failures += 1
            log.error("delivery failed: %s", err)

    ticks = plan(read_split("test"), cfg, cfg["seed"])
    sent = 0
    for i, tick in enumerate(ticks, start=1):
        start = time.monotonic()
        for key, value in tick:
            producer.produce(cfg["kafka"]["telemetry_topic"], key=key, value=value, on_delivery=on_delivery)
            sent += 1
        producer.poll(0)
        if i % 25 == 0:
            log.info("tick %s/%s, %s messages sent", i, len(ticks), sent)
        time.sleep(max(0.0, 1.0 / tps - (time.monotonic() - start)))
    producer.flush(30)
    log.info("replay finished: %s messages, %s delivery failures", sent, failures)
    if failures:
        raise SystemExit(1)
