"""Local SQLite store for fusion weights and episodic memory."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class MemoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS weights (
                room TEXT NOT NULL,
                feature TEXT NOT NULL,
                weight REAL NOT NULL,
                PRIMARY KEY (room, feature)
            );
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                room TEXT NOT NULL,
                occupied INTEGER NOT NULL,
                confidence REAL NOT NULL,
                person TEXT,
                features_json TEXT NOT NULL,
                summary TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_episodes_room_ts
                ON episodes(room, ts DESC);
            """
        )
        self._conn.commit()

    def get_weight(self, room: str, feature: str, default: float) -> float:
        cur = self._conn.execute(
            "SELECT weight FROM weights WHERE room = ? AND feature = ?",
            (room, feature),
        )
        row = cur.fetchone()
        return float(row["weight"]) if row else default

    def set_weight(self, room: str, feature: str, weight: float) -> None:
        self._conn.execute(
            """
            INSERT INTO weights(room, feature, weight) VALUES (?, ?, ?)
            ON CONFLICT(room, feature) DO UPDATE SET weight = excluded.weight
            """,
            (room, feature, weight),
        )
        self._conn.commit()

    def nudge_weight(
        self,
        room: str,
        feature: str,
        default: float,
        *,
        active: bool,
        occupied: bool,
        rate: float = 0.02,
    ) -> float:
        """Increase weight when feature agrees with occupancy outcome."""
        current = self.get_weight(room, feature, default)
        agrees = (active and occupied) or ((not active) and (not occupied))
        delta = rate if agrees else -rate
        updated = max(0.05, min(1.5, current + delta))
        self.set_weight(room, feature, updated)
        return updated

    def add_episode(
        self,
        *,
        room: str,
        occupied: bool,
        confidence: float,
        person: str | None,
        features: dict[str, float],
        summary: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO episodes(ts, room, occupied, confidence, person, features_json, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                time.time(),
                room,
                1 if occupied else 0,
                confidence,
                person,
                json.dumps(features),
                summary,
            ),
        )
        self._conn.commit()

    def recent_summaries(self, room: str, limit: int = 8) -> list[str]:
        cur = self._conn.execute(
            """
            SELECT summary FROM episodes
            WHERE room = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (room, limit),
        )
        return [str(row["summary"]) for row in cur.fetchall()]

    def stats(self) -> dict[str, Any]:
        episodes = self._conn.execute("SELECT COUNT(*) AS c FROM episodes").fetchone()["c"]
        weights = self._conn.execute("SELECT COUNT(*) AS c FROM weights").fetchone()["c"]
        return {"episodes": episodes, "weights": weights, "db_path": str(self.db_path)}

    def close(self) -> None:
        self._conn.close()
