"""Synthetic response fixtures matching the public endpoint schema."""
from datetime import date
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from investbuddy.agent import execute, plan
from investbuddy.market_data import query_eastmoney
from investbuddy.quality import analyze_live
from investbuddy.store import Store


def fixture_fetch(url):
    params = parse_qs(urlsplit(url).query)
    assert "300750" in params["filter"][0]
    if params["reportName"] == ["RPT_DMSK_FN_INCOME"]:
        rows = [dict(SECUCODE="300750.SZ", REPORT_DATE="2026-03-31 00:00:00",
                     NOTICE_DATE="2026-04-16 00:00:00", TOTAL_OPERATE_INCOME=100,
                     PARENT_NETPROFIT=12)]
    else:
        rows = [dict(SECUCODE="300750.SZ", TRADE_DATE=day, PE_TTM=pe)
                for day, pe in [("2026-04-20", 21), ("2026-04-21", 19)]]
    return {"success": True, "result": {"data": rows, "pages": 1, "count": len(rows)}}


class MarketDataTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = Store(Path(directory.name) / "test.sqlite3")
        self.task = self.store.create("300750.SZ", "financial review", "2026-01-01", "2026-04-22",
                                      plan("financial review", "live"), mode="live")

    def evidence(self):
        return query_eastmoney(self.task, fetch=fixture_fetch)

    def test_provider_fixture_and_persisted_trace(self):
        execute(self.task, self.store, {"finance.query_live": lambda task: self.evidence()}, approve=True)
        task = self.store.recent()[0]
        self.assertEqual(task["status"], "completed")
        result = task["result"]
        self.assertEqual([metric["value"] for metric in result["metrics"]], [12, -2])
        by_id = {row["id"]: row for row in result["evidence"]}
        for metric in result["metrics"]:
            for identifier in metric["evidence"]:
                row = by_id[identifier]
                self.assertIn(row["raw_field"], parse_qs(urlsplit(row["source_url"]).query)["columns"][0])
                self.assertTrue(row["queried_at"] and row["unit"] and row["basis"])
        self.assertEqual(by_id["E1"]["report_period"], "2026-03-31")
        self.assertEqual(by_id["E1"]["disclosed_at"], "2026-04-16")
        self.assertIsNone(by_id["E3"]["report_period"])

    def test_missing_field_blocks_financial_conclusion(self):
        rows = self.evidence()
        rows[0]["value"] = None
        result = analyze_live(rows, self.task["end"])
        self.assertEqual([metric["value"] for metric in result["metrics"]], [-2])
        self.assertFalse(result["facts"])
        self.assertTrue(any("revenue" in warning for warning in result["warnings"]))

    def test_stale_data_blocks_conclusions(self):
        result = analyze_live(self.evidence(), "2026-11-01", today=date(2026, 11, 1))
        self.assertFalse(result["metrics"])
        self.assertEqual(sum("数据过期" in warning for warning in result["warnings"]), 3)

    def test_conflicting_sources_block_valuation(self):
        rows = self.evidence()
        rows.append(dict(rows[-1], id="E5", source="Fixture B", value=25))
        result = analyze_live(rows, self.task["end"])
        self.assertEqual([metric["value"] for metric in result["metrics"]], [12])
        self.assertTrue(any("Fixture B" in warning and "E4" in warning for warning in result["warnings"]))

    def test_provider_timeout_keeps_live_task_failed(self):
        def timeout(url):
            raise TimeoutError("fixture timeout")

        execute(self.task, self.store, {"finance.query_live": lambda task: query_eastmoney(task, fetch=timeout)}, approve=True)
        task = self.store.recent()[0]
        self.assertEqual(task["status"], "failed")
        self.assertIn("TimeoutError", task["error"])
        self.assertIsNone(task["result"])


if __name__ == "__main__":
    unittest.main()
