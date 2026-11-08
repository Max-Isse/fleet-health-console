"""REST and GraphQL API over the fleet health data product."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel

from fleet.auth import ROLE_ENGINEER, ROLE_VIEWER, Principal, TokenVerifier, require_role
from fleet.config import config, settings
from fleet.graphql_schema import graphql_router

log = logging.getLogger(__name__)

Band = Literal["healthy", "warning", "critical"]


class EngineSummary(BaseModel):
    engine_id: int
    cycle: int
    rul_pred: float
    band: Band
    model_version: str
    scored_at: datetime


class Alert(BaseModel):
    id: int
    engine_id: int
    band: Literal["warning", "critical"]
    cycle: int
    rul_pred: float
    raised_at: datetime
    acknowledged_by: str | None
    acknowledged_at: datetime | None


class EngineDetail(BaseModel):
    engine_id: int
    predictions: list[dict[str, Any]]
    readings: list[dict[str, Any]]
    alerts: list[Alert]


class Me(BaseModel):
    username: str
    roles: list[str]


def create_app(
    repo: Any | None = None,
    verifier: TokenVerifier | None = None,
    status_fn: Callable[[], dict[str, Any]] | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if app.state.repo is None:
            from fleet.db import Repository

            app.state.repo = Repository.from_url()
        if app.state.verifier is None:
            s = settings()
            app.state.verifier = TokenVerifier.from_jwks(s.oidc_issuer, s.oidc_audience, s.oidc_jwks_url)
        yield

    app = FastAPI(
        title="Fleet Health API",
        version="0.1.0",
        description="Live remaining-useful-life predictions for a turbofan fleet. All data routes need an "
        "OIDC bearer token; `viewer` can read, `engineer` can acknowledge alerts.",
        lifespan=lifespan,
    )
    app.state.repo = repo
    app.state.verifier = verifier
    if status_fn is None:
        from fleet.kafka_status import group_status

        status_fn = group_status
    app.state.status_fn = status_fn

    viewer = require_role(ROLE_VIEWER)
    engineer = require_role(ROLE_ENGINEER)

    def repo_dep(request: Request) -> Any:
        return request.app.state.repo

    @app.get("/api/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/me", response_model=Me, tags=["auth"])
    def me(p: Principal = Depends(viewer)) -> Me:
        return Me(username=p.username, roles=sorted(p.roles))

    @app.get("/api/engines", response_model=list[EngineSummary], tags=["fleet"])
    def engines(band: Band | None = None, _: Principal = Depends(viewer), r: Any = Depends(repo_dep)) -> Any:
        return r.list_engines(band)

    @app.get("/api/engines/{engine_id}", response_model=EngineDetail, tags=["fleet"])
    def engine(engine_id: int, _: Principal = Depends(viewer), r: Any = Depends(repo_dep)) -> Any:
        detail = r.engine_history(engine_id, config()["model"]["sensors"])
        if detail is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"engine {engine_id} has no data yet")
        return detail

    @app.get("/api/alerts", response_model=list[Alert], tags=["alerts"])
    def alerts(
        status_: Literal["open", "acknowledged", "all"] = Query("open", alias="status"),
        _: Principal = Depends(viewer),
        r: Any = Depends(repo_dep),
    ) -> Any:
        return r.list_alerts(status=status_)

    @app.post("/api/alerts/{alert_id}/acknowledge", response_model=Alert, tags=["alerts"])
    def acknowledge(alert_id: int, p: Principal = Depends(engineer), r: Any = Depends(repo_dep)) -> Any:
        row = r.acknowledge_alert(alert_id, p.username, datetime.now(UTC))
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"alert {alert_id} not found")
        log.info("alert %s acknowledged by %s", alert_id, p.username)
        return row

    @app.get("/api/pipeline", tags=["ops"])
    def pipeline(
        request: Request, _: Principal = Depends(viewer), r: Any = Depends(repo_dep)
    ) -> dict[str, Any]:
        try:
            kafka = request.app.state.status_fn()
        except Exception as exc:  # noqa: BLE001 - the console should still show database counts
            log.warning("kafka status unavailable: %s", exc)
            kafka = {"error": "Kafka status unavailable"}
        return {"database": r.pipeline_counts(), "kafka": kafka, "dead_letters": r.recent_dead_letters()}

    app.include_router(graphql_router(viewer, repo_dep), prefix="/graphql")
    return app


app = create_app()
