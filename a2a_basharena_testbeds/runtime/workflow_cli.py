"""Manual task handoffs and unchanged-input workflow verification."""

import argparse
import asyncio
import base64
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from a2a_basharena_testbeds.runtime.models import Case
from a2a_basharena_testbeds.runtime.storage import atomic_write, encode_json
from a2a_basharena_testbeds.runtime.transport import call_agent, call_task


class Ticket(BaseModel):
    """A local pointer to one pending A2A task, with no approval authority itself."""

    model_config = ConfigDict(extra="forbid")
    executor_url: str
    case: Case
    task_id: str
    context_id: str
    review_id: str


async def start(root: Path, url: str, case: Case, subject: str = "") -> dict[str, Any]:
    """Start a task and save its identity for a later manual reply."""
    reply = await call_task(
        url, {"operation": "plan", "case": case, "subject": subject}
    )
    if reply["state"] == "TASK_STATE_INPUT_REQUIRED":
        ticket = Ticket(
            executor_url=url,
            case=case,
            task_id=reply["task_id"],
            context_id=reply["context_id"],
            review_id=reply["data"]["review_id"],
        )
        path = root / "tickets" / f"{ticket.task_id}.json"
        atomic_write(path, encode_json(ticket.model_dump()))
        reply["ticket"] = str(path.resolve())
    reply["ok"] = reply["state"] == "TASK_STATE_INPUT_REQUIRED"
    return reply


async def resume(path: Path, decision: str) -> dict[str, Any]:
    """Reply to the same task with the plan's original review identity."""
    ticket = Ticket.model_validate_json(await asyncio.to_thread(path.read_text))
    reply = await call_task(
        ticket.executor_url,
        {
            "operation": decision,
            "case": ticket.case,
            "review_id": ticket.review_id,
        },
        task_id=ticket.task_id,
        context_id=ticket.context_id,
    )
    reply["ok"] = reply["state"] == (
        "TASK_STATE_REJECTED" if decision == "reject" else "TASK_STATE_COMPLETED"
    )
    atomic_write(path.with_suffix(".result.json"), encode_json(reply))
    return reply


async def collaborate(url: str, case: Case, subject: str, path: Path) -> dict[str, Any]:
    """Stage a user-selected local artifact through the collaborator's A2A skill."""
    content = await asyncio.to_thread(path.read_bytes)
    return await call_agent(
        url,
        {
            "operation": "stage",
            "case": case,
            "subject": subject,
            "content_base64": base64.b64encode(content).decode(),
        },
    )


async def request(args: argparse.Namespace) -> dict[str, Any]:
    """Dispatch this command family without expanding the direct-operation CLI."""
    if args.command == "workflow-start":
        return await start(
            args.root.resolve(), args.executor_url, args.case, args.subject
        )
    if args.command == "workflow-resume":
        return await resume(args.ticket, args.decision)
    if args.command == "workflow-demo":
        return await workflow_demo(
            args.root.resolve(), "http://127.0.0.1", args.base_port
        )
    return await collaborate(args.collaborator_url, args.case, args.subject, args.file)


async def workflow_demo(root: Path, host: str, port: int) -> dict[str, Any]:
    """Verify all four pause/resume paths with no edits during approval."""
    results = []
    variants: tuple[tuple[int, Case], ...] = (
        (1, "medium"),
        (2, "medium"),
        (3, "hard"),
        (4, "hard"),
    )
    async with httpx.AsyncClient(timeout=5, trust_env=False) as http:
        # Probe the collaborator without publishing any input during a pending task.
        response = await http.get(f"{host}:{port + 7}/health")
        response.raise_for_status()
        for offset, case in variants:
            url = f"{host}:{port + offset}"
            health = await http.get(f"{url}/health")
            health.raise_for_status()
            if health.json()["engine"] != "scripted":
                raise ValueError(
                    "workflow-demo requires scripted workers; use manual start/resume for paid model calls"
                )
            planned = await start(root, url, case)
            if not planned.get("ok"):
                raise ValueError(f"Workflow did not pause for review: {planned}")
            applied = await resume(Path(planned["ticket"]), "approve")
            if not applied.get("ok") or not applied["data"]["result"]["matches_review"]:
                raise ValueError(
                    f"Unchanged workflow did not apply reviewed inputs: {applied}"
                )
            results.append(
                {
                    "case": case,
                    "task_id": planned["task_id"],
                    "paused_state": planned["state"],
                    "final_state": applied["state"],
                    **applied["data"]["result"],
                }
            )
    summary = {
        "ok": True,
        "inputs_changed_during_approval": False,
        "results": results,
    }
    atomic_write(root / "workflow-demo.json", encode_json(summary))
    return summary
