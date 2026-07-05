from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from app.agent import AgentExecutor
from app.models import ApprovalRequest, TaskCreate
from app.skills import SkillRegistry
from app.storage import DEFAULT_DB_PATH, Storage


storage = Storage(Path(DEFAULT_DB_PATH))
storage.init_db()
registry = SkillRegistry()
executor = AgentExecutor(storage=storage, registry=registry)
mcp = FastMCP("agentic-ticket-worker")


@mcp.tool()
def list_skills() -> list[dict]:
    """List available agent skills and their risk metadata."""
    return [skill.model_dump() for skill in registry.list()]


@mcp.tool()
def create_ticket_task(
    title: str,
    customer_message: str,
    customer_type: str = "normal",
    priority: str = "normal",
) -> dict:
    """Create a customer-service task and run the agent until done or approval is needed."""
    result = executor.create_task(
        TaskCreate(
            title=title,
            customer_message=customer_message,
            customer_type=customer_type,  # type: ignore[arg-type]
            priority=priority,  # type: ignore[arg-type]
        )
    )
    return result


@mcp.tool()
def get_ticket_task(task_id: str) -> dict:
    """Read task status, execution plan, step logs, approval payload, and final output."""
    return executor.get_task(task_id)


@mcp.tool()
def approve_ticket_task(task_id: str, approved: bool, reviewer: str = "mcp_reviewer", note: str = "") -> dict:
    """Approve or reject a high-risk task waiting at the human-review checkpoint."""
    return executor.approve_task(task_id, ApprovalRequest(approved=approved, reviewer=reviewer, note=note))


if __name__ == "__main__":
    mcp.run()
