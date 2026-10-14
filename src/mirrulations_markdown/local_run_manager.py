"""Local background-process management with readable, Git-ignored logs."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time


class LocalRunManager:
    """Manage one named local pipeline process without shell orchestration."""

    _local_processes = {}
    RUN_DIRECTORY_ENVIRONMENT_VARIABLE = "MIRRULATIONS_LOCAL_RUN_DIRECTORY"

    @staticmethod
    def _read_json(*, path):
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    @staticmethod
    def _write_json(*, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary_path.replace(path)

    @staticmethod
    def _is_running(*, pid):
        local_process = LocalRunManager._local_processes.get(pid)
        if local_process is not None:
            return local_process.poll() is None
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    @staticmethod
    def start(*, run_root, command, description):
        latest_path = run_root / "latest.json"
        latest = LocalRunManager._read_json(path=latest_path)
        if latest and LocalRunManager._is_running(pid=latest["pid"]):
            raise ValueError(
                f"local_run_manager.py Error: {description} is already running as "
                f"PID {latest['pid']}"
            )
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_directory = run_root / run_id
        run_directory.mkdir(parents=True, exist_ok=False)
        log_path = run_directory / "status.log"
        started_at = datetime.now(timezone.utc).isoformat()
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"{started_at} Starting {description}\n")
            log_file.flush()
            process = subprocess.Popen(
                command,
                cwd=Path(__file__).resolve().parents[2],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env={
                    **os.environ,
                    LocalRunManager.RUN_DIRECTORY_ENVIRONMENT_VARIABLE: str(run_directory),
                },
            )
            LocalRunManager._local_processes[process.pid] = process
        status = {
            "run_id": run_id, "description": description, "pid": process.pid,
            "started_at": started_at, "run_directory": str(run_directory),
            "log_path": str(log_path), "command": command,
        }
        LocalRunManager._write_json(path=run_directory / "status.json", value=status)
        LocalRunManager._write_json(path=latest_path, value=status)
        return LocalRunManager.status(run_root=run_root)

    @staticmethod
    def status(*, run_root):
        latest = LocalRunManager._read_json(path=run_root / "latest.json")
        if not latest:
            return {"status": "not-started", "run_root": str(run_root)}
        running = LocalRunManager._is_running(pid=latest["pid"])
        log_path = Path(latest["log_path"])
        lines = log_path.read_text(encoding="utf-8").splitlines() if log_path.is_file() else []
        attention = LocalRunManager._read_json(
            path=Path(latest["run_directory"]) / "attention_required.json"
        )
        return {
            **latest,
            "status": "running" if running else "finished",
            "last_log_line": lines[-1] if lines else None,
            "attention_required": attention,
        }

    @staticmethod
    def signal_attention(*, category, message, action_url=None):
        """Persist and announce a human-action requirement for a managed run."""
        run_directory_value = os.getenv(
            LocalRunManager.RUN_DIRECTORY_ENVIRONMENT_VARIABLE, ""
        ).strip()
        signal = {
            "category": category,
            "message": message,
            "action_url": action_url,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if run_directory_value:
            run_directory = Path(run_directory_value)
            LocalRunManager._write_json(
                path=run_directory / "attention_required.json", value=signal,
            )
            with (run_directory / "status.log").open("a", encoding="utf-8") as log_file:
                log_file.write(f"ATTENTION REQUIRED [{category}]: {message}\n")
                if action_url:
                    log_file.write(f"Action: {action_url}\n")
        if sys.platform == "darwin":
            notification_message = message.replace('"', "'")[:180]
            try:
                subprocess.run(
                    [
                        "osascript", "-e",
                        f'display notification "{notification_message}" '
                        'with title "Mirrulations pipeline needs attention" sound name "Basso"',
                    ],
                    check=False, capture_output=True, text=True, timeout=10,
                )
            except (OSError, subprocess.SubprocessError):
                pass
        return signal

    @staticmethod
    def wait(*, run_root, poll_seconds=2):
        status = LocalRunManager.status(run_root=run_root)
        if status["status"] == "not-started":
            return status
        while status["status"] == "running":
            time.sleep(poll_seconds)
            status = LocalRunManager.status(run_root=run_root)
        return status

    @staticmethod
    def print_status(*, status):
        attention = status.get("attention_required")
        if attention:
            print("\aATTENTION REQUIRED")
            print(f"Reason: {attention['message']}")
            if attention.get("action_url"):
                print(f"Action: {attention['action_url']}")
        print(f"Status: {status['status']}")
        if status.get("stage"):
            stage4_documents = status.get("stage4_documents")
            stage_text = f"Stage {status['stage']}"
            if status["stage"] == "4" and stage4_documents is not None:
                stage_text += f" ({stage4_documents} documents linked)"
            print(stage_text)
        if status.get("percent_complete") is not None and status.get("expected_segments"):
            print(
                f"Progress: {status['percent_complete']}% "
                f"({status.get('segments_started', 0)}/"
                f"{status.get('expected_segments')} segments)"
            )
        elif status.get("segments_started") is not None:
            print(f"Segments started: {status['segments_started']}")
        if status.get("pid"):
            print(f"PID: {status['pid']}")
        if status.get("log_path"):
            print(f"Log: {status['log_path']}")
        if status.get("last_log_line"):
            print(f"Latest: {status['last_log_line']}")