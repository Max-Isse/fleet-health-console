"""Consumer-group health for the console: committed offset, end offset and lag per partition, and which
consumer owns which partition."""

from __future__ import annotations

from typing import Any

from fleet.config import config, settings


def group_status(timeout: float = 5.0) -> dict[str, Any]:  # pragma: no cover - needs a broker
    from confluent_kafka import Consumer, ConsumerGroupState, TopicPartition
    from confluent_kafka.admin import AdminClient

    k = config()["kafka"]
    topic, group = k["telemetry_topic"], k["consumer_group"]
    conf = {"bootstrap.servers": settings().kafka_bootstrap}
    admin = AdminClient(conf)
    meta = admin.list_topics(topic, timeout=timeout)
    partitions = sorted(meta.topics[topic].partitions) if topic in meta.topics else []

    owners: dict[int, str] = {}
    state = "UNKNOWN"
    desc = admin.describe_consumer_groups([group])[group].result(timeout=timeout)
    state = desc.state.name if isinstance(desc.state, ConsumerGroupState) else str(desc.state)
    for member in desc.members:
        for tp in member.assignment.topic_partitions:
            if tp.topic == topic:
                owners[tp.partition] = f"{member.client_id}@{member.host.strip('/')}"

    probe = Consumer({**conf, "group.id": group, "enable.auto.commit": False})
    try:
        committed = probe.committed([TopicPartition(topic, p) for p in partitions], timeout=timeout)
        rows = []
        for tp in committed:
            low, high = probe.get_watermark_offsets(TopicPartition(topic, tp.partition), timeout=timeout)
            offset = tp.offset if tp.offset >= 0 else low
            rows.append(
                {
                    "partition": tp.partition,
                    "committed_offset": offset,
                    "end_offset": high,
                    "lag": max(0, high - offset),
                    "owner": owners.get(tp.partition),
                }
            )
    finally:
        probe.close()
    return {
        "topic": topic,
        "group": group,
        "state": state,
        "partitions": rows,
        "total_lag": sum(r["lag"] for r in rows),
    }
