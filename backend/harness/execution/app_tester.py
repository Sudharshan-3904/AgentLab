"""Application testing manager for detecting, building, launching, probing, and testing generated apps."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import urllib.error
import urllib.request
import uuid

from pydantic import BaseModel, Field

logger = logging.getLogger("agentlab.app_tester")


class AppInfo(BaseModel):
    """Metadata describing a detected application."""

    app_type: str = Field(..., description="Detected type: python_http, python_fastapi, python_flask, static_html, node, custom")
    entry_point: str = Field(..., description="Main file or entry script")
    suggested_command: List[str] = Field(default_factory=list, description="Recommended command to launch application")
    health_path: str = Field(default="/", description="Default HTTP path to probe for health status")
    working_directory: str = Field(..., description="Root working directory of the application")


class AppDetector:
    """Detects application runtime and entry point from workspace files."""

    @classmethod
    def detect(cls, workspace_path: str | Path) -> Optional[AppInfo]:
        """Inspect the directory tree to identify runnable web application projects."""
        ws = Path(workspace_path).resolve()
        if not ws.exists() or not ws.is_dir():
            return None

        # Check for python applications
        candidates = ["app.py", "main.py", "server.py"]
        for cand in candidates:
            cand_path = ws / cand
            if cand_path.is_file():
                try:
                    content = cand_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    content = ""

                if "fastapi" in content.lower() or "uvicorn" in content.lower():
                    # FastAPI app
                    module_name = cand[:-3]
                    return AppInfo(
                        app_type="python_fastapi",
                        entry_point=cand,
                        suggested_command=[sys.executable, "-m", "uvicorn", f"{module_name}:app", "--host", "127.0.0.1", "--port", "{port}"],
                        health_path="/docs",
                        working_directory=str(ws),
                    )
                elif "flask" in content.lower():
                    return AppInfo(
                        app_type="python_flask",
                        entry_point=cand,
                        suggested_command=[sys.executable, cand],
                        health_path="/",
                        working_directory=str(ws),
                    )
                else:
                    return AppInfo(
                        app_type="python_http",
                        entry_point=cand,
                        suggested_command=[sys.executable, cand],
                        health_path="/",
                        working_directory=str(ws),
                    )

        # Check for static html
        index_html = ws / "index.html"
        if index_html.is_file():
            return AppInfo(
                app_type="static_html",
                entry_point="index.html",
                suggested_command=[sys.executable, "-m", "http.server", "{port}", "--bind", "127.0.0.1"],
                health_path="/",
                working_directory=str(ws),
            )

        # Check for node/package.json
        pkg_json = ws / "package.json"
        if pkg_json.is_file():
            return AppInfo(
                app_type="node",
                entry_point="package.json",
                suggested_command=["npm", "start"],
                health_path="/",
                working_directory=str(ws),
            )

        return None


class LaunchedApp:
    """Represents an actively running application launched for testing/preview."""

    def __init__(
        self,
        app_id: str,
        process: subprocess.Popen,
        host: str,
        port: int,
        command: List[str],
        cwd: str,
        health_path: str = "/",
    ):
        self.app_id = app_id
        self.process = process
        self.host = host
        self.port = port
        self.command = command
        self.cwd = cwd
        self.health_path = health_path
        self.url = f"http://{host}:{port}"
        self.launch_time = time.time()
        self.status = "running"
        self._logs: List[str] = []
        self._lock = threading.Lock()

        # Start background log reader threads
        self._stdout_thread = threading.Thread(
            target=self._read_stream, args=(self.process.stdout, "STDOUT"), daemon=True
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stream, args=(self.process.stderr, "STDERR"), daemon=True
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _read_stream(self, stream, prefix: str) -> None:
        if not stream:
            return
        try:
            for line in iter(stream.readline, ""):
                if not line:
                    break
                with self._lock:
                    self._logs.append(f"[{prefix}] {line.rstrip()}")
        except Exception:
            pass

    def is_alive(self) -> bool:
        """Check if the process is currently still running."""
        return self.process.poll() is None

    def get_logs(self, max_lines: int = 100) -> str:
        """Return the collected stdout/stderr logs."""
        with self._lock:
            return "\n".join(self._logs[-max_lines:])

    def stop(self, timeout: float = 3.0) -> None:
        """Stop the application gracefully or forcefully."""
        if not self.is_alive():
            self.status = "stopped"
            return

        try:
            self.process.terminate()
            self.process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, Exception):
            try:
                self.process.kill()
                self.process.wait(timeout=1.0)
            except Exception:
                pass
        finally:
            self.status = "stopped"


class AppTestingManager:
    """Manages application detection, builds, execution launch, health checking, and feedback."""

    def __init__(self, on_event: Optional[Callable[[str, str, Dict[str, Any]], None]] = None):
        self.on_event = on_event
        self.active_apps: Dict[str, LaunchedApp] = {}

    def _emit(self, event_type: str, source: str, payload: Dict[str, Any]) -> None:
        if self.on_event:
            self.on_event(event_type, source, payload)

    @staticmethod
    def find_available_port(start_port: int = 8000, end_port: int = 9999) -> int:
        """Find an unallocated TCP port bound to localhost."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def detect(self, workspace_path: str | Path) -> Optional[AppInfo]:
        """Detect the application type and launch command in the target directory."""
        return AppDetector.detect(workspace_path)

    def build(
        self,
        command: str | List[str],
        cwd: str,
        timeout: float = 60.0,
        env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Run an optional build or pre-launch preparation step."""
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        if isinstance(command, str):
            cmd_args = command.split()
        else:
            cmd_args = list(command)

        start = time.time()
        try:
            proc = subprocess.run(
                cmd_args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=full_env,
            )
            duration = time.time() - start
            return {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "duration_seconds": duration,
            }
        except subprocess.TimeoutExpired as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": e.stdout or "",
                "stderr": f"Build timed out after {timeout} seconds",
                "duration_seconds": timeout,
            }
        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "duration_seconds": time.time() - start,
            }

    def launch(
        self,
        workspace_path: str | Path,
        command: Optional[str | List[str]] = None,
        port: Optional[int] = None,
        host: str = "127.0.0.1",
        health_path: str = "/",
        env: Optional[Dict[str, str]] = None,
    ) -> LaunchedApp:
        """Launch the application process on an available or specified port."""
        ws = Path(workspace_path).resolve()
        target_port = port or self.find_available_port()

        if command is None:
            detected = self.detect(ws)
            if not detected:
                raise ValueError(f"Could not auto-detect runnable application in {ws}")
            cmd_parts = [part.replace("{port}", str(target_port)) for part in detected.suggested_command]
            health_path = detected.health_path
        elif isinstance(command, str):
            cmd_str = command.replace("{port}", str(target_port))
            cmd_parts = cmd_str.split()
        else:
            cmd_parts = [str(c).replace("{port}", str(target_port)) for c in command]

        full_env = os.environ.copy()
        full_env["PORT"] = str(target_port)
        full_env["HOST"] = host
        full_env["PYTHONUNBUFFERED"] = "1"
        if env:
            full_env.update(env)

        app_id = f"app-{uuid.uuid4().hex[:8]}"

        try:
            proc = subprocess.Popen(
                cmd_parts,
                cwd=str(ws),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=full_env,
                bufsize=1,
            )
        except Exception as e:
            logger.error("Failed to launch application: %s", e)
            raise RuntimeError(f"Failed to start application command '{' '.join(cmd_parts)}': {e}") from e

        launched = LaunchedApp(
            app_id=app_id,
            process=proc,
            host=host,
            port=target_port,
            command=cmd_parts,
            cwd=str(ws),
            health_path=health_path,
        )

        self.active_apps[app_id] = launched

        self._emit(
            "APPLICATION_LAUNCHED",
            "app_testing_manager",
            {
                "app_id": app_id,
                "url": launched.url,
                "host": host,
                "port": target_port,
                "command": cmd_parts,
                "cwd": str(ws),
            },
        )
        return launched

    def health_check(
        self,
        app_or_url: str | LaunchedApp,
        path: Optional[str] = None,
        timeout: float = 10.0,
        retry_interval: float = 0.4,
        expected_statuses: Tuple[int, ...] = (200, 201, 204, 301, 302, 304, 404),
    ) -> bool:
        """Poll the application endpoint until it responds with an acceptable HTTP status or times out."""
        if isinstance(app_or_url, LaunchedApp):
            base_url = app_or_url.url
            target_path = path or app_or_url.health_path
            app_obj: Optional[LaunchedApp] = app_or_url
        else:
            base_url = app_or_url.rstrip("/")
            target_path = path or "/"
            app_obj = None

        full_url = f"{base_url}{target_path}"
        deadline = time.time() + timeout
        last_error = ""

        while time.time() < deadline:
            if app_obj and not app_obj.is_alive():
                self._emit(
                    "APPLICATION_HEALTH_CHECK",
                    "app_testing_manager",
                    {"url": full_url, "healthy": False, "error": "Process terminated prematurely"},
                )
                return False

            try:
                req = urllib.request.Request(
                    full_url,
                    headers={"User-Agent": "AgentLab-AppTester/1.0"},
                )
                with urllib.request.urlopen(req, timeout=1.5) as response:
                    status = response.getcode()
                    if status in expected_statuses:
                        if app_obj:
                            app_obj.status = "healthy"
                        self._emit(
                            "APPLICATION_HEALTH_CHECK",
                            "app_testing_manager",
                            {"url": full_url, "healthy": True, "status_code": status},
                        )
                        return True
            except urllib.error.HTTPError as e:
                if e.code in expected_statuses:
                    if app_obj:
                        app_obj.status = "healthy"
                    self._emit(
                        "APPLICATION_HEALTH_CHECK",
                        "app_testing_manager",
                        {"url": full_url, "healthy": True, "status_code": e.code},
                    )
                    return True
                last_error = f"HTTP {e.code}: {e.reason}"
            except Exception as e:
                last_error = str(e)

            time.sleep(retry_interval)

        self._emit(
            "APPLICATION_HEALTH_CHECK",
            "app_testing_manager",
            {"url": full_url, "healthy": False, "error": last_error},
        )
        return False

    def collect_feedback(
        self,
        execution_id: str,
        feedback_text: str,
        passed: bool = True,
        rating: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record human or automated preview feedback regarding the launched application."""
        feedback_payload = {
            "execution_id": execution_id,
            "feedback": feedback_text,
            "passed": passed,
            "rating": rating,
            "metadata": metadata or {},
            "timestamp": time.time(),
        }
        self._emit("USER_FEEDBACK", "app_testing_manager", feedback_payload)
        return feedback_payload

    def stop(self, app_id: str) -> None:
        """Stop and unregister a running application."""
        app = self.active_apps.pop(app_id, None)
        if app:
            app.stop()
            self._emit(
                "APPLICATION_STOPPED",
                "app_testing_manager",
                {"app_id": app_id, "url": app.url},
            )

    def stop_all(self) -> None:
        """Stop all currently registered applications."""
        for app_id in list(self.active_apps.keys()):
            self.stop(app_id)
