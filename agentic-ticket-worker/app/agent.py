from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.models import ApprovalRequest, TaskCreate
from app.skills import SkillRegistry, TransientSkillError
from app.storage import Storage, dumps, loads


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentExecutor:
    def __init__(self, storage: Storage, registry: SkillRegistry):
        self.storage = storage
        self.registry = registry

    def create_task(self, request: TaskCreate) -> dict[str, Any]:
        task_id = str(uuid.uuid4())
        created_at = now_iso()
        plan = ["ticket_triage", "policy_lookup", "escalation_decision", "reply_draft", "crm_update_mock"]
        task = {
            "id": task_id,
            "title": request.title,
            "customer_message": request.customer_message,
            "customer_type": request.customer_type,
            "priority": request.priority,
            "status": "running",
            "plan": plan,
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
                    dumps(plan),
                    None,
                    None,
                    created_at,
                    created_at,
                ),
            )

        self._run_until_approval_or_done(task)
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
                    "phase": step["phase"],
                    "skill_name": step["skill_name"],
                    "status": step["status"],
                    "input": loads(step["input_json"], {}),
                    "output": loads(step["output_json"]),
                    "error": step["error"],
                    "retry_count": step["retry_count"],
                    "duration_ms": step["duration_ms"],
                    "created_at": step["created_at"],
                }
                for step in steps
            ],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _run_until_approval_or_done(self, task: dict[str, Any]) -> None:
        scratch: dict[str, Any] = {"task": self._task_view(task)}
        try:
            scratch["triage"] = self._call_skill(task["id"], 1, "ticket_triage", self._task_view(task))
            scratch["policy"] = self._call_skill(
                task["id"],
                2,
                "policy_lookup",
                {
                    "triage": scratch["triage"],
                    "simulate_transient_failure": "模拟失败" in task["customer_message"],
                },
            )
            scratch["decision"] = self._call_skill(
                task["id"],
                3,
                "escalation_decision",
                {
                    "task": self._task_view(task),
                    "triage": scratch["triage"],
                    "policy": scratch["policy"],
                },
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
            self._finish_task(task["id"], task, scratch)
        except Exception as exc:
            self._update_task(task["id"], status="failed", final_output={"error": str(exc)})

    def _continue_after_approval(self, task: dict[str, Any]) -> None:
        steps_by_skill = {step["skill_name"]: step["output"] for step in task["steps"] if step["output"]}
        scratch = {
            "task": self._task_view(task),
            "triage": steps_by_skill["ticket_triage"],
            "policy": steps_by_skill["policy_lookup"],
            "decision": steps_by_skill["escalation_decision"],
            "approval": task["approval_payload"],
        }
        self._finish_task(task["id"], task, scratch)

    def _finish_task(self, task_id: str, task: dict[str, Any], scratch: dict[str, Any]) -> None:
        reply = self._call_skill(
            task_id,
            4,
            "reply_draft",
            {
                "task": self._task_view(task),
                "triage": scratch["triage"],
                "policy": scratch["policy"],
                "approval": scratch["approval"],
            },
        )
        crm = self._call_skill(
            task_id,
            5,
            "crm_update_mock",
            {
                "task_id": task_id,
                "reply": reply,
                "decision": scratch["decision"],
            },
        )
        self._update_task(
            task_id,
            status="completed",
            final_output={
                "triage": scratch["triage"],
                "decision": scratch["decision"],
                "reply": reply,
                "crm": crm,
            },
        )

    def _call_skill(self, task_id: str, step_index: int, skill_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        skill = self.registry.get(skill_name)
        max_attempts = 2
        started = time.perf_counter()
        last_error: str | None = None
        for attempt in range(max_attempts):
            try:
                output = skill.handler({**payload, "attempt": attempt})
                self._record_step(
                    task_id=task_id,
                    step_index=step_index,
                    phase=skill.phase,
                    skill_name=skill_name,
                    status="success",
                    input_payload=payload,
                    output_payload=output,
                    error=None,
                    retry_count=attempt,
                    duration_ms=int((time.perf_counter() - started) * 1000),
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
            step_index=step_index,
            phase=skill.phase,
            skill_name=skill_name,
            status="failed",
            input_payload=payload,
            output_payload=None,
            error=last_error or "unknown skill error",
            retry_count=max_attempts - 1,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        raise RuntimeError(f"{skill_name} failed: {last_error}")

    def _record_step(
        self,
        task_id: str,
        step_index: int,
        phase: str,
        skill_name: str,
        status: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any] | None,
        error: str | None,
        retry_count: int,
        duration_ms: int,
    ) -> None:
        with self.storage.connection() as conn:
            conn.execute(
                """
                INSERT INTO execution_steps (
                    task_id, step_index, phase, skill_name, status, input_json,
                    output_json, error, retry_count, duration_ms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    step_index,
                    phase,
                    skill_name,
                    status,
                    dumps(input_payload),
                    dumps(output_payload) if output_payload is not None else None,
                    error,
                    retry_count,
                    duration_ms,
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
