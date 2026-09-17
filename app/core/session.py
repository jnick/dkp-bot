from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional


class SessionStore:
    """Черновики сбора полей: одна строка на (channel, chat_id)."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                channel TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                template TEXT,
                field_index INTEGER DEFAULT 0,
                answers TEXT,
                state TEXT,
                updated_at REAL,
                PRIMARY KEY (channel, chat_id)
            )
            """
        )
        self._conn.commit()

    def get(self, channel: str, chat_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT template, field_index, answers, state FROM sessions WHERE channel=? AND chat_id=?",
                (channel, chat_id),
            ).fetchone()
        if not row:
            return None
        return {
            "template": row[0],
            "index": row[1],
            "answers": json.loads(row[2] or "{}"),
            "state": row[3],
        }

    def save(
        self,
        channel: str,
        chat_id: str,
        template: str,
        index: int,
        answers: Dict[str, str],
        state: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO sessions (channel, chat_id, template, field_index, answers, state, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (channel, chat_id, template, index, json.dumps(answers, ensure_ascii=False), state, time.time()),
            )
            self._conn.commit()

    def clear(self, channel: str, chat_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM sessions WHERE channel=? AND chat_id=?", (channel, chat_id)
            )
            self._conn.commit()

    def cleanup(self, max_age_seconds: float = 60 * 60 * 24 * 7) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM sessions WHERE updated_at < ?", (time.time() - max_age_seconds,)
            )
            self._conn.commit()