from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT_DIR / "data" / "agentic_ticket_worker.sqlite3"


class Storage:
    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)

    def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    customer_message TEXT NOT NULL,
                    customer_type TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    final_output_json TEXT,
                    approval_payload_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS execution_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    agent_name TEXT NOT NULL DEFAULT 'TicketWorkerAgent',
                    phase TEXT NOT NULL,
                    skill_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    thought TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL DEFAULT '',
                    observation TEXT NOT NULL DEFAULT '',
                    input_json TEXT NOT NULL,
                    output_json TEXT,
                    error TEXT,
                    retry_count INTEGER NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    loaded_context_keys_json TEXT NOT NULL DEFAULT '[]',
                    estimated_tokens INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                );
                """
            )
            self._ensure_execution_step_columns(conn)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_execution_step_columns(self, conn: sqlite3.Connection) -> None:
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(execution_steps)").fetchall()
        }
        migrations = {
            "agent_name": "ALTER TABLE execution_steps ADD COLUMN agent_name TEXT NOT NULL DEFAULT 'TicketWorkerAgent'",
            "thought": "ALTER TABLE execution_steps ADD COLUMN thought TEXT NOT NULL DEFAULT ''",
            "action": "ALTER TABLE execution_steps ADD COLUMN action TEXT NOT NULL DEFAULT ''",
            "observation": "ALTER TABLE execution_steps ADD COLUMN observation TEXT NOT NULL DEFAULT ''",
            "loaded_context_keys_json": "ALTER TABLE execution_steps ADD COLUMN loaded_context_keys_json TEXT NOT NULL DEFAULT '[]'",
            "estimated_tokens": "ALTER TABLE execution_steps ADD COLUMN estimated_tokens INTEGER NOT NULL DEFAULT 0",
        }
        for column, statement in migrations.items():
            if column not in columns:
                conn.execute(statement)


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    return json.loads(value)
