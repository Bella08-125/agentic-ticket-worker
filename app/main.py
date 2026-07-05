from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException

from app.agent import AgentExecutor
from app.models import ApprovalRequest, SkillInfo, TaskCreate, TaskCreated, TaskDetail
from app.skills import SkillRegistry
from app.storage import DEFAULT_DB_PATH, Storage


def build_app(db_path: str | Path | None = None) -> FastAPI:
    storage = Storage(db_path or os.getenv("AGENTIC_DB_PATH", DEFAULT_DB_PATH))
    registry = SkillRegistry()
    executor = AgentExecutor(storage=storage, registry=registry)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        storage.init_db()
        app.state.executor = executor
        app.state.registry = registry
        yield

    app = FastAPI(
        title="Agentic Ticket Worker",
        description=(
            "A minimal executable-agent demo: Task -> Planning -> Skill calls -> "
            "progressive context -> human approval -> final action."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/skills", response_model=list[SkillInfo])
    def list_skills() -> list[SkillInfo]:
        return registry.list()

    @app.post("/tasks", response_model=TaskCreated, status_code=201)
    def create_task(request: TaskCreate) -> dict[str, object]:
        return executor.create_task(request)

    @app.get("/tasks/{task_id}", response_model=TaskDetail)
    def get_task(task_id: str) -> dict[str, object]:
        try:
            return executor.get_task(task_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="task not found") from None

    @app.post("/tasks/{task_id}/approve", response_model=TaskDetail)
    def approve_task(task_id: str, request: ApprovalRequest) -> dict[str, object]:
        try:
            return executor.approve_task(task_id, request)
        except KeyError:
            raise HTTPException(status_code=404, detail="task not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return app


app = build_app()
