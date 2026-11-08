"""Contract tests: the event schema producers and consumers share."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from fleet.cli import CONTRACT_PATH, _contract
from fleet.producer import corrupt, plan
from fleet.schemas import TelemetryEvent
from fleet.scorer import RawMessage, parse
from tests.conftest import make_event


def test_committed_contract_matches_code() -> None:
    """Fails if the model changes without regenerating contracts/ (run `fleet contract` on purpose)."""
    assert json.loads(CONTRACT_PATH.read_text(encoding="utf-8")) == json.loads(_contract())


def test_valid_event_round_trips(train_small: pd.DataFrame) -> None:
    event = make_event(train_small.iloc[0])
    parsed = TelemetryEvent.model_validate(event)
    assert parsed.flat()["s11"] == event["sensors"]["s11"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e["sensors"].pop("s2"),
        lambda e: e.update(cycle=0),
        lambda e: e.update(engine_id=-3),
        lambda e: e["sensors"].update(s9=float("inf")),
        lambda e: e.update(schema_version=2),
        lambda e: e.update(unexpected="field"),
    ],
)
def test_contract_rejects_bad_events(train_small: pd.DataFrame, mutate) -> None:
    event = make_event(train_small.iloc[0])
    mutate(event)
    with pytest.raises(ValidationError):
        TelemetryEvent.model_validate(event)


def test_every_injected_fault_is_caught(train_small: pd.DataFrame) -> None:
    rng = np.random.default_rng(0)
    event = make_event(train_small.iloc[0])
    for _ in range(40):
        bad = corrupt(event, rng)
        parsed, error = parse(RawMessage("t", 0, 0, bad))
        assert parsed is None and error


def test_replay_plan_keeps_per_engine_order_and_injects_faults(train_small: pd.DataFrame) -> None:
    cfg = {"replay": {"malformed_rate": 0.05, "duplicate_rate": 0.05}}
    ticks = plan(train_small, cfg, seed=1)
    good: dict[str, list[int]] = {}
    bad = 0
    for tick in ticks:
        for key, payload in tick:
            event, error = parse(RawMessage("t", 0, 0, payload))
            if event is None:
                bad += 1
                continue
            assert key == str(event.engine_id)
            good.setdefault(key, []).append(event.cycle)
    assert bad > 0
    for cycles in good.values():
        assert cycles == sorted(cycles)  # ordered per engine (duplicates repeat in place)
    assert sum(len(set(c)) for c in good.values()) == len(train_small)  # every reading delivered


def test_commit_offsets_are_one_past_the_highest_per_partition() -> None:
    from fleet.scorer import next_offsets

    msgs = [RawMessage("t", 0, 5, b""), RawMessage("t", 0, 9, b""), RawMessage("t", 3, 2, b"")]
    assert next_offsets(msgs) == {("t", 0): 10, ("t", 3): 3}
