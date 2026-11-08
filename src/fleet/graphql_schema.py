"""Read-only GraphQL view of the fleet, for clients that want one round trip for an engine and its history.

It uses the same repository and the same `viewer` role check as the REST API.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

import strawberry
from fastapi import Depends
from strawberry.fastapi import GraphQLRouter
from strawberry.types import Info

from fleet.auth import Principal


@strawberry.type
class Prediction:
    cycle: int
    rul_pred: float
    band: str


@strawberry.type
class AlertType:
    id: int
    band: str
    cycle: int
    rul_pred: float
    raised_at: datetime
    acknowledged_by: str | None


@strawberry.type
class Engine:
    engine_id: int
    cycle: int
    rul_pred: float
    band: str

    @strawberry.field
    def history(self, info: Info, last: int = 50) -> list[Prediction]:
        detail = info.context["repo"].engine_history(self.engine_id, [])
        rows = (detail or {}).get("predictions", [])[-last:]
        return [Prediction(cycle=r["cycle"], rul_pred=r["rul_pred"], band=r["band"]) for r in rows]

    @strawberry.field
    def alerts(self, info: Info) -> list[AlertType]:
        rows = info.context["repo"].list_alerts(status="all", engine_id=self.engine_id)
        return [
            AlertType(
                **{k: r[k] for k in ("id", "band", "cycle", "rul_pred", "raised_at", "acknowledged_by")}
            )
            for r in rows
        ]


def _engine(row: dict[str, Any]) -> Engine:
    return Engine(engine_id=row["engine_id"], cycle=row["cycle"], rul_pred=row["rul_pred"], band=row["band"])


@strawberry.type
class Query:
    @strawberry.field(description="Latest prediction per engine, most at-risk first.")
    def engines(self, info: Info, band: str | None = None, limit: int = 100) -> list[Engine]:
        return [_engine(r) for r in info.context["repo"].list_engines(band)[:limit]]

    @strawberry.field
    def engine(self, info: Info, engine_id: int) -> Engine | None:
        row = next((r for r in info.context["repo"].list_engines(None) if r["engine_id"] == engine_id), None)
        return _engine(row) if row else None


schema = strawberry.Schema(query=Query)


def graphql_router(viewer: Callable[..., Principal], repo_dep: Callable[..., Any]) -> GraphQLRouter:
    async def context(
        principal: Principal = Depends(viewer), repo: Any = Depends(repo_dep)
    ) -> dict[str, Any]:
        return {"principal": principal, "repo": repo}

    return GraphQLRouter(schema, context_getter=context, graphql_ide=None)
