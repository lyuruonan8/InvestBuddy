"""Runtime profiles for public review and trusted local development."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from investbuddy.store import Store


def profile():
    value = os.environ.get("INVESTBUDDY_PROFILE", "public-demo")
    if value not in {"public-demo", "local"}:
        raise ValueError("Unknown InvestBuddy runtime profile")
    return value


class DemoWorkspace:
    def __init__(self):
        self.directory = TemporaryDirectory(prefix="investbuddy-demo-")
        self.store = Store(Path(self.directory.name) / "demo.sqlite3", demo_only=True)
