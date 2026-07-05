---
name: agent-repo-review
description: Review this agentic-ticket-worker repository for Agent developer interview readiness. Use when Codex needs to assess or improve architecture quality, Skill Registry design, Progressive Context, ReACT trace, FastAPI boundaries, tests, README/GitHub presentation, or whether the project convincingly demonstrates an executable Agent / digital worker rather than a RAG chatbot.
---

# Agent Repo Review

Use this skill as a focused review checklist for `agentic-ticket-worker`.

## Review Workflow

1. Inspect the repo before judging. Read `README.md`, `docs/architecture.md`, `app/planner.py`, `app/agent.py`, `app/skills.py`, `app/context.py`, `app/memory.py`, `app/main.py`, and `tests/test_tasks.py` as needed.
2. Verify that the project still demonstrates task execution: Planning, Progressive Context, Skill/Tool calls, ReACT trace, approval, retry, state persistence, and final output.
3. Check that architectural responsibilities stay separated:
   - FastAPI routes adapt HTTP only.
   - Planner creates structured task plans.
   - Executor owns state transitions and execution flow.
   - SkillRegistry owns skill metadata and lookup.
   - ContextManager owns staged context loading.
   - MemoryStore owns customer profile recall.
   - Storage owns persistence.
4. Check whether each public behavior has a readable test or a documented demo path.
5. Prefer small, explicit recommendations over broad rewrites.

## Architecture Checks

- Confirm `Task -> Planning -> Skill/Tool Call -> Output` is visible in code and README.
- Confirm RAG-like behavior remains auxiliary through `policy_lookup`.
- Confirm high-risk actions wait for human approval before mock side effects.
- Confirm skills expose useful metadata: type, phase, capabilities, risk, schemas, and approval requirements.
- Confirm ReACT trace fields are present in execution steps: `thought`, `action`, and `observation`.

## Engineering Checks

- Do not allow business orchestration to drift into `app/main.py`.
- Do not hardcode secrets, private URLs, local absolute paths, or API keys.
- Do not add dependencies unless they improve the demo or reviewability.
- Do not submit generated files such as `.venv`, `data`, `__pycache__`, `.pytest_cache`, or local SQLite databases.
- Keep README and docs aligned with actual API responses.

## Test Expectations

Run or request:

```powershell
.\.venv\Scripts\python -m pytest -q
```

Look for tests covering:

- Skill Registry metadata.
- Structured planning.
- Low-risk automatic completion.
- High-risk human approval.
- Approval continuation.
- Transient failure retry.
- Progressive context keys.
- ReACT trace fields.
- Memory profile use.

## Output Format

When using this skill, report:

- **Architecture**: boundaries touched, strengths, and violations.
- **Agent Behavior**: whether execution, planning, context, approval, retry, and trace are convincing.
- **Engineering Quality**: maintainability, typing, persistence, API clarity, and dependency risks.
- **Tests**: tests run, results, and missing scenarios.
- **README/GitHub Presentation**: whether the project is interview-ready.
- **Action Items**: short prioritized fixes, ordered by interview impact.
