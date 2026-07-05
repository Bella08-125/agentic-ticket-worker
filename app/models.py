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
    skill_type: Literal["api", "workflow", "tool"]
    phase: str
    capabilities: list[str]
    match_rules: dict[str, Any]
    risk_level: Literal["low", "medium", "high"]
    requires_approval: bool
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class PlanStep(BaseModel):
    step_index: int
    phase: str
    skill_name: str
    reason: str
    required_context: list[str] = Field(default_factory=list)
    requires_approval: bool = False


class ExecutionStep(BaseModel):
    step_index: int
    agent_name: str
    phase: str
    skill_name: str
    status: StepStatus
    thought: str
    action: str
    observation: str
    input: dict[str, Any]
    output: dict[str, Any] | None = None
    error: str | None = None
    retry_count: int = 0
    duration_ms: int
    loaded_context_keys: list[str] = Field(default_factory=list)
    estimated_tokens: int = 0
    created_at: str


class TaskDetail(BaseModel):
    id: str
    title: str
    customer_message: str
    customer_type: str
    priority: str
    status: TaskStatus
    plan: list[PlanStep]
    final_output: dict[str, Any] | None = None
    approval_payload: dict[str, Any] | None = None
    steps: list[ExecutionStep]
    created_at: str
    updated_at: str


class TaskCreated(BaseModel):
    id: str
    status: TaskStatus
    plan: list[PlanStep]
    next_action: str
