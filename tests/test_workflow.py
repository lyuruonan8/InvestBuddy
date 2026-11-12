import tempfile
import unittest
from pathlib import Path

from investbuddy.agent import execute, plan
from investbuddy.store import Store


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "test.sqlite3"
        self.store = Store(self.path)

    def task(self, start="2026-01-01", end="2026-06-30"):
        goal = "研究宁德时代财务、估值与风险"
        return self.store.create("300750.SZ", goal, start, end, plan(goal))

    def test_completed_with_traceable_metrics(self):
        execute(self.task(), self.store)
        task = Store(self.path).recent()[0]
        self.assertEqual(task["status"], "completed")
        self.assertTrue(all(step["status"] == "completed" for step in task["steps"]))
        self.assertEqual(task["result"]["report"]["mode"], "合成示例")
        self.assertEqual(task["result"]["metrics"][-1]["value"], -2)
        ids = {row["id"] for row in task["result"]["evidence"]}
        for metric in task["result"]["metrics"]:
            self.assertTrue(set(metric["evidence"]) <= ids)

    def test_provider_failure(self):
        def unavailable(task):
            raise TimeoutError("provider timed out")

        execute(self.task(), self.store, {"finance.query": unavailable})
        task = Store(self.path).recent()[0]
        self.assertEqual(task["status"], "failed")
        self.assertIn("TimeoutError", task["error"])
        self.assertEqual(task["steps"][1]["status"], "pending")
        self.assertIsNone(task["result"])

    def test_missing_data(self):
        task = execute(self.task("2025-01-01", "2025-12-31"), self.store)
        self.assertEqual(task["status"], "failed")
        self.assertIsNone(task["result"])

    def test_single_period(self):
        task = execute(self.task("2026-04-01"), self.store)
        self.assertIn("无法计算估值变化", task["result"]["report"]["uncertainty"])


if __name__ == "__main__":
    unittest.main()
