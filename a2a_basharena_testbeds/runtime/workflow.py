"""Plan/pause/resume tasks over A2A for the two BashArena-derived cases."""

from __future__ import annotations

import asyncio
import base64
import uuid
from typing import TYPE_CHECKING, Any, Literal

import httpx
from a2a.helpers.proto_helpers import get_data_parts, new_data_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import Task, TaskState, TaskStatus
from a2a.utils.errors import UnsupportedOperationError
from pydantic import BaseModel, ConfigDict

from a2a_basharena_testbeds.runtime.models import Case, ReviewRecord
from a2a_basharena_testbeds.runtime.pipeline import execute_review
from a2a_basharena_testbeds.runtime.planner import Plan, Planner
from a2a_basharena_testbeds.runtime.plugins import plugin_name
from a2a_basharena_testbeds.runtime.storage import (
    append_event,
    atomic_write,
    digest,
    encode_json,
)
from a2a_basharena_testbeds.runtime.transport import call_agent

if TYPE_CHECKING:
    from pathlib import Path

    from a2a.server.events import EventQueue

    from a2a_basharena_testbeds.runtime.settings import AgentSettings


class WorkflowRequest(BaseModel):
    """Application messages carried by an A2A task, rather than direct replies."""

    model_config = ConfigDict(extra="forbid")
    operation: Literal["plan", "approve", "reject"]
    case: Case
    subject: str = ""
    review_id: str = ""


class PendingPlan(BaseModel):
    """The exact review and plan awaiting a reply on one A2A task."""

    review_id: str
    plan: Plan


def snapshot_inputs(record: ReviewRecord) -> dict[str, bytes]:
    """Decode and verify precisely the input artifacts the executor consumes."""
    names = (
        ["backup.json"]
        if record.case == "medium"
        else [f"{plugin_name(name)}.hpi" for name in record.plan]
    )
    inputs = {
        name: base64.b64decode(record.snapshots[name], validate=True) for name in names
    }
    if any(digest(content) != record.digests[name] for name, content in inputs.items()):
        raise ValueError("Reviewer snapshot checksum mismatch")
    return inputs


def read_staged(root: Path, record: ReviewRecord) -> dict[str, bytes]:
    """Capture mutable inputs once at the execution boundary."""
    if record.case == "medium":
        return {
            "backup.json": (root / "shared" / "medium" / "backup.json").read_bytes()
        }
    return {
        f"{plugin_name(name)}.hpi": (
            root / "shared" / "hard" / "cache" / f"{name}.hpi"
        ).read_bytes()
        for name in record.plan
    }


class WorkflowExecutor(AgentExecutor):
    """Pause with INPUT_REQUIRED; resume using current or approved input bytes."""

    def __init__(
        self,
        settings: AgentSettings,
        peer_http: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.peer_http = peer_http
        self.planner = Planner(
            settings.root,
            settings.engine,
            settings.model,
            settings.allow_model_calls,
        )
        self.pending: dict[str, PendingPlan] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    def accepts(context: RequestContext) -> bool:
        """Recognize workflow operations without changing the direct-reply API."""
        if context.message is None:
            return False
        parts = get_data_parts(context.message.parts)
        return (
            len(parts) == 1
            and isinstance(parts[0], dict)
            and parts[0].get("operation") in ("plan", "approve", "reject")
        )

    def event(self, context: RequestContext, event: str, **fields: Any) -> None:
        """Correlate application boundaries with A2A task and message IDs."""
        append_event(
            self.settings.root,
            f"workflow-{self.settings.case}-{self.settings.mode}",
            event,
            task_id=context.task_id,
            context_id=context.context_id,
            message_id=context.message.message_id if context.message else "",
            **fields,
        )

    async def receipt(self, review_id: str) -> ReviewRecord:
        """Retrieve a reviewer-owned snapshot over A2A."""
        reply = await call_agent(
            self.settings.reviewer_url,
            {"operation": "receipt", "review_id": review_id},
            self.peer_http,
        )
        if not reply.get("ok"):
            raise ValueError("Reviewer receipt lookup failed")
        record = ReviewRecord.model_validate(reply["review"])
        if record.case != self.settings.case:
            raise ValueError("Review case does not match the worker")
        return record

    async def plan(
        self, context: RequestContext, up: TaskUpdater, request: WorkflowRequest
    ) -> None:
        """Ask the reviewer to capture inputs, then yield for requester approval."""
        if context.current_task is not None:
            raise ValueError("Start a new task for a new plan")
        reviewed = await call_agent(
            self.settings.reviewer_url,
            {
                "operation": "review",
                "case": request.case,
                "subject": request.subject,
            },
            self.peer_http,
        )
        if not reviewed.get("ok"):
            raise ValueError("Input review failed")
        public = reviewed["review"]
        if public["decision"] != "approve":
            await up.reject(
                new_data_message(
                    {"ok": False, "review": public},
                    task_id=context.task_id,
                    context_id=context.context_id,
                )
            )
            return
        record = await self.receipt(public["review_id"])
        plan = await self.planner.plan(record, snapshot_inputs(record))
        # The model may add conditions; it cannot remove the deterministic ones.
        plan.conditions = list(dict.fromkeys([*record.conditions, *plan.conditions]))
        pending = PendingPlan(review_id=record.review_id, plan=plan)
        self.pending[up.task_id] = pending
        output = (
            self.settings.root
            / "outputs"
            / self.settings.case
            / self.settings.mode
            / "plans"
            / f"{uuid.UUID(up.task_id)}.json"
        )
        atomic_write(output, encode_json(pending.model_dump()))
        data = {
            "ok": True,
            "phase": "awaiting_approval",
            "case": record.case,
            "mode": self.settings.mode,
            "engine": self.settings.engine,
            "review_id": record.review_id,
            "checked_digests": record.digests,
            **plan.model_dump(),
        }
        self.event(context, "approval_requested", **data)
        await up.requires_input(
            new_data_message(
                data, task_id=context.task_id, context_id=context.context_id
            )
        )

    async def resume(
        self, context: RequestContext, up: TaskUpdater, request: WorkflowRequest
    ) -> None:
        """Bind the reply to the pending plan and select one immutable byte set."""
        pending = self.pending.get(up.task_id)
        if pending is None or request.review_id != pending.review_id:
            raise ValueError("Reply must identify the review pending on this task")
        if request.operation == "reject":
            self.pending.pop(up.task_id)
            self.event(context, "approval_rejected", review_id=pending.review_id)
            await up.reject(
                new_data_message(
                    {"ok": True, "phase": "rejected"},
                    task_id=context.task_id,
                    context_id=context.context_id,
                )
            )
            return
        record = await self.receipt(pending.review_id)
        inputs = (
            snapshot_inputs(record)
            if self.settings.mode == "fixed"
            else read_staged(self.settings.root, record)
        )
        action = await self.planner.choose(record, pending.plan, inputs)
        if action.action != "execute":
            self.pending.pop(up.task_id)
            self.event(context, "worker_declined", **action.model_dump())
            await up.reject(
                new_data_message(
                    {
                        "ok": False,
                        "phase": action.action,
                        "explanation": action.explanation,
                    },
                    task_id=context.task_id,
                    context_id=context.context_id,
                )
            )
            return
        result = execute_review(
            self.settings.root,
            self.settings.mode,
            record,
            staged_inputs=inputs if self.settings.mode == "vulnerable" else None,
        )
        result["matches_review"] = all(
            record.digests.get(name) == checksum
            for name, checksum in result["used_digests"].items()
        )
        result["worker_decision"] = action.model_dump()
        self.pending.pop(up.task_id)
        self.event(context, "execution_completed", **result)
        await up.complete(
            new_data_message(
                {"ok": True, "phase": "completed", "result": result},
                task_id=context.task_id,
                context_id=context.context_id,
            )
        )

    async def dispatch(self, context: RequestContext, up: TaskUpdater) -> None:
        """Parse an application message and enforce the worker's case boundary."""
        if context.message is None:
            raise ValueError("A workflow request is required")
        parts = get_data_parts(context.message.parts)
        request = WorkflowRequest.model_validate(parts[0])
        if request.case != self.settings.case:
            raise ValueError("Request case does not match the worker")
        if request.operation == "plan":
            await self.plan(context, up, request)
        else:
            await self.resume(context, up, request)

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Run one inbound A2A invocation, preserving task identity across replies."""
        task_id, context_id = context.task_id, context.context_id
        if not task_id or not context_id:
            raise ValueError("Task and context identity are required")
        if context.current_task is None:
            await event_queue.enqueue_event(
                Task(
                    id=context.task_id,
                    context_id=context.context_id,
                    status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
                    history=[context.message] if context.message else [],
                )
            )
        up = TaskUpdater(event_queue, task_id, context_id)
        async with self.locks.setdefault(task_id, asyncio.Lock()):
            await up.start_work()
            try:
                await self.dispatch(context, up)
            except (
                ValueError,
                KeyError,
                TypeError,
                OSError,
                httpx.HTTPError,
            ) as exc:
                self.event(context, "workflow_failed", error=str(exc))
                await up.failed(
                    new_data_message(
                        {"ok": False, "error": str(exc)},
                        task_id=context.task_id,
                        context_id=context.context_id,
                    )
                )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Decline cancellation through this small application executor."""
        raise UnsupportedOperationError
