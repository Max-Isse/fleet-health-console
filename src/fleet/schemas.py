"""The telemetry event contract.

Producers and consumers share this model. Its JSON Schema is committed at contracts/telemetry_event.schema.json
and a contract test fails if the two drift apart, so a breaking change has to be made on purpose.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

SENSOR_FIELDS = [f"s{i}" for i in range(1, 22)]


class Sensors(BaseModel):
    model_config = ConfigDict(extra="forbid")
    s1: float
    s2: float
    s3: float
    s4: float
    s5: float
    s6: float
    s7: float
    s8: float
    s9: float
    s10: float
    s11: float
    s12: float
    s13: float
    s14: float
    s15: float
    s16: float
    s17: float
    s18: float
    s19: float
    s20: float
    s21: float

    @field_validator("*")
    @classmethod
    def finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("sensor values must be finite")
        return v


class OperatingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op_setting_1: float
    op_setting_2: float
    op_setting_3: float


class TelemetryEvent(BaseModel):
    """One sensor reading from one engine at one operating cycle."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    event_id: UUID
    engine_id: int = Field(ge=1)
    cycle: int = Field(ge=1)
    produced_at: datetime
    settings: OperatingSettings
    sensors: Sensors

    def flat(self) -> dict[str, float | int]:
        return {
            "engine_id": self.engine_id,
            "cycle": self.cycle,
            **self.settings.model_dump(),
            **self.sensors.model_dump(),
        }
