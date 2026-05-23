import sqlite3
import os
import threading

class IdempotencyStore:
    def is_processed(self, delivery_id: str) -> bool:
        raise NotImplementedError

    def mark_processed(self, delivery_id: str):
        raise NotImplementedError

class SQLiteIdempotencyStore(IdempotencyStore):
    def __init__(self, db_path=".aegis_idempotency.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS webhooks (
                    delivery_id TEXT PRIMARY KEY,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            conn.close()

    def is_processed(self, delivery_id: str) -> bool:
        if not delivery_id:
            return False
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM webhooks WHERE delivery_id = ?", (delivery_id,))
            exists = cursor.fetchone() is not None
            conn.close()
            return exists

    def mark_processed(self, delivery_id: str):
        if not delivery_id:
            return
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO webhooks (delivery_id) VALUES (?)", (delivery_id,))
                conn.commit()
            except sqlite3.IntegrityError:
                # Already exists
                pass
            finally:
                conn.close()

# Global instance for easy import in server.py
# In production, this can be swapped with a Redis/Postgres implementation
store = SQLiteIdempotencyStore()
