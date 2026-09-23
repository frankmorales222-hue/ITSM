import json
import sqlite3
from pathlib import Path


class AgentDatabase:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
          CREATE TABLE IF NOT EXISTS current_inventory (
            singleton INTEGER PRIMARY KEY CHECK (singleton=1), inventory TEXT NOT NULL, collected_at TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS sync_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL, created_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT NOT NULL DEFAULT ''
          );
        """)
        self.connection.commit()

    def save_inventory(self, inventory: dict) -> int:
        serialized = json.dumps(inventory, separators=(",", ":"), sort_keys=True)
        self.connection.execute(
            "INSERT INTO current_inventory(singleton,inventory,collected_at) VALUES(1,?,?) "
            "ON CONFLICT(singleton) DO UPDATE SET inventory=excluded.inventory,collected_at=excluded.collected_at",
            (serialized, inventory["collected_at"]),
        )
        cursor = self.connection.execute(
            "INSERT INTO sync_outbox(payload,created_at) VALUES(?,?)", (serialized, inventory["collected_at"])
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def pending(self, limit: int = 10) -> list[dict]:
        return [dict(row) for row in self.connection.execute(
            "SELECT id,payload,attempts FROM sync_outbox ORDER BY id LIMIT ?", (limit,)
        ).fetchall()]

    def delivered(self, item_id: int) -> None:
        self.connection.execute("DELETE FROM sync_outbox WHERE id=?", (item_id,))
        self.connection.commit()

    def failed(self, item_id: int, error: str) -> None:
        self.connection.execute("UPDATE sync_outbox SET attempts=attempts+1,last_error=? WHERE id=?",
                                (error[:500], item_id))
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
