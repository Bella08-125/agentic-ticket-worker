# Architecture

This project is intentionally small, but it keeps the core Agent boundaries visible.

## Components

- `SupervisorAgent` in `app/planner.py`: turns a task into structured `PlanStep` objects.
- `AgentExecutor` in `app/agent.py`: executes the plan, handles approval, retry, state transition and final output.
- `SkillRegistry` in `app/skills.py`: stores modular business capabilities with type, phase, schema and capability metadata.
- `ContextManager` in `app/context.py`: loads context progressively by task phase and triage category.
- `MemoryStore` in `app/memory.py`: provides a tiny long-term memory abstraction for customer profile recall.
- `Storage` in `app/storage.py`: persists tasks and execution steps in SQLite.

## Execution Chain

```mermaid
sequenceDiagram
    participant User
    participant API as FastAPI
    participant Planner as SupervisorAgent
    participant Worker as TicketWorkerAgent
    participant Context as ContextManager
    participant Skills as SkillRegistry / Skills
    participant DB as SQLite

    User->>API: POST /tasks
    API->>Planner: plan(task)
    Planner-->>API: structured PlanStep[]
    API->>Worker: execute(plan)
    Worker->>Skills: ticket_triage
    Worker->>Context: load policy context by category
    Worker->>Skills: policy_lookup
    Worker->>Skills: escalation_decision
    alt high risk
        Worker->>DB: status = waiting_approval
        User->>API: POST /tasks/{id}/approve
    end
    Worker->>Skills: reply_draft
    Worker->>Skills: crm_update_mock
    Worker->>DB: final output + ReACT steps
```

## Why This Is Not Just RAG

RAG is only represented by the `policy_lookup` skill. The main architecture is task execution: planning, skill selection, context control, tool execution, approval boundaries, state persistence and traceable output.
