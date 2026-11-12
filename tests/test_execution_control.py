from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest

from investbuddy.agent import execute, plan
from investbuddy.store import Store
from investbuddy.tools import TOOLS


class ExecutionControlTest(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = Store(Path(folder.name) / "research.sqlite3")

    def create(self, mode="demo", **limits):
        return self.store.create("300750.SZ", "financial review", "2026-01-01", "2026-06-30",
                                 plan("financial review", mode), mode=mode, **limits)

    def test_resume_reuses_checkpoint_in_same_task(self):
        task = self.create()

        def interrupt(current):
            if current["steps"][0]["status"] == "completed":
                raise RuntimeError("interrupted after checkpoint")

        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            execute(task, self.store, on_update=interrupt)
        persisted = Store(self.store.path).get(task["id"])
        self.assertEqual(persisted["status"], "running")
        resumed = execute(persisted, self.store, {"finance.calculate": TOOLS["finance.calculate"]})
        self.assertEqual(resumed["id"], task["id"])
        self.assertEqual(resumed["status"], "completed")
        self.assertEqual(resumed["steps"][0]["attempts"], 1)
        self.assertEqual(resumed["control"]["calls"], 2)
        self.assertTrue(any("duration_ms" in entry for entry in resumed["logs"]))

    def test_live_waits_for_approval(self):
        task = self.create("live")
        calls = []

        def query(current):
            calls.append(current["id"])
            raise TimeoutError("fixture")

        tools = {"finance.query_live": query}
        self.assertEqual(execute(task, self.store, tools)["status"], "awaiting_approval")
        self.assertEqual(calls, [])
        self.assertEqual(execute(task, self.store, tools, approve=True)["status"], "failed")
        self.assertEqual(calls, [task["id"]])
        self.assertTrue(self.store.get(task["id"])["control"]["approved"])

    def test_cancel_prevents_unapproved_task_from_running(self):
        task = self.create("live")
        execute(task, self.store, {})
        self.store.request_cancel(task["id"])
        self.assertEqual(execute(task, self.store, {}, approve=True)["status"], "cancelled")

    def test_cancel_running_task_and_reject_concurrent_execution(self):
        task = self.create()
        entered, released = Event(), Event()

        def query(current):
            entered.set()
            if not released.wait(5):
                raise TimeoutError("test did not release query")
            return TOOLS["finance.query"](current)

        worker = Thread(target=execute, args=(task, self.store, {"finance.query": query}))
        worker.start()
        try:
            self.assertTrue(entered.wait(5))
            persisted = self.store.get(task["id"])
            self.assertEqual(execute(persisted, self.store, {})["status"], "running")
            self.store.request_cancel(task["id"])
        finally:
            released.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        current = self.store.get(task["id"])
        self.assertEqual(current["status"], "cancelled")
        self.assertEqual(current["steps"][1]["status"], "pending")
        self.assertIsNone(current["result"])
        self.assertIn("cancel_requested", [entry.get("event") for entry in current["logs"]])

    def test_call_budget_stops_before_next_tool(self):
        task = execute(self.create(max_calls=1), self.store)
        self.assertEqual(task["status"], "stopped")
        self.assertEqual(task["control"]["calls"], 1)
        self.assertEqual(task["steps"][1]["status"], "pending")
        self.assertIsNone(task["result"])

    def test_time_budget_stops_before_next_step(self):
        from unittest.mock import patch

        with patch("investbuddy.agent.monotonic", side_effect=[0, 0, 0, 2, 2]):
            task = execute(self.create(max_seconds=1), self.store)
        self.assertEqual(task["status"], "stopped")
        self.assertEqual(task["steps"][1]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
