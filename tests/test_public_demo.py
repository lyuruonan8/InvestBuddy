from datetime import date
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from investbuddy.agent import execute, plan
from investbuddy.runtime import DemoWorkspace, profile
from investbuddy.store import Store


class PublicDemoTest(unittest.TestCase):
    def workspace(self):
        workspace = DemoWorkspace()
        self.addCleanup(workspace.directory.cleanup)
        return workspace.store

    def task(self, store, **kwargs):
        return store.create("300750.SZ", "财务", "2026-01-01", "2026-06-30", plan("财务"), **kwargs)

    def test_profile_defaults_safe_and_rejects_typo(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(profile(), "public-demo")
        with patch.dict(os.environ, {"INVESTBUDDY_PROFILE": "invalid"}):
            with self.assertRaises(ValueError):
                profile()

    def test_stores_isolate_tasks_threads_and_preferences(self):
        first, second = self.workspace(), self.workspace()
        self.assertNotEqual(first.path, second.path)
        thread = first.create_thread("300750.SZ", "2026-01-01", "2026-06-30")
        task = self.task(first, thread_id=thread["id"])
        first.save_preference("默认关注财务")
        self.assertEqual(second.threads(), [])
        self.assertEqual(second.thread_tasks(thread["id"]), [])
        self.assertEqual(second.preferences(), [])
        self.assertIsNone(second.get(task["id"]))
        second.request_cancel(task["id"])
        second.delete_preference("默认关注财务")
        self.assertEqual(first.get(task["id"])["status"], "pending")
        self.assertEqual(first.preferences(), ["默认关注财务"])

    def test_server_rejects_live_creation_and_injected_live_step(self):
        store = self.workspace()
        with self.assertRaises(ValueError):
            self.task(store, mode="live")
        task = self.task(store)
        task["steps"][0]["action"] = "finance.query_live"
        store.save(task)
        with self.assertRaises(PermissionError):
            execute(task, store, {}, approve=True)

    def test_public_failure_redacts_internal_details_and_resume_uses_approval(self):
        store = self.workspace()
        task = self.task(store)
        self.assertEqual(execute(task, store)["status"], "awaiting_approval")

        def fail(current):
            raise RuntimeError("internal marker")

        task = execute(task, store, {"finance.query": fail}, approve=True)
        self.assertEqual(task["status"], "failed")
        self.assertNotIn("internal marker", str(task))
        recovered = execute(task, store)
        self.assertEqual(recovered["status"], "completed")
        self.assertEqual(sum(entry.get("event") == "approved" for entry in recovered["logs"]), 1)

    def test_two_page_sessions_do_not_share_history_and_demo_runs(self):
        with patch.dict(os.environ, {"INVESTBUDDY_PROFILE": "public-demo"}):
            app_path = str(Path(__file__).resolve().parents[1] / "app.py")
            with patch("investbuddy.runtime.Store", wraps=Store) as opened:
                first = AppTest.from_file(app_path).run()
                self.assertFalse(first.exception)
                self.assertEqual(first.selectbox[2].options, ["演示 · 合成数据"])
                first.button[-1].click().run()
                self.assertFalse(first.exception)
                workspace = first.session_state["demo_workspace"]
                task = workspace.store.recent()[0]
                self.assertEqual(task["status"], "awaiting_approval")
                first.button(key=f'approve_{task["id"]}').click().run()
                deadline = monotonic() + 10
                while workspace.store.get(task["id"])["status"] in {"awaiting_approval", "running"}:
                    if monotonic() >= deadline:
                        self.fail("demo task did not finish")
                    sleep(.02)
                first.run()
                self.assertFalse(first.exception)
                self.assertEqual(workspace.store.get(task["id"])["status"], "completed")
                self.assertEqual(len(first.get("plotly_chart")), 1)
                second = AppTest.from_file(app_path).run()
                self.assertFalse(second.exception)
                self.assertEqual(second.selectbox(key="thread_selector").options, ["新建线程"])
                self.assertTrue(all(call.kwargs.get("demo_only") for call in opened.call_args_list))

    def test_page_handles_empty_data_without_normal_report(self):
        with patch.dict(os.environ, {"INVESTBUDDY_PROFILE": "public-demo"}):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
            app.date_input[0].set_value(date(2025, 1, 1))
            app.date_input[1].set_value(date(2025, 2, 1))
            app.button[-1].click().run()
            self.assertFalse(app.exception)
            store = app.session_state["demo_workspace"].store
            task = store.recent()[0]
            execute(task, store, approve=True)
            app.run()
            self.assertFalse(app.exception)
            self.assertIn("没有可用数据", app.error[0].value)
            self.assertFalse(app.get("plotly_chart"))


if __name__ == "__main__":
    unittest.main()
