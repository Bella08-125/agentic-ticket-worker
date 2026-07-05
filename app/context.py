from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContextBundle:
    keys: list[str]
    data: dict[str, Any]
    estimated_tokens: int
    strategy: str = "progressive_context_by_task_phase"


class ContextManager:
    """Loads only the context needed for the current task phase."""

    def prepare(self, phase: str, scratch: dict[str, Any]) -> ContextBundle:
        if phase == "context":
            category = scratch["triage"]["category"]
            snippets = self._policy_snippets(category)
            return ContextBundle(
                keys=[f"policy:{category}"],
                data={
                    "loaded_context": snippets,
                    "context_strategy": "progressive_context_by_triage_category",
                    "source": "mock_policy_book/v1",
                },
                estimated_tokens=self._estimate_tokens(snippets),
            )

        if phase == "act":
            keys = ["reply_style:empathetic", "action_boundary:mock_crm"]
            data = {
                "reply_style": "empathetic_and_actionable",
                "side_effect_policy": "crm_update_mock_only_after_approval_or_low_risk_auto_policy",
            }
            return ContextBundle(keys=keys, data=data, estimated_tokens=self._estimate_tokens(list(data.values())))

        return ContextBundle(keys=[], data={}, estimated_tokens=0)

    def _policy_snippets(self, category: str) -> list[str]:
        policies = {
            "general_consultation": [
                "优先回答商品、育儿、门店服务相关问题。",
                "不确定内容需要给出人工客服转接建议。",
            ],
            "refund_request": [
                "退款和赔偿类动作需要人工审批后才能承诺。",
                "先收集订单号、购买渠道、问题照片和用户诉求。",
            ],
            "health_risk": [
                "健康风险场景不得给出诊断结论。",
                "建议用户及时咨询医生，并同步人工客服跟进。",
            ],
            "complaint": [
                "投诉类场景需要安抚、记录证据并升级主管确认。",
                "不得承诺超出政策范围的补偿。",
            ],
        }
        return policies.get(category, policies["general_consultation"])

    def _estimate_tokens(self, values: list[str]) -> int:
        return max(1, sum(len(value) for value in values) // 2)
