import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from investbuddy.agent import execute
from investbuddy.planning import MockProvider, make_plan, validate
from investbuddy.research import resolve_followup, summarize
from investbuddy.store import Store
from investbuddy.tools import TOOLS


def response(topic):
    return json.dumps({"tools": [{"tool": "research.scope", "arguments": {"topic": topic}}]})


class ResearchTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = Store(Path(directory.name) / "test.sqlite3")
        self.thread = self.store.create_thread("300750.SZ", "2026-01-01", "2026-06-30")

    def create(self, goal, mode="demo", context=None, provider=None):
        steps, strategy = make_plan(goal, mode, context, provider)
        return self.store.create(*resolve_followup(goal, self.thread)[:1], goal,
                                 self.thread["start"], self.thread["end"], steps, mode,
                                 thread_id=self.thread["id"], planning=strategy, context=context)

    def test_plans_execute_different_work(self):
        finance = execute(self.create("财务"), self.store)
        valuation = execute(self.create("估值"), self.store)
        risk = execute(self.create("风险"), self.store)
        self.assertEqual({row["field"] for row in finance["result"]["evidence"]}, {"revenue", "net_income"})
        self.assertEqual({row["field"] for row in valuation["result"]["evidence"]}, {"pe_ttm"})
        self.assertEqual(risk["result"]["evidence"], [])
        self.assertEqual(risk["steps"][0]["action"], "research.risk")

    def test_illegal_tool_and_parameters_rejected(self):
        for invalid in [response("shell"), response("financial").replace("research.scope", "finance.query_live"),
                        response("financial").replace('"financial"', '"financial", "url": "https://example.org"')]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate(invalid)

    def test_provider_failure_falls_back(self):
        class Unavailable:
            def generate(self, context):
                raise TimeoutError

        steps, strategy = make_plan("估值", "live", provider=Unavailable())
        self.assertIn("降级", strategy)
        self.assertEqual(steps[0]["topics"], ["valuation"])

    def test_followup_inherits_and_reuses_context_after_compression(self):
        older = execute(self.create("财务"), self.store)
        latest = execute(self.create("估值"), self.store)
        other = self.store.create_thread("300750.SZ", "2026-01-01", "2026-06-30")
        self.assertEqual(self.store.thread_tasks(other["id"]), [])
        self.assertEqual(resolve_followup("继续", self.thread), ("300750.SZ", "2026-01-01", "2026-06-30"))
        context = summarize(self.thread, self.store.thread_tasks(self.thread["id"]), 1)
        self.assertEqual(context["compressed"][0]["task_id"], older["id"])
        self.assertIn("E1", context["compressed"][0]["evidence_by_date"]["2026-03-31"])
        self.assertTrue(context["constraints"])
        followup = execute(self.create("继续", context=context), self.store)
        self.assertEqual(followup["steps"][0]["topics"], latest["steps"][0]["topics"])
        self.assertEqual(followup["status"], "completed")
        self.assertEqual(self.store.get(older["id"])["result"], older["result"])

    def test_ambiguous_followup_requires_clarification(self):
        for goal in ("比亚迪估值", "600519.SH 估值", "上季度营收", "它呢"):
            with self.subTest(goal=goal), self.assertRaises(ValueError):
                resolve_followup(goal, self.thread)

    def test_private_holdings_are_rejected_before_persistence(self):
        with self.assertRaises(ValueError):
            self.store.create("300750.SZ", "我的持仓是 100 股", self.thread["start"], self.thread["end"], [])
        self.assertEqual(self.store.recent(), [])

    def test_preference_is_opt_in_persistent_and_deletable(self):
        self.assertEqual(self.store.preferences(), [])
        with self.assertRaises(ValueError):
            self.store.save_preference("持仓明细")
        self.store.save_preference("默认关注财务")
        self.assertEqual(Store(self.store.path).preferences(), ["默认关注财务"])
        self.store.delete_preference("默认关注财务")
        self.assertEqual(Store(self.store.path).preferences(), [])

    def test_model_plan_cannot_bypass_approval_and_resume_keeps_it(self):
        task = self.create("估值", "live", provider=MockProvider(response("valuation")))
        self.assertIn("Mock", task["planning"])
        self.assertEqual(execute(task, self.store, {})["status"], "awaiting_approval")

        def fail(current):
            raise TimeoutError("fixture")

        self.assertEqual(execute(task, self.store, {"finance.query_live": fail}, approve=True)["status"], "failed")
        tools = {**TOOLS, "finance.query_live": TOOLS["finance.query"]}
        result = execute(self.store.get(task["id"]), self.store, tools)
        self.assertEqual(result["status"], "completed")
        context = summarize(self.thread, [result], 1)
        self.assertEqual(len(context["recent"][0]["confirmations"]), 1)

    def test_model_advice_is_rejected_and_never_in_plan(self):
        output = response("financial")[:-1] + ', "advice":"立刻买入，保证上涨"}'
        steps, strategy = make_plan("估值", "demo", provider=MockProvider(output))
        self.assertIn("降级", strategy)
        self.assertNotIn("立刻买入", str(steps))


if __name__ == "__main__":
    unittest.main()
