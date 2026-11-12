import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from uuid import uuid4


class Store:
    def __init__(self, path):
        self.path = path
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    def create(self, symbol, goal, start, end, plan):
        task = dict(id=uuid4().hex, symbol=symbol, goal=goal, start=start, end=end,
                    status="pending", steps=plan, logs=[], result=None, error=None)
        self.save(task)
        return task

    def save(self, task):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT OR REPLACE INTO tasks VALUES (?, ?)",
                       (task["id"], json.dumps(task, ensure_ascii=False)))

    def record(self, task, message):
        task["logs"].append(dict(time=datetime.now(timezone.utc).isoformat(), message=message))
        self.save(task)

    def recent(self):
        with closing(sqlite3.connect(self.path)) as db:
            return [json.loads(row[0]) for row in
                    db.execute("SELECT payload FROM tasks ORDER BY rowid DESC LIMIT 30")]
