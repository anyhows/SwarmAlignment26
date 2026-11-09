"""SDK-backed reviewer and executor HTTP services."""

import uuid
from typing import Any, Literal

import httpx
from a2a.helpers.proto_helpers import get_data_parts, new_data_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_rest_routes
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
)
from a2a.utils.errors import UnsupportedOperationError
from pydantic import BaseModel, ConfigDict
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from a2a_basharena_testbeds.runtime.collaborator import CollaboratorExecutor
from a2a_basharena_testbeds.runtime.models import Case, ReviewRecord
from a2a_basharena_testbeds.runtime.pipeline import (
    ReviewService,
    append_event,
    execute_review,
)
from a2a_basharena_testbeds.runtime.settings import AgentSettings
from a2a_basharena_testbeds.runtime.transport import call_agent
from a2a_basharena_testbeds.runtime.workflow import WorkflowExecutor


class Operation(BaseModel):
    """The local pipeline's application-level request schema."""

    model_config = ConfigDict(extra="forbid")

    operation: Literal["review", "receipt", "apply"]
    case: Case = "medium"
    subject: str = ""
    review_id: str = ""


def parse_operation(context: RequestContext) -> tuple[Operation, str]:
    """Parse exactly one structured application data part."""
    if context.message is None:
        raise ValueError("An application request message is required")
    parts = get_data_parts(context.message.parts)
    if len(parts) != 1:
        raise ValueError("Exactly one JSON data part is required")
    return Operation.model_validate(parts[0]), context.message.message_id


class PipelineAgent(AgentExecutor):
    """An A2A executor that implements reviewer or execution operations."""

    def __init__(
        self, settings: AgentSettings, peer_http: httpx.AsyncClient | None
    ) -> None:
        self.settings = settings
        self.peer_http = peer_http
        self.reviewer = ReviewService(settings.root)
        self.workflow = WorkflowExecutor(settings, peer_http)

    async def dispatch(self, operation: Operation) -> dict[str, Any]:
        """Run a typed application operation, consulting the peer over A2A."""
        settings = self.settings
        if settings.role == "reviewer":
            if operation.operation == "review":
                review = self.reviewer.review(operation.case, operation.subject)
                return {"ok": True, "review": review.public()}
            if operation.operation == "receipt":
                return {
                    "ok": True,
                    "review": self.reviewer.get(operation.review_id).model_dump(),
                }
            raise ValueError("The reviewer does not apply operations")
        if operation.case != settings.case:
            raise ValueError("Request case does not match this executor")
        if operation.operation == "review":
            return await call_agent(
                settings.reviewer_url, operation.model_dump(), self.peer_http
            )
        if operation.operation != "apply":
            raise ValueError("Executors accept review or apply operations")
        receipt = await call_agent(
            settings.reviewer_url,
            {"operation": "receipt", "review_id": operation.review_id},
            self.peer_http,
        )
        if not receipt.get("ok"):
            raise ValueError(f"Reviewer lookup failed: {receipt.get('error')}")
        review = ReviewRecord.model_validate(receipt["review"])
        if review.case != settings.case:
            raise ValueError("Review case does not match this executor")
        result = execute_review(settings.root, settings.mode, review)
        return {"ok": True, "result": result}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Receive a real A2A data message and return a structured response."""
        if self.settings.role == "executor" and self.workflow.accepts(context):
            await self.workflow.execute(context, event_queue)
            return
        component = self.settings.role
        if component == "executor":
            component = f"{self.settings.case}-{self.settings.mode}"
        try:
            operation, message_id = parse_operation(context)
            append_event(
                self.settings.root,
                component,
                "a2a_request",
                message_id=message_id,
                operation=operation.operation,
                case=operation.case,
            )
            response = await self.dispatch(operation)
        except (
            ValueError,
            KeyError,
            OSError,
            TypeError,
            httpx.HTTPError,
        ) as exc:
            response = {"ok": False, "error": str(exc)}
        await event_queue.enqueue_event(
            new_data_message(
                response, context_id=context.context_id or str(uuid.uuid4())
            )
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Decline cancellation of these short request/response operations."""
        raise UnsupportedOperationError


def create_app(
    settings: AgentSettings, peer_http: httpx.AsyncClient | None = None
) -> Starlette:
    """Create the reviewer or executor A2A application."""
    card = AgentCard(
        name=f"BashArena {settings.role} ({settings.case}/{settings.mode})",
        description="Local deterministic artifact-review pipeline",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        supported_interfaces=[
            AgentInterface(
                protocol_binding="HTTP+JSON",
                protocol_version="1.0",
                url=settings.url,
            )
        ],
        skills=[
            AgentSkill(
                id=settings.role,
                name=settings.role,
                description="Review artifacts or apply a reviewer-issued decision",
                tags=["basharena", "pipeline"],
            )
        ],
    )
    handler = DefaultRequestHandler(
        agent_executor=CollaboratorExecutor(settings.root)
        if settings.role == "collaborator"
        else PipelineAgent(settings, peer_http),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )

    async def health(request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "ready": True,
                "role": settings.role,
                "case": settings.case,
                "mode": settings.mode,
                "engine": settings.engine,
                "model_calls_enabled": settings.allow_model_calls,
            }
        )

    return Starlette(
        routes=[
            Route("/health", health),
            *create_agent_card_routes(card),
            *create_rest_routes(handler),
        ]
    )
