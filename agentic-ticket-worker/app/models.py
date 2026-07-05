from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


TaskStatus = Literal["running", "waiting_approval", "completed", "failed"]
StepStatus = Literal["success", "failed", "skipped"]


class TaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    customer_message: str = Field(min_length=5, max_length=2000)
    customer_type: Literal["normal", "vip", "store"] = "normal"
    priority: Literal["low", "normal", "high"] = "normal"


class ApprovalRequest(BaseModel):
    approved: bool
    reviewer: str = Field(default="human_reviewer", max_length=80)
    note: str = Field(default="", max_length=500)


class SkillInfo(BaseModel):
    name: str
    version: str
    description: str
    phase: str
    risk_level: Literal["low", "medium", "high"]
    requires_approval: bool
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class ExecutionStep(BaseModel):
    step_index: int
    phase: str
    skill_name: str
    status: StepStatus
    input: dict[str, Any]
    output: dict[str, Any] | None = None
    error: str | None = None
    retry_count: int = 0
    duration_ms: int
    created_at: str


class TaskDetail(BaseModel):
    id: str
    title: str
    customer_message: str
    customer_type: str
    priority: str
    status: TaskStatus
    plan: list[str]
    final_output: dict[str, Any] | None = None
    approval_payload: dict[str, Any] | None = None
    steps: list[ExecutionStep]
    created_at: str
    updated_at: str


class TaskCreated(BaseModel):
    id: str
    status: TaskStatus
    plan: list[str]
    next_action: str
