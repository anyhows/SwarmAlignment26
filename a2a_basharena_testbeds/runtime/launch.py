"""Start the local HTTP environment and run an optional benign smoke cycle."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import ExitStack
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from a2a_basharena_testbeds.runtime.agents import call_agent
from a2a_basharena_testbeds.runtime.pipeline import seed_workspace
from a2a_basharena_testbeds.runtime.repository import (
    repository_headers,
    stage_from_repository,
)
from a2a_basharena_testbeds.runtime.storage import atomic_write, encode_json
from a2a_basharena_testbeds.runtime.workflow_cli import workflow_demo

if TYPE_CHECKING:
    from types import FrameType


SERVICE_COUNT = 8
AGENT_COUNT = 5
MIN_BASE_PORT = 1024
MAX_BASE_PORT = 65535 - SERVICE_COUNT + 1
SERVICE_COMMANDS = (
    ("reviewer", ["serve", "--role", "reviewer"]),
    (
        "medium-vulnerable",
        [
            "serve",
            "--role",
            "executor",
            "--case",
            "medium",
            "--mode",
            "vulnerable",
        ],
    ),
    (
        "medium-fixed",
        ["serve", "--role", "executor", "--case", "medium", "--mode", "fixed"],
    ),
    (
        "hard-vulnerable",
        [
            "serve",
            "--role",
            "executor",
            "--case",
            "hard",
            "--mode",
            "vulnerable",
        ],
    ),
    (
        "hard-fixed",
        ["serve", "--role", "executor", "--case", "hard", "--mode", "fixed"],
    ),
    ("config-api", ["repository", "--case", "medium"]),
    ("plugin-api", ["repository", "--case", "hard"]),
    ("collaborator", ["serve", "--role", "collaborator"]),
)


async def benign_demo(root: Path, host: str, port: int) -> dict[str, Any]:
    """Stage API data and run both cases in both modes with unchanged inputs."""
    staged = [
        await stage_from_repository(root, "medium", f"{host}:{port + 5}"),
        await stage_from_repository(root, "hard", f"{host}:{port + 6}"),
    ]
    results = []
    for offset, case, mode in (
        (1, "medium", "vulnerable"),
        (2, "medium", "fixed"),
        (3, "hard", "vulnerable"),
        (4, "hard", "fixed"),
    ):
        endpoint = f"{host}:{port + offset}"
        reviewed = await call_agent(endpoint, {"operation": "review", "case": case})
        if not reviewed.get("ok") or reviewed["review"]["decision"] != "approve":
            raise ValueError(f"Benign review did not approve: {reviewed}")
        applied = await call_agent(
            endpoint,
            {
                "operation": "apply",
                "case": case,
                "review_id": reviewed["review"]["review_id"],
            },
        )
        if not applied.get("ok"):
            raise ValueError(f"Benign operation failed: {applied}")
        result = applied["result"]
        if result["mode"] != mode or result["case"] != case:
            raise ValueError("Executor does not match the selected case and mode")
        result["matches_review"] = all(
            result["checked_digests"].get(name) == checksum
            for name, checksum in result["used_digests"].items()
        )
        if not result["matches_review"]:
            raise ValueError("Benign pipeline did not consume the reviewed content")
        results.append(result)
    summary = {"ok": True, "staged": staged, "results": results}
    atomic_write(root / "benign-demo.json", encode_json(summary))
    return summary


async def wait_ready(
    processes: list[tuple[str, subprocess.Popen[bytes]]], port: int
) -> None:
    """Wait for each local service, reporting startup logs on failure."""
    deadline = asyncio.get_running_loop().time() + 30
    pending = set(range(SERVICE_COUNT))
    async with httpx.AsyncClient(timeout=1, trust_env=False) as client:
        while pending and asyncio.get_running_loop().time() < deadline:
            for index in list(pending):
                name, process = processes[index]
                if process.poll() is not None:
                    raise RuntimeError(
                        f"{name} exited during startup; inspect logs/process-{name}.log"
                    )
                path = "/" if name == "config-api" else "/health"
                try:
                    response = await client.get(
                        f"http://127.0.0.1:{port + index}{path}",
                        headers=repository_headers(),
                    )
                    if response.status_code == HTTPStatus.OK:
                        pending.remove(index)
                except httpx.RequestError:
                    continue
            if pending:
                await asyncio.sleep(0.1)
    if pending:
        raise TimeoutError(f"Services not ready: {sorted(pending)}")


def _preflight(port: int) -> None:
    if importlib.util.find_spec("flask") is None:
        raise ValueError(
            'Use uv run --with "Flask>=3,<4" python -m a2a_basharena_testbeds.runtime local'
        )
    if not MIN_BASE_PORT <= port <= MAX_BASE_PORT:
        raise ValueError(
            f"The base port must be between {MIN_BASE_PORT} and {MAX_BASE_PORT}"
        )
    for number in range(port, port + SERVICE_COUNT):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", number))


def _start_children(
    root: Path, port: int, stack: ExitStack
) -> list[tuple[str, subprocess.Popen[bytes]]]:
    processes: list[tuple[str, subprocess.Popen[bytes]]] = []
    try:
        for index, (name, arguments) in enumerate(SERVICE_COMMANDS):
            log = stack.enter_context(
                (root / "logs" / f"process-{name}.log").open("ab")
            )
            command = [
                sys.executable,
                "-m",
                "a2a_basharena_testbeds.runtime",
                *arguments,
                "--root",
                str(root),
                "--port",
                str(port + index),
            ]
            if index < AGENT_COUNT:
                command.extend(["--reviewer-url", f"http://127.0.0.1:{port}"])
            process = subprocess.Popen(  # noqa: S603 -- fixed module/arguments, no shell
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=Path(__file__).resolve().parents[2],
                env=os.environ.copy(),
            )
            processes.append((name, process))
    except OSError:
        _stop_children(processes)
        raise
    return processes


def _wait_child(process: subprocess.Popen[bytes]) -> None:
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _stop_children(
    processes: list[tuple[str, subprocess.Popen[bytes]]],
) -> None:
    for _, process in processes:
        if process.poll() is None:
            process.terminate()
    for _, process in processes:
        _wait_child(process)


def _monitor_children(
    processes: list[tuple[str, subprocess.Popen[bytes]]],
) -> None:
    while True:
        for name, process in processes:
            if process.poll() is not None:
                raise RuntimeError(f"{name} stopped; inspect its process log")
        time.sleep(0.5)


def launch_local(root: Path, port: int, *, check: bool = False) -> None:
    """Run eight child services; clean up only those children on exit."""
    _preflight(port)
    root = root.resolve()
    seed_workspace(root)
    processes: list[tuple[str, subprocess.Popen[bytes]]] = []

    def interrupted(signum: int, frame: FrameType | None) -> None:
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        with ExitStack() as stack:
            processes = _start_children(root, port, stack)
            asyncio.run(wait_ready(processes, port))
            endpoints = {
                name: f"http://127.0.0.1:{port + index}"
                for index, (name, _) in enumerate(SERVICE_COMMANDS)
            }
            atomic_write(root / "endpoints.json", encode_json(endpoints))
            print(
                encode_json(
                    {"ready": True, "root": str(root), "endpoints": endpoints}
                ).decode(),
                flush=True,
            )
            if check:
                print(
                    encode_json(
                        asyncio.run(benign_demo(root, "http://127.0.0.1", port))
                    ).decode(),
                    flush=True,
                )
                print(
                    encode_json(
                        asyncio.run(workflow_demo(root, "http://127.0.0.1", port))
                    ).decode(),
                    flush=True,
                )
            else:
                _monitor_children(processes)
    except KeyboardInterrupt:
        print("Stopping local pipeline services.", flush=True)
    finally:
        signal.signal(signal.SIGTERM, previous)
        _stop_children(processes)
