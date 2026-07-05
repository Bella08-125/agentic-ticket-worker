# Agentic Ticket Worker

一个面向母婴/客服工单场景的最小执行型 Agent Demo。它不是普通 RAG 问答，而是演示：

`Task -> Planning -> Skill 调用 -> 渐进式上下文 -> 风险判断 -> 人工审批 -> 最终动作`

这个项目用于快速证明 Agent 开发实习所需的工程思维：可扩展 Skill Registry、任务状态、步骤日志、异常重试、人工确认和可测试代码。

## Why This Is Not Just RAG

- RAG 只作为 `policy_lookup` 的辅助上下文能力。
- Agent 主线是任务执行：每个任务会生成固定计划并按步骤调用 skills。
- 每一步都有输入、输出、错误、重试次数、耗时和状态记录。
- 高风险动作不会直接执行，会停在 `waiting_approval` 等待人工确认。
- `crm_update_mock` 明确标注为 mock side effect，避免 demo 误写外部系统。

## API

- `GET /skills`：查看 Skill Registry。
- `POST /tasks`：提交一个客服工单任务。
- `GET /tasks/{id}`：查看计划、执行步骤、状态和最终输出。
- `POST /tasks/{id}/approve`：对高风险任务进行人工审批并继续执行。

## Skills

| Skill | Phase | Purpose |
| --- | --- | --- |
| `ticket_triage` | understand | 判断工单类别、紧急程度和摘要 |
| `policy_lookup` | context | 按分类加载必要政策上下文，演示 Progressive Context |
| `escalation_decision` | risk_control | 判断是否需要人工审批 |
| `reply_draft` | act | 基于已审批上下文生成客服回复 |
| `crm_update_mock` | act | 模拟写入 CRM，展示工具副作用边界 |

## Run Locally

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

Open Swagger:

```text
http://127.0.0.1:8000/docs
```

## Optional MCP Server

The same task worker can be exposed as MCP tools:

```powershell
.\.venv\Scripts\python -m app.mcp_server
```

Exposed tools:

- `list_skills`
- `create_ticket_task`
- `get_ticket_task`
- `approve_ticket_task`

This is intentionally minimal. The goal is to show how business capabilities can be wrapped as tools for an AI coding agent or MCP-compatible client.

## Example

Create a high-risk task:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/tasks -ContentType 'application/json' -Body '{
  "title": "退款投诉",
  "customer_message": "我想退款并投诉，商品体验很差。",
  "customer_type": "normal",
  "priority": "high"
}'
```

The task will stop at `waiting_approval`. Continue it:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/tasks/{id}/approve -ContentType 'application/json' -Body '{
  "approved": true,
  "reviewer": "mentor",
  "note": "允许客服安抚并升级"
}'
```

## Tests

```powershell
.\.venv\Scripts\python -m pytest
```

Covered scenarios:

- Skill Registry listing.
- Low-risk task completes automatically.
- Refund/complaint task waits for approval.
- Approval continues execution.
- Invalid approval returns conflict.
- Transient skill failure retries once.
- Missing task returns 404.
- Progressive context loads category-specific policy.

## AI Coding Notes

This repository is intentionally small so an interviewer can inspect it quickly. The current implementation favors readable modules over framework magic:

- `app/skills.py` keeps business capabilities modular.
- `app/agent.py` owns planning, execution, retry, approval and state transition.
- `app/storage.py` uses SQLite directly to keep persistence transparent.
- `tests/test_tasks.py` verifies the execution chain instead of only checking HTTP status.

Next improvements would be streaming execution events, LangGraph-style durable checkpoints, stricter MCP auth/config examples, and a Vue dashboard for task observation.
