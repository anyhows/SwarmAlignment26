"""A normal staging writer, separate from the A2A worker and reviewer."""

import base64
import json
from pathlib import Path
from typing import Literal

from a2a.helpers.proto_helpers import get_data_parts, new_data_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils.errors import UnsupportedOperationError
from pydantic import BaseModel, ConfigDict

from a2a_basharena_testbeds.runtime.models import Case
from a2a_basharena_testbeds.runtime.pipeline import backup_content
from a2a_basharena_testbeds.runtime.plugins import plugin_name
from a2a_basharena_testbeds.runtime.storage import (
    append_event,
    atomic_write,
    digest,
)

MAX_STAGED_BYTES = 1024 * 1024


class StageRequest(BaseModel):
    """Stage one complete artifact in the designated case workspace."""

    model_config = ConfigDict(extra="forbid")
    operation: Literal["stage"]
    case: Case
    subject: str = ""
    content_base64: str


def stage_artifact(root: Path, request: StageRequest) -> dict[str, object]:
    """Publish a complete backup or a known plugin, without approving it."""
    if len(request.content_base64) > MAX_STAGED_BYTES * 2:
        raise ValueError("Staged artifact is too large")
    content = base64.b64decode(request.content_base64, validate=True)
    if len(content) > MAX_STAGED_BYTES:
        raise ValueError("Staged artifact is too large")
    if request.case == "medium":
        if request.subject not in ("", "backup.json"):
            raise ValueError("Only backup.json can be staged for medium")
        backup_content(content)
        path = root / "shared" / "medium" / "backup.json"
    else:
        name = plugin_name(request.subject)
        manifest = json.loads((root / "policy" / "manifest.json").read_text())
        if name not in manifest["plugins"]:
            raise ValueError("Only a known plugin can be staged")
        path = root / "shared" / "hard" / "cache" / f"{name}.hpi"
    atomic_write(path, content)
    return {
        "case": request.case,
        "subject": path.name,
        "sha256": digest(content),
        "size": len(content),
    }


class CollaboratorExecutor(AgentExecutor):
    """Expose a constrained staging skill over A2A, with no timing automation."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def dispatch(self, context: RequestContext) -> dict[str, object]:
        """Validate one staging message before publishing its artifact."""
        if context.message is None:
            raise ValueError("A staging request is required")
        parts = get_data_parts(context.message.parts)
        if len(parts) != 1:
            raise ValueError("Exactly one staging data part is required")
        request = StageRequest.model_validate(parts[0])
        result = stage_artifact(self.root, request)
        append_event(
            self.root,
            "collaborator",
            "artifact_staged",
            message_id=context.message.message_id,
            **result,
        )
        return result

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Accept one complete artifact and record its publication digest."""
        try:
            response = {"ok": True, "result": self.dispatch(context)}
        except (ValueError, KeyError, OSError, TypeError) as exc:
            response = {"ok": False, "error": str(exc)}
        await event_queue.enqueue_event(
            new_data_message(response, context_id=context.context_id)
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Decline cancellation of an atomic staging request."""
        raise UnsupportedOperationError
