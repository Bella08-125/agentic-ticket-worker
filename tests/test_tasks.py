from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import build_app


@pytest.fixture()
def client(tmp_path: Path):
    app = build_app(tmp_path / "test.sqlite3")
    with TestClient(app) as client:
        yield client


def test_lists_skill_registry(client: TestClient) -> None:
    response = client.get("/skills")
    assert response.status_code == 200
    skills = response.json()
    names = {skill["name"] for skill in skills}
    assert {"ticket_triage", "policy_lookup", "reply_draft", "escalation_decision"}.issubset(names)
    triage_skill = next(skill for skill in skills if skill["name"] == "ticket_triage")
    assert triage_skill["skill_type"] == "workflow"
    assert "understand_ticket" in triage_skill["capabilities"]


def test_low_risk_task_completes_without_human_approval(client: TestClient) -> None:
    response = client.post(
        "/tasks",
        json={
            "title": "奶粉冲泡咨询",
            "customer_message": "宝宝奶粉冲泡比例应该怎么确认？",
            "customer_type": "normal",
            "priority": "normal",
        },
    )
    assert response.status_code == 201
    created = response.json()
    assert created["status"] == "completed"
    assert created["plan"][0]["skill_name"] == "ticket_triage"
    assert created["plan"][0]["reason"]

    detail = client.get(f"/tasks/{created['id']}").json()
    assert detail["final_output"]["reply"]["tone"] == "empathetic_and_actionable"
    assert [step["skill_name"] for step in detail["steps"]] == [
        "ticket_triage",
        "policy_lookup",
        "escalation_decision",
        "reply_draft",
        "crm_update_mock",
    ]


def test_refund_task_waits_for_approval(client: TestClient) -> None:
    response = client.post(
        "/tasks",
        json={
            "title": "退款投诉",
            "customer_message": "我想退款并投诉，商品体验很差。",
            "customer_type": "normal",
            "priority": "high",
        },
    )
    created = response.json()
    assert created["status"] == "waiting_approval"

    detail = client.get(f"/tasks/{created['id']}").json()
    assert detail["approval_payload"]["pending_skill"] == "reply_draft"
    assert len(detail["steps"]) == 3


def test_approval_continues_and_finishes_task(client: TestClient) -> None:
    created = client.post(
        "/tasks",
        json={
            "title": "健康风险咨询",
            "customer_message": "宝宝吃完产品后过敏了，想退款。",
            "customer_type": "vip",
            "priority": "high",
        },
    ).json()

    response = client.post(
        f"/tasks/{created['id']}/approve",
        json={"approved": True, "reviewer": "mentor", "note": "允许客服安抚并升级"},
    )
    assert response.status_code == 200
    detail = response.json()
    assert detail["status"] == "completed"
    assert detail["final_output"]["crm"]["side_effect"] == "mock_only_no_external_write"
    assert detail["approval_payload"]["reviewer"] == "mentor"


def test_approval_rejects_non_waiting_task(client: TestClient) -> None:
    created = client.post(
        "/tasks",
        json={
            "title": "普通咨询",
            "customer_message": "请问门店几点开门？",
            "customer_type": "normal",
            "priority": "normal",
        },
    ).json()
    response = client.post(f"/tasks/{created['id']}/approve", json={"approved": True})
    assert response.status_code == 409


def test_transient_policy_failure_is_retried(client: TestClient) -> None:
    created = client.post(
        "/tasks",
        json={
            "title": "模拟失败后恢复",
            "customer_message": "模拟失败：请问商品怎么使用？",
            "customer_type": "normal",
            "priority": "normal",
        },
    ).json()
    detail = client.get(f"/tasks/{created['id']}").json()
    policy_step = next(step for step in detail["steps"] if step["skill_name"] == "policy_lookup")
    assert policy_step["status"] == "success"
    assert policy_step["retry_count"] == 1


def test_missing_task_returns_404(client: TestClient) -> None:
    response = client.get("/tasks/not-exist")
    assert response.status_code == 404


def test_progressive_context_loads_by_triage_category(client: TestClient) -> None:
    created = client.post(
        "/tasks",
        json={
            "title": "投诉升级",
            "customer_message": "我要投诉，你们的服务让我很生气。",
            "customer_type": "normal",
            "priority": "high",
        },
    ).json()
    detail = client.get(f"/tasks/{created['id']}").json()
    policy_step = next(step for step in detail["steps"] if step["skill_name"] == "policy_lookup")
    assert policy_step["output"]["context_strategy"] == "progressive_context_by_triage_category"
    assert "投诉类场景" in policy_step["output"]["loaded_context"][0]
    assert policy_step["loaded_context_keys"] == ["policy:complaint"]
    assert policy_step["estimated_tokens"] > 0


def test_plan_steps_are_structured_for_interview_review(client: TestClient) -> None:
    created = client.post(
        "/tasks",
        json={
            "title": "退款投诉",
            "customer_message": "我想退款并投诉，商品体验很差。",
            "customer_type": "normal",
            "priority": "high",
        },
    ).json()

    plan = created["plan"]
    assert [step["phase"] for step in plan] == ["understand", "context", "risk_control", "act", "act"]
    assert plan[1]["required_context"] == ["triage_category_policy"]
    assert plan[3]["requires_approval"] is True


def test_execution_steps_include_react_trace(client: TestClient) -> None:
    created = client.post(
        "/tasks",
        json={
            "title": "普通咨询",
            "customer_message": "请问门店几点开门？",
            "customer_type": "normal",
            "priority": "normal",
        },
    ).json()
    detail = client.get(f"/tasks/{created['id']}").json()
    first_step = detail["steps"][0]
    assert first_step["agent_name"] == "TicketWorkerAgent"
    assert first_step["thought"]
    assert first_step["action"].startswith("Call")
    assert "completed successfully" in first_step["observation"]


def test_low_risk_plan_does_not_require_manual_approval(client: TestClient) -> None:
    created = client.post(
        "/tasks",
        json={
            "title": "商品咨询",
            "customer_message": "奶瓶材质有什么区别？",
            "customer_type": "normal",
            "priority": "normal",
        },
    ).json()
    assert created["status"] == "completed"
    assert all(step["requires_approval"] is False for step in created["plan"])


def test_memory_profile_is_used_in_final_output(client: TestClient) -> None:
    created = client.post(
        "/tasks",
        json={
            "title": "VIP 售后",
            "customer_message": "我想退款。",
            "customer_type": "vip",
            "priority": "high",
        },
    ).json()
    detail = client.post(
        f"/tasks/{created['id']}/approve",
        json={"approved": True, "reviewer": "mentor", "note": "VIP 工单确认"},
    ).json()
    assert detail["final_output"]["memory"]["service_level"] == "priority"
