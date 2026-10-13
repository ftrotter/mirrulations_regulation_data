"""Tests for local pipeline process management."""

from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()