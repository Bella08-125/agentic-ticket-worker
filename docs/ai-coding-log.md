# AI Coding Log

This document explains how AI coding tools were used as collaborators rather than black boxes.

## Workflow

- Used Codex to inspect requirements and turn the job description into concrete engineering checkpoints.
- Implemented the first backend slice with FastAPI, Pydantic, SQLite and pytest.
- Refactored the first version into visible Agent boundaries: planner, executor, skill registry, context manager and memory store.
- Used tests to control AI-generated changes and prevent regressions.

## Quality Controls

- Keep modules small and named by responsibility.
- Avoid hiding business behavior inside prompts.
- Persist task state and execution steps for inspection.
- Add tests for behavior that maps directly to the job requirements.
- Keep MCP support optional so the HTTP demo remains easy to run.

## What I Would Improve Next

- Add streaming execution events.
- Add a real model adapter behind the planner while keeping deterministic tests.
- Add a small Vue dashboard for observing task runs.
- Add more realistic policy retrieval through vector search, while keeping RAG as an auxiliary ability.
