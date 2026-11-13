from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from investbuddy.agent import execute
from investbuddy.fuyao_data import MARKET_TZ, query_fuyao
from investbuddy.planning import make_plan
from investbuddy.store import Store


def fixture(url, key):
    assert key == "fixture"
    now = datetime.now(MARKET_TZ)
    timestamp = int(now.timestamp() * 1000)
    row = dict(thscode="600519.SH", last_price=100, pe_ttm=20,
               operating_income=400, parent_holder_net_profit=200,
               period="annual", fiscal_period="FY", currency="CNY",
               period_end_ms=int(datetime(now.year - 1, 12, 31, tzinfo=MARKET_TZ).timestamp() * 1000))
    return 200, dict(code=0, request_id="sample", data=dict(timestamp=timestamp, item=[row]))


class FuyaoTest(unittest.TestCase):
    def setUp(self):
        env = patch.dict("os.environ", {"FUYAO_API_KEY": "fixture"})
        env.start()
        self.addCleanup(env.stop)
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "test.sqlite3"

    def test_complete_task_requires_approval_and_has_no_pe_change(self):
        store = Store(self.path)
        steps, _ = make_plan("财务及估值", "fuyao")
        task = store.create("600519.SH", "财务及估值", "2026-01-01", "2026-12-31", steps, "fuyao")

        def query(task):
            return query_fuyao(task, fixture)

        self.assertEqual(execute(task, store, {})["status"], "awaiting_approval")
        result = execute(task, store, {"finance.query_fuyao": query}, approve=True)["result"]
        self.assertEqual([row["field"] for row in result["evidence"]],
                         ["last_price", "operating_income", "net_income", "pe_ttm"])
        self.assertTrue(all(row["request_id"] == "sample" and row["data_at"]
                            for row in result["evidence"]))
        self.assertEqual(len(result["metrics"]), 1)
        self.assertEqual(result["metrics"][0]["value"], 50)
        self.assertIn("无法计算", result["report"]["warnings"][0])

    def test_demo_rejects_fuyao(self):
        store = Store(self.path, demo_only=True)
        steps, _ = make_plan("估值", "fuyao")
        with self.assertRaises(ValueError):
            store.create("600519.SH", "估值", "2026-01-01", "2026-12-31", steps, "demo")

    def test_auth_and_rate_limit(self):
        for status, code, message in ((200, 2003, "鉴权"), (429, None, "额度")):
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, message):
                query_fuyao({"symbol": "600519.SH"}, lambda url, key: (status, {"code": code}))

    def test_missing_and_wrong_symbol(self):
        for field, value, message in (("last_price", None, "必需字段"),
                                      ("thscode", "002594.SZ", "证券代码不匹配")):
            def invalid(url, key):
                status, payload = fixture(url, key)
                payload["data"]["item"][0][field] = value
                return status, payload
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                query_fuyao({"symbol": "600519.SH"}, invalid)
