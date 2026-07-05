from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.context import ContextBundle, ContextManager
from app.memory import MemoryStore
from app.models import ApprovalRequest, PlanStep, TaskCreate
from app.planner import SupervisorAgent
from app.skills import SkillRegistry, TransientSkillError
from app.storage import Storage, dumps, loads


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentExecutor:
    def __init__(
        self,
        storage: Storage,
        registry: SkillRegistry,
        supervisor: SupervisorAgent | None = None,
        context_manager: ContextManager | None = None,
        memory: MemoryStore | None = None,
    ):
        self.storage = storage
        self.registry = registry
        self.supervisor = supervisor or SupervisorAgent(registry)
        self.context_manager = context_manager or ContextManager()
        self.memory = memory or MemoryStore()

    def create_task(self, request: TaskCreate) -> dict[str, Any]:
        task_id = str(uuid.uuid4())
        created_at = now_iso()
        plan = self.supervisor.plan(request)
        plan_payload = [step.model_dump() for step in plan]
        task = {
            "id": task_id,
            "title": request.title,
            "customer_message": request.customer_message,
            "customer_type": request.customer_type,
            "priority": request.priority,
            "status": "running",
            "plan": plan_payload,
            "final_output": None,
            "approval_payload": None,
            "created_at": created_at,
            "updated_at": created_at,
        }
        with self.storage.connection() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    id, title, customer_message, customer_type, priority, status,
                    plan_json, final_output_json, approval_payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    request.title,
                    request.customer_message,
                    request.customer_type,
                    request.priority,
                    "running",
                    dumps(plan_payload),
                    None,
                    None,
                    created_at,
                    created_at,
                ),
            )

        self._run_until_approval_or_done(task, plan)
        detail = self.get_task(task_id)
        return {
            "id": task_id,
            "status": detail["status"],
            "plan": detail["plan"],
            "next_action": "call POST /tasks/{id}/approve" if detail["status"] == "waiting_approval" else "review final_output",
        }

    def approve_task(self, task_id: str, approval: ApprovalRequest) -> dict[str, Any]:
        task = self.get_task(task_id)
        if task["status"] != "waiting_approval":
            raise ValueError("task is not waiting for approval")

        task["approval_payload"] = {
            "approved": approval.approved,
            "reviewer": approval.reviewer,
            "note": approval.note,
            "reviewed_at": now_iso(),
        }
        self._update_task(task_id, status="running", approval_payload=task["approval_payload"])
        self._continue_after_approval(task)
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self.storage.connection() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                raise KeyError(task_id)
            steps = conn.execute(
                "SELECT * FROM execution_steps WHERE task_id = ? ORDER BY step_index ASC, id ASC",
                (task_id,),
            ).fetchall()

        return {
            "id": row["id"],
            "title": row["title"],
            "customer_message": row["customer_message"],
            "customer_type": row["customer_type"],
            "priority": row["priority"],
            "status": row["status"],
            "plan": loads(row["plan_json"], []),
            "final_output": loads(row["final_output_json"]),
            "approval_payload": loads(row["approval_payload_json"]),
            "steps": [
                {
                    "step_index": step["step_index"],
                    "agent_name": step["agent_name"],
                    "phase": step["phase"],
                    "skill_name": step["skill_name"],
                    "status": step["status"],
                    "thought": step["thought"],
                    "action": step["action"],
                    "observation": step["observation"],
                    "input": loads(step["input_json"], {}),
                    "output": loads(step["output_json"]),
                    "error": step["error"],
                    "retry_count": step["retry_count"],
                    "duration_ms": step["duration_ms"],
                    "loaded_context_keys": loads(step["loaded_context_keys_json"], []),
                    "estimated_tokens": step["estimated_tokens"],
                    "created_at": step["created_at"],
                }
                for step in steps
            ],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _run_until_approval_or_done(self, task: dict[str, Any], plan: list[PlanStep]) -> None:
        scratch: dict[str, Any] = {
            "task": self._task_view(task),
            "memory": self.memory.recall_customer_profile(task["customer_type"]),
        }
        try:
            scratch["triage"] = self._call_skill(
                task_id=task["id"],
                plan_step=plan[0],
                payload={**self._task_view(task), "memory": scratch["memory"]},
                thought="Understand the ticket before loading any policy context.",
                action="Call ticket_triage skill.",
                context_bundle=ContextBundle(keys=["memory:customer_profile"], data={}, estimated_tokens=8),
            )

            policy_context = self.context_manager.prepare("context", scratch)
            scratch["policy"] = self._call_skill(
                task_id=task["id"],
                plan_step=plan[1],
                payload={
                    "triage": scratch["triage"],
                    "context": policy_context.data,
                    "simulate_transient_failure": "模拟失败" in task["customer_message"],
                },
                thought="Load policy snippets only after triage identifies the task category.",
                action="Call policy_lookup skill with progressive context.",
                context_bundle=policy_context,
            )

            scratch["decision"] = self._call_skill(
                task_id=task["id"],
                plan_step=plan[2],
                payload={
                    "task": self._task_view(task),
                    "triage": scratch["triage"],
                    "policy": scratch["policy"],
                    "memory": scratch["memory"],
                },
                thought="Check whether this task can proceed automatically or needs human approval.",
                action="Call escalation_decision skill.",
                context_bundle=ContextBundle(keys=["memory:customer_profile"], data={}, estimated_tokens=8),
            )

            if scratch["decision"]["requires_approval"]:
                self._update_task(
                    task["id"],
                    status="waiting_approval",
                    approval_payload={
                        "reason": scratch["decision"]["reason"],
                        "risk_level": scratch["decision"]["risk_level"],
                        "pending_skill": "reply_draft",
                    },
                )
                return

            scratch["approval"] = {"approved": True, "reviewer": "auto_low_risk_policy"}
            self._finish_task(task["id"], task, scratch, plan)
        except Exception as exc:
            self._update_task(task["id"], status="failed", final_output={"error": str(exc)})

    def _continue_after_approval(self, task: dict[str, Any]) -> None:
        steps_by_skill = {step["skill_name"]: step["output"] for step in task["steps"] if step["output"]}
        plan = [PlanStep(**step) for step in task["plan"]]
        scratch = {
            "task": self._task_view(task),
            "memory": self.memory.recall_customer_profile(task["customer_type"]),
            "triage": steps_by_skill["ticket_triage"],
            "policy": steps_by_skill["policy_lookup"],
            "decision": steps_by_skill["escalation_decision"],
            "approval": task["approval_payload"],
        }
        self._finish_task(task["id"], task, scratch, plan)

    def _finish_task(self, task_id: str, task: dict[str, Any], scratch: dict[str, Any], plan: list[PlanStep]) -> None:
        act_context = self.context_manager.prepare("act", scratch)
        reply = self._call_skill(
            task_id=task_id,
            plan_step=plan[3],
            payload={
                "task": self._task_view(task),
                "triage": scratch["triage"],
                "policy": scratch["policy"],
                "approval": scratch["approval"],
                "context": act_context.data,
            },
            thought="Generate the customer response from approved policy and action context.",
            action="Call reply_draft skill.",
            context_bundle=act_context,
        )
        crm = self._call_skill(
            task_id=task_id,
            plan_step=plan[4],
            payload={
                "task_id": task_id,
                "reply": reply,
                "decision": scratch["decision"],
                "context": act_context.data,
            },
            thought="Record the result through a mock tool after approval boundaries are satisfied.",
            action="Call crm_update_mock skill.",
            context_bundle=act_context,
        )
        self._update_task(
            task_id,
            status="completed",
            final_output={
                "triage": scratch["triage"],
                "decision": scratch["decision"],
                "reply": reply,
                "crm": crm,
                "memory": scratch["memory"],
            },
        )

    def _call_skill(
        self,
        task_id: str,
        plan_step: PlanStep,
        payload: dict[str, Any],
        thought: str,
        action: str,
        context_bundle: ContextBundle,
    ) -> dict[str, Any]:
        skill = self.registry.get(plan_step.skill_name)
        max_attempts = 2
        started = time.perf_counter()
        last_error: str | None = None
        for attempt in range(max_attempts):
            try:
                output = skill.handler({**payload, "attempt": attempt})
                self._record_step(
                    task_id=task_id,
                    plan_step=plan_step,
                    status="success",
                    input_payload=payload,
                    output_payload=output,
                    error=None,
                    retry_count=attempt,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    thought=thought,
                    action=action,
                    observation=f"{plan_step.skill_name} completed successfully.",
                    context_bundle=context_bundle,
                )
                return output
            except TransientSkillError as exc:
                last_error = str(exc)
                continue
            except Exception as exc:
                last_error = str(exc)
                break

        self._record_step(
            task_id=task_id,
            plan_step=plan_step,
            status="failed",
            input_payload=payload,
            output_payload=None,
            error=last_error or "unknown skill error",
            retry_count=max_attempts - 1,
            duration_ms=int((time.perf_counter() - started) * 1000),
            thought=thought,
            action=action,
            observation=f"{plan_step.skill_name} failed after retry policy.",
            context_bundle=context_bundle,
        )
        raise RuntimeError(f"{plan_step.skill_name} failed: {last_error}")

    def _record_step(
        self,
        task_id: str,
        plan_step: PlanStep,
        status: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any] | None,
        error: str | None,
        retry_count: int,
        duration_ms: int,
        thought: str,
        action: str,
        observation: str,
        context_bundle: ContextBundle,
    ) -> None:
        with self.storage.connection() as conn:
            conn.execute(
                """
                INSERT INTO execution_steps (
                    task_id, step_index, agent_name, phase, skill_name, status,
                    thought, action, observation, input_json, output_json, error,
                    retry_count, duration_ms, loaded_context_keys_json, estimated_tokens, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    plan_step.step_index,
                    "TicketWorkerAgent",
                    plan_step.phase,
                    plan_step.skill_name,
                    status,
                    thought,
                    action,
                    observation,
                    dumps(input_payload),
                    dumps(output_payload) if output_payload is not None else None,
                    error,
                    retry_count,
                    duration_ms,
                    dumps(context_bundle.keys),
                    context_bundle.estimated_tokens,
                    now_iso(),
                ),
            )

    def _update_task(
        self,
        task_id: str,
        status: str,
        final_output: dict[str, Any] | None = None,
        approval_payload: dict[str, Any] | None = None,
    ) -> None:
        with self.storage.connection() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET status = ?,
                    final_output_json = COALESCE(?, final_output_json),
                    approval_payload_json = COALESCE(?, approval_payload_json),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    dumps(final_output) if final_output is not None else None,
                    dumps(approval_payload) if approval_payload is not None else None,
                    now_iso(),
                    task_id,
                ),
            )

    def _task_view(self, task: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": task["id"],
            "title": task["title"],
            "customer_message": task["customer_message"],
            "customer_type": task["customer_type"],
            "priority": task["priority"],
        }
