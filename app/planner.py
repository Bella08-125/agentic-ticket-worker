from __future__ import annotations

from app.models import PlanStep, TaskCreate
from app.skills import SkillRegistry


class SupervisorAgent:
    """Plans task execution and delegates concrete work to skill-backed workers."""

    def __init__(self, registry: SkillRegistry):
        self.registry = registry

    def plan(self, request: TaskCreate) -> list[PlanStep]:
        raw_text = f"{request.title} {request.customer_message}".lower()
        likely_high_risk = (
            request.priority == "high"
            or request.customer_type == "vip"
            or any(word in raw_text for word in ["refund", "退款", "退货", "投诉", "过敏", "发烧"])
        )

        capabilities = [
            ("understand_ticket", "understand", "Classify the customer task before loading context."),
            ("load_policy_context", "context", "Load only policy snippets needed for the triage result."),
            ("decide_escalation", "risk_control", "Decide whether the action needs human approval."),
            ("draft_reply", "act", "Draft the customer-facing response."),
            ("write_crm_record", "act", "Record the final action with a mock side-effect boundary."),
        ]

        steps: list[PlanStep] = []
        for index, (capability, phase, reason) in enumerate(capabilities, start=1):
            skill = self.registry.find_by_capability(capability)
            steps.append(
                PlanStep(
                    step_index=index,
                    phase=phase,
                    skill_name=skill.name,
                    reason=reason,
                    required_context=self._required_context(phase),
                    requires_approval=skill.requires_approval and likely_high_risk,
                )
            )
        return steps

    def _required_context(self, phase: str) -> list[str]:
        if phase == "context":
            return ["triage_category_policy"]
        if phase == "act":
            return ["reply_style", "side_effect_policy"]
        return []
