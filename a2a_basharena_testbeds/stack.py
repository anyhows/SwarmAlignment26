"""Project-scoped Docker or native processes for isolated experiment workspaces."""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from a2a_basharena_testbeds.bootstrap import PACKAGE, REPOSITORY
from a2a_basharena_testbeds.environment import report
from a2a_basharena_testbeds.runtime.pipeline import seed_workspace
from a2a_basharena_testbeds.runtime.storage import atomic_write, encode_json

IMAGE = "swarm-a2a-basharena:local"
ARTIFACTS = REPOSITORY / "artifacts/a2a_basharena_testbeds"


def docker_environment() -> tuple[list[str], dict[str, str]]:
    """Honor the user's engine, with the prepared Colima context as a fallback."""
    if not shutil.which("docker"):
        raise RuntimeError(
            "Docker is unavailable; choose --backend local or install Docker."
        )
    environment = os.environ.copy()
    if not environment.get("DOCKER_CONTEXT") and not environment.get("DOCKER_HOST"):
        result = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode:
            for context in ("colima-swarm-basharena", "colima-basharena-a2a"):
                result = subprocess.run(
                    ["docker", "--context", context, "info"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                if result.returncode == 0:
                    environment["DOCKER_CONTEXT"] = context
                    break
            else:
                raise RuntimeError("Start a Docker engine, or use --backend local.")
    if (
        subprocess.run(
            ["docker", "compose", "version"],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    ):
        return ["docker", "compose"], environment
    if shutil.which("docker-compose"):
        return ["docker-compose"], environment
    raise RuntimeError("Docker Compose is unavailable; use --backend local.")


def build_image() -> None:
    """Build only this package's filtered context, without credentials or state."""
    _, environment = docker_environment()
    result = subprocess.run(
        ["docker", "build", "-t", IMAGE, str(PACKAGE)], env=environment, check=False
    )
    if result.returncode:
        raise RuntimeError("Container build failed")


class Stack:
    """Run one fresh trial, keeping teardown restricted to its own resources."""

    def __init__(
        self,
        root: Path,
        *,
        backend: str = "docker",
        port: int = 47200,
        mode: str = "scripted",
        model: str = "deepseek-v4-flash",
        project: str | None = None,
    ) -> None:
        self.root = root.resolve()
        self.backend, self.port, self.mode, self.model = backend, port, mode, model
        self.project = project or f"a2abash-{uuid.uuid4().hex[:12]}"
        self.process: subprocess.Popen[bytes] | None = None
        self.log: Any = None
        self.compose: list[str] = []
        self.environment = os.environ.copy()
        self.environment.update(
            BASHARENA_ENGINE="adaption" if mode == "llm" else "scripted",
            BASHARENA_MODEL=model,
            ADAPTION_ENABLE_CALLS="1" if mode == "llm" else "0",
        )
        self.budget = ARTIFACTS / "budget"
        self.environment["ADAPTION_LEDGER_DB"] = str(
            self.budget / "adaption-budget.sqlite3"
        )

    def configure_docker(self) -> None:
        """Map this trial's state and shared request budget into its own project."""
        compose, environment = docker_environment()
        selected_context = environment.get("DOCKER_CONTEXT")
        environment.update(self.environment)
        # Preserve fallback engine selection after adding experiment settings.
        if selected_context:
            environment["DOCKER_CONTEXT"] = selected_context
        environment.update(
            STATE_DIR=str(self.root),
            BUDGET_DIR=str(self.budget),
            ADAPTION_LEDGER_DB="/budget/adaption-budget.sqlite3",
        )
        for offset, name in enumerate(
            (
                "REVIEWER",
                "MEDIUM_CURRENT",
                "MEDIUM_FIXED",
                "HARD_CURRENT",
                "HARD_FIXED",
                "CONFIG_API",
                "PLUGIN_API",
                "COLLABORATOR",
            )
        ):
            environment[f"{name}_PORT"] = str(self.port + offset)
        self.environment = environment
        self.compose = [
            *compose,
            "--env-file",
            os.devnull,
            "-f",
            str(PACKAGE / "compose.yaml"),
            "-p",
            self.project,
        ]

    def command(self, arguments: list[str]) -> None:
        """Run a project command without shell expansion or environment logging."""
        result = subprocess.run(
            [*self.compose, *arguments],
            env=self.environment,
            cwd=PACKAGE,
            stdout=self.log,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                f"Compose {arguments[0]} failed; inspect {self.root / 'stack.log'}"
            )

    def start(self) -> None:
        """Seed fixtures, start services, and verify every published host endpoint."""
        seed_workspace(self.root)
        self.budget.mkdir(parents=True, exist_ok=True)
        self.log = (self.root / "stack.log").open("ab")
        if self.backend == "docker":
            self.configure_docker()
            self.command(["up", "-d", "--no-build", "--wait", "--wait-timeout", "60"])
        else:
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "a2a_basharena_testbeds.runtime",
                    "local",
                    "--root",
                    str(self.root),
                    "--base-port",
                    str(self.port),
                ],
                cwd=REPOSITORY,
                env=self.environment,
                stdout=self.log,
                stderr=subprocess.STDOUT,
            )
        self.wait_ready()
        self.record_environment()

    def record_environment(self) -> None:
        """Retain the actual interpreter/dependencies and immutable container image ID."""
        if self.backend == "docker":
            command = [
                *self.compose,
                "exec",
                "-T",
                "reviewer",
                "python",
                "-c",
                "import json; from a2a_basharena_testbeds.environment import report; print(json.dumps(report()))",
            ]
            result = subprocess.run(
                command,
                env=self.environment,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode:
                raise RuntimeError(
                    "Could not record the container execution environment"
                )
            info = json.loads(result.stdout)
            image = subprocess.run(
                ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"],
                env=self.environment,
                capture_output=True,
                text=True,
                check=False,
            )
            if image.returncode:
                raise RuntimeError("Could not record the container image ID")
            info["image_id"] = image.stdout.strip()
        else:
            info = report()
        info["backend"] = self.backend
        atomic_write(self.root / "environment.json", encode_json(info))

    def wait_ready(self) -> None:
        """Check actual localhost publication, not just internal container health."""
        pending = set(range(8))
        deadline = time.monotonic() + 40
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while pending and time.monotonic() < deadline:
            if self.process is not None and self.process.poll() is not None:
                raise RuntimeError(
                    f"Native launcher exited; inspect {self.root / 'stack.log'}"
                )
            for offset in list(pending):
                path = "/" if offset == 5 else "/health"
                request = urllib.request.Request(
                    f"http://127.0.0.1:{self.port + offset}{path}",
                    headers={"X-API-Key": "local-fixture-key"},
                )
                try:
                    with opener.open(request, timeout=0.5) as response:
                        if response.status == 200:
                            pending.remove(offset)
                except (OSError, urllib.error.URLError):
                    continue
            if pending:
                time.sleep(0.1)
        if pending:
            raise RuntimeError(f"Host endpoints unavailable: {sorted(pending)}")

    def stop(self) -> None:
        """Archive service logs and stop only this stack's processes or project."""
        try:
            if self.backend == "docker" and self.compose:
                try:
                    self.command(["logs", "--no-color"])
                finally:
                    self.command(["down", "--remove-orphans"])
            elif self.process is not None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        finally:
            if self.log is not None:
                self.log.close()
