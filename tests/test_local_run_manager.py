"""Tests for local pipeline process management."""

from pathlib import Path
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.local_run_manager import LocalRunManager  # noqa: E402


class LocalRunManagerTest(unittest.TestCase):
    def test_background_run_writes_readable_log_and_status(self):
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "runs"
            started = LocalRunManager.start(
                run_root=run_root,
                command=[sys.executable, "-c", "print('human readable completion')"],
                description="test run",
            )
            self.assertEqual("running", started["status"])
            finished = LocalRunManager.wait(run_root=run_root, poll_seconds=0.01)
            self.assertEqual("finished", finished["status"])
            self.assertIn(
                "human readable completion",
                Path(finished["log_path"]).read_text(encoding="utf-8"),
            )

    def test_attention_signal_is_durable_and_visible_in_status(self):
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "runs"
            script = (
                f"import sys; sys.path.insert(0, {str(Path(__file__).parents[1] / 'src')!r}); "
                "from mirrulations_markdown.local_run_manager import LocalRunManager; "
                "LocalRunManager.signal_attention(category='provider_budget_exhausted', "
                "message='Credits depleted.', action_url='https://billing.example/')"
            )
            status = LocalRunManager.start(
                run_root=run_root,
                command=[sys.executable, "-c", script],
                description="attention test",
            )
            finished = LocalRunManager.wait(run_root=run_root, poll_seconds=0.01)
            self.assertEqual(
                "provider_budget_exhausted",
                finished["attention_required"]["category"],
            )
            signal_path = Path(status["run_directory"]) / "attention_required.json"
            self.assertEqual(
                "https://billing.example/",
                json.loads(signal_path.read_text())["action_url"],
            )


if __name__ == "__main__":
    unittest.main()