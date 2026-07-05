from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.models import SkillInfo


SkillHandler = Callable[[dict[str, Any]], dict[str, Any]]


class TransientSkillError(RuntimeError):
    """Raised when a tool-like skill should be retried."""


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    version: str
    description: str
    skill_type: str
    phase: str
    capabilities: list[str]
    match_rules: dict[str, Any]
    risk_level: str
    requires_approval: bool
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: SkillHandler

    def public_info(self) -> SkillInfo:
        return SkillInfo(
            name=self.name,
            version=self.version,
            description=self.description,
            skill_type=self.skill_type,  # type: ignore[arg-type]
            phase=self.phase,
            capabilities=self.capabilities,
            match_rules=self.match_rules,
            risk_level=self.risk_level,  # type: ignore[arg-type]
            requires_approval=self.requires_approval,
            input_schema=self.input_schema,
            output_schema=self.output_schema,
        )


def ticket_triage(payload: dict[str, Any]) -> dict[str, Any]:
    message = payload["customer_message"]
    lowered = message.lower()
    refund_words = ["退款", "退货", "refund", "赔偿"]
    health_words = ["过敏", "发烧", "拉肚子", "医生", "医院", "不舒服"]
    complaint_words = ["投诉", "差评", "生气", "欺骗", "投诉平台"]

    category = "general_consultation"
    if any(word in lowered or word in message for word in refund_words):
        category = "refund_request"
    if any(word in lowered or word in message for word in health_words):
        category = "health_risk"
    if any(word in lowered or word in message for word in complaint_words):
        category = "complaint"

    urgency = "high" if category in {"health_risk", "complaint"} or payload["priority"] == "high" else "normal"
    return {
        "category": category,
        "urgency": urgency,
        "customer_type": payload["customer_type"],
        "summary": message[:120],
    }


def policy_lookup(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("simulate_transient_failure") and payload.get("attempt") == 0:
        raise TransientSkillError("policy service timeout, retry with same context")

    context = payload["context"]
    return {
        "loaded_context": context["loaded_context"],
        "context_strategy": context["context_strategy"],
        "source": context["source"],
    }


def escalation_decision(payload: dict[str, Any]) -> dict[str, Any]:
    category = payload["triage"]["category"]
    high_risk = category in {"refund_request", "health_risk", "complaint"}
    vip = payload["task"]["customer_type"] == "vip"
    requires_approval = high_risk or vip
    return {
        "requires_approval": requires_approval,
        "risk_level": "high" if high_risk else "medium" if vip else "low",
        "reason": "高风险/退款/投诉/健康或 VIP 工单需要人工确认" if requires_approval else "低风险咨询可自动回复",
    }


def reply_draft(payload: dict[str, Any]) -> dict[str, Any]:
    triage = payload["triage"]
    policies = "；".join(payload["policy"]["loaded_context"])
    approval = payload.get("approval")
    approved_text = "已通过人工审批。" if approval and approval.get("approved") else ""
    if approval and not approval.get("approved"):
        approved_text = "人工审批未通过，回复中避免承诺补偿。"

    return {
        "reply": (
            f"您好，已收到您的反馈。我们判断当前问题类型为 {triage['category']}。"
            f"{approved_text} 处理依据：{policies} 我们会先核对信息并安排客服继续跟进。"
        ),
        "tone": "empathetic_and_actionable",
        "next_actions": ["记录工单", "同步客服", "必要时升级人工"],
    }


def crm_update_mock(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "crm_record_id": f"mock-crm-{payload['task_id'][:8]}",
        "written_fields": ["category", "risk_level", "reply", "next_actions"],
        "side_effect": "mock_only_no_external_write",
    }


class SkillRegistry:
    def __init__(self) -> None:
        self._skills = {
            skill.name: skill
            for skill in [
                SkillDefinition(
                    name="ticket_triage",
                    version="1.0.0",
                    description="Classify customer ticket category, urgency, and summary.",
                    skill_type="workflow",
                    phase="understand",
                    capabilities=["understand_ticket", "classify_ticket"],
                    match_rules={"always": True},
                    risk_level="low",
                    requires_approval=False,
                    input_schema={"customer_message": "str", "customer_type": "str", "priority": "str"},
                    output_schema={"category": "str", "urgency": "str", "summary": "str"},
                    handler=ticket_triage,
                ),
                SkillDefinition(
                    name="policy_lookup",
                    version="1.0.0",
                    description="Load only the policy snippets needed for the current triage category.",
                    skill_type="api",
                    phase="context",
                    capabilities=["load_policy_context", "retrieve_policy"],
                    match_rules={"requires": ["triage.category"]},
                    risk_level="low",
                    requires_approval=False,
                    input_schema={"triage": "dict", "context": "dict", "simulate_transient_failure": "bool"},
                    output_schema={"loaded_context": "list[str]", "context_strategy": "str"},
                    handler=policy_lookup,
                ),
                SkillDefinition(
                    name="escalation_decision",
                    version="1.0.0",
                    description="Decide whether the planned action needs human approval.",
                    skill_type="workflow",
                    phase="risk_control",
                    capabilities=["decide_escalation", "risk_control"],
                    match_rules={"requires": ["task.customer_type", "triage.category"]},
                    risk_level="medium",
                    requires_approval=False,
                    input_schema={"task": "dict", "triage": "dict", "policy": "dict"},
                    output_schema={"requires_approval": "bool", "risk_level": "str", "reason": "str"},
                    handler=escalation_decision,
                ),
                SkillDefinition(
                    name="reply_draft",
                    version="1.0.0",
                    description="Draft a customer reply from approved context and policy.",
                    skill_type="tool",
                    phase="act",
                    capabilities=["draft_reply", "compose_customer_message"],
                    match_rules={"requires": ["policy.loaded_context", "approval"]},
                    risk_level="medium",
                    requires_approval=True,
                    input_schema={"task": "dict", "triage": "dict", "policy": "dict", "approval": "dict | null"},
                    output_schema={"reply": "str", "tone": "str", "next_actions": "list[str]"},
                    handler=reply_draft,
                ),
                SkillDefinition(
                    name="crm_update_mock",
                    version="1.0.0",
                    description="Mock a CRM write to demonstrate tool side-effect boundaries.",
                    skill_type="tool",
                    phase="act",
                    capabilities=["write_crm_record", "record_resolution"],
                    match_rules={"requires": ["task_id", "reply", "decision"]},
                    risk_level="high",
                    requires_approval=True,
                    input_schema={"task_id": "str", "reply": "dict", "decision": "dict"},
                    output_schema={"crm_record_id": "str", "side_effect": "str"},
                    handler=crm_update_mock,
                ),
            ]
        }

    def list(self) -> list[SkillInfo]:
        return [skill.public_info() for skill in self._skills.values()]

    def get(self, name: str) -> SkillDefinition:
        return self._skills[name]

    def find_by_capability(self, capability: str) -> SkillDefinition:
        for skill in self._skills.values():
            if capability in skill.capabilities:
                return skill
        raise KeyError(f"no skill supports capability: {capability}")
