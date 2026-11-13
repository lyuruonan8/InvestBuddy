import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
import os
from datetime import datetime, timezone
from uuid import uuid4


class Store:
    def __init__(self, path, *, demo_only=False):
        self.path = path
        self.demo_only = demo_only
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS threads (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS preferences (value TEXT PRIMARY KEY)")

    def create(self, symbol, goal, start, end, plan, mode="demo", max_calls=4, max_seconds=45, *, thread_id=None, planning=None, context=None):
        from investbuddy.research import validate_goal_privacy

        validate_goal_privacy(goal)
        if self.demo_only and (mode != "demo" or any(step["action"] in {"finance.query_live", "finance.query_fuyao"} for step in plan)):
            raise ValueError("公开演示仅允许合成数据。")
        if max_calls < 1 or max_seconds <= 0:
            raise ValueError("执行预算必须为正数。")
        task = dict(id=uuid4().hex, symbol=symbol, goal=goal, start=start, end=end,
                    mode=mode, control=dict(max_calls=max_calls, max_seconds=max_seconds, calls=0), status="pending", steps=plan, logs=[], result=None, error=None)
        if self.demo_only:
            task["control"]["demo_approval"] = True
        if thread_id:
            if self.demo_only:
                thread = next((item for item in self.threads() if item["id"] == thread_id), None)
                if not thread or thread["symbol"] != symbol:
                    raise ValueError("研究任务必须沿用当前线程的股票。")
            task.update(thread_id=thread_id, planning=planning, context=context)
        self.save(task)
        return task

    def save(self, task):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT OR REPLACE INTO tasks VALUES (?, ?)",
                       (task["id"], json.dumps(task, ensure_ascii=False)))

    def get(self, task_id):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT payload FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def record(self, task, message, **details):
        task["logs"].append(dict(time=datetime.now(timezone.utc).isoformat(), message=message, **details))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM tasks WHERE id = ?", (task["id"],)).fetchone()
            current = json.loads(row[0]) if row else {}
            if current.get("cancel_requested"):
                for entry in current["logs"]:
                    if entry.get("event") == "cancel_requested" and entry not in task["logs"]:
                        task["logs"].insert(-1, entry)
                task["cancel_requested"] = True
                if task["status"] != "running":
                    task.update(status="cancelled", result=None)
            db.execute("UPDATE tasks SET payload = ? WHERE id = ?",
                       (json.dumps(task, ensure_ascii=False), task["id"]))

    def request_cancel(self, task_id):
        with self.claim(task_id) as idle, closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                return
            task = json.loads(row[0])
            if task["status"] in {"completed", "cancelled", "stopped"}:
                return
            task["cancel_requested"] = True
            if idle or task["status"] != "running":
                task["status"] = "cancelled"
            task["logs"].append(dict(time=datetime.now(timezone.utc).isoformat(),
                                     message="用户请求取消", event="cancel_requested"))
            db.execute("UPDATE tasks SET payload = ? WHERE id = ?",
                       (json.dumps(task, ensure_ascii=False), task_id))

    @contextmanager
    def claim(self, task_id):
        # An OS lock releases on process exit, including an interrupted run.
        path = Path(self.path).with_suffix(".sqlite3-locks")
        path.mkdir(exist_ok=True)
        with (path / task_id).open("a+b") as lock:
            try:
                if os.name == "nt":
                    import msvcrt
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                yield False
                return
            yield True

    def recent(self):
        with closing(sqlite3.connect(self.path)) as db:
            return [json.loads(row[0]) for row in
                    db.execute("SELECT payload FROM tasks ORDER BY rowid DESC LIMIT 30")]


    def create_thread(self, symbol, start, end):
        thread = dict(id=uuid4().hex, symbol=symbol, start=start, end=end)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO threads VALUES (?, ?)", (thread["id"], json.dumps(thread)))
        return thread

    def threads(self):
        with closing(sqlite3.connect(self.path)) as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM threads ORDER BY rowid DESC")]

    def thread_tasks(self, thread_id):
        with closing(sqlite3.connect(self.path)) as db:
            return [json.loads(row[0]) for row in db.execute(
                "SELECT payload FROM tasks WHERE json_extract(payload, '$.thread_id') = ? ORDER BY rowid",
                (thread_id,))]

    def preferences(self):
        with closing(sqlite3.connect(self.path)) as db:
            return [row[0] for row in db.execute("SELECT value FROM preferences ORDER BY value")]

    def save_preference(self, value):
        from investbuddy.research import PREFERENCES

        if value not in PREFERENCES:
            raise ValueError("只能保存预设的非敏感研究偏好。")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT OR IGNORE INTO preferences VALUES (?)", (value,))

    def delete_preference(self, value):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM preferences WHERE value = ?", (value,))
