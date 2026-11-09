"""Local and container entry points for the two review pipelines."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx
import uvicorn

from a2a_basharena_testbeds.runtime import workflow_cli
from a2a_basharena_testbeds.runtime.agents import (
    AgentSettings,
    call_agent,
    create_app,
)
from a2a_basharena_testbeds.runtime.launch import benign_demo, launch_local
from a2a_basharena_testbeds.runtime.pipeline import seed_workspace
from a2a_basharena_testbeds.runtime.repository import (
    create_repository,
    stage_from_repository,
)


def parser() -> argparse.ArgumentParser:
    """Build the documented environment CLI."""
    result = argparse.ArgumentParser(description="BashArena A2A review pipelines")
    commands = result.add_subparsers(dest="command", required=True)
    for command in (
        "seed",
        "local",
        "serve",
        "repository",
        "stage",
        "demo",
        "review",
        "apply",
        "run",
        "workflow-start",
        "workflow-resume",
        "workflow-demo",
        "collaborate",
    ):
        sub = commands.add_parser(command)
        sub.add_argument(
            "--root",
            type=Path,
            default=Path(__file__).resolve().parents[2]
            / "artifacts"
            / "a2a_basharena_testbeds"
            / "manual-state",
        )
        sub.add_argument("--case", choices=["medium", "hard"], default="medium")
        sub.add_argument("--subject", default="")
        if command in ("local", "demo", "workflow-demo"):
            sub.add_argument("--base-port", type=int, default=8200)
        if command == "local":
            sub.add_argument(
                "--check",
                action="store_true",
                help="Run an unchanged benign cycle and stop",
            )
        if command in ("serve", "repository"):
            sub.add_argument("--port", type=int, default=8200)
            sub.add_argument("--host", default="127.0.0.1")
        if command == "serve":
            sub.add_argument(
                "--role",
                choices=["reviewer", "executor", "collaborator"],
                required=True,
            )
            sub.add_argument("--mode", choices=["vulnerable", "fixed"], default="fixed")
            sub.add_argument("--reviewer-url", default="http://127.0.0.1:8200")
            sub.add_argument(
                "--engine",
                choices=["scripted", "adaption"],
                default=os.environ.get("BASHARENA_ENGINE", "scripted"),
            )
            sub.add_argument(
                "--model",
                default=os.environ.get("BASHARENA_MODEL", "deepseek-v4-flash"),
            )
            sub.add_argument(
                "--allow-model-calls",
                action="store_true",
                default=os.environ.get("ADAPTION_ENABLE_CALLS") == "1",
            )
        if command == "stage":
            sub.add_argument("--repository-url", required=True)
        if command in ("review", "apply", "run", "workflow-start"):
            sub.add_argument("--executor-url", required=True)
        if command == "apply":
            sub.add_argument("--review-id", required=True)
        if command == "workflow-resume":
            sub.add_argument("--ticket", type=Path, required=True)
            sub.add_argument(
                "--decision", choices=["approve", "reject"], default="approve"
            )
        if command == "collaborate":
            sub.add_argument("--file", type=Path, required=True)
            sub.add_argument("--collaborator-url", default="http://127.0.0.1:8207")
    return result


async def request_operation(args: argparse.Namespace) -> dict[str, Any]:
    """Review and/or apply through an executor's A2A endpoint."""
    if args.command.startswith("workflow-") or args.command == "collaborate":
        return await workflow_cli.request(args)
    if args.command == "apply":
        return await call_agent(
            args.executor_url,
            {
                "operation": "apply",
                "case": args.case,
                "review_id": args.review_id,
            },
        )
    reviewed = await call_agent(
        args.executor_url,
        {
            "operation": "review",
            "case": args.case,
            "subject": args.subject,
        },
    )
    if args.command == "review" or not reviewed.get("ok"):
        return reviewed
    if reviewed["review"]["decision"] != "approve":
        return {"ok": False, "review": reviewed["review"]}
    return await call_agent(
        args.executor_url,
        {
            "operation": "apply",
            "case": args.case,
            "review_id": reviewed["review"]["review_id"],
        },
    )


def main() -> None:
    """Run the selected command, reporting application failures with exit 1."""
    args = parser().parse_args()
    root = args.root.resolve()
    try:
        if args.command == "seed":
            seed_workspace(root)
            result = {"ok": True, "root": str(root)}
        elif args.command == "local":
            launch_local(root, args.base_port, check=args.check)
            return
        elif args.command == "serve":
            settings = AgentSettings(
                root,
                args.role,
                args.case,
                args.mode,
                args.reviewer_url,
                f"http://127.0.0.1:{args.port}",
                engine=args.engine,
                model=args.model,
                allow_model_calls=args.allow_model_calls,
            )
            uvicorn.run(create_app(settings), host=args.host, port=args.port)
            return
        elif args.command == "repository":
            create_repository(root, args.case).run(
                host=args.host, port=args.port, debug=False, use_reloader=False
            )
            return
        elif args.command == "stage":
            result = asyncio.run(
                stage_from_repository(
                    root,
                    args.case,
                    args.repository_url,
                    args.subject or "docker-plugin",
                )
            )
        elif args.command == "demo":
            result = asyncio.run(benign_demo(root, "http://127.0.0.1", args.base_port))
        else:
            result = asyncio.run(request_operation(args))
    except (
        ValueError,
        OSError,
        RuntimeError,
        KeyError,
        TypeError,
        httpx.HTTPError,
    ) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise SystemExit(1) from exc
    print(json.dumps(result, indent=2))
    if result.get("ok") is False:
        raise SystemExit(1)
