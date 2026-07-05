# Demo Script

Target length: 1-3 minutes.

## 1. Open Swagger

Open:

```text
http://127.0.0.1:8000/docs
```

Say:

> This is a minimal executable Agent demo for customer-service ticket work. It is not a RAG chatbot. The task goes through planning, skill calls, progressive context, approval and final action.

## 2. Show Skill Registry

Call `GET /skills`.

Point out:

- skills have type: `api / workflow / tool`
- skills have capabilities
- skills expose input and output schema

## 3. Low-Risk Task

Call `POST /tasks`:

```json
{
  "title": "商品咨询",
  "customer_message": "奶瓶材质有什么区别？",
  "customer_type": "normal",
  "priority": "normal"
}
```

Expected result:

- status is `completed`
- plan is structured
- final output includes reply and mock CRM record

## 4. High-Risk Task

Call `POST /tasks`:

```json
{
  "title": "退款投诉",
  "customer_message": "我想退款并投诉，商品体验很差。",
  "customer_type": "normal",
  "priority": "high"
}
```

Expected result:

- status is `waiting_approval`
- only triage, policy and escalation steps have run

Then call `POST /tasks/{id}/approve`:

```json
{
  "approved": true,
  "reviewer": "mentor",
  "note": "允许客服安抚并升级"
}
```

Expected result:

- status is `completed`
- reply and CRM mock action are generated after approval

## 5. Show Trace

Call `GET /tasks/{id}` and show:

- `plan[].reason`
- `steps[].thought`
- `steps[].action`
- `steps[].observation`
- `steps[].loaded_context_keys`
- `steps[].estimated_tokens`

Close with:

> The key idea is progressive task execution: the Agent does not load all context at once, and high-risk actions wait for human approval before tool side effects.
