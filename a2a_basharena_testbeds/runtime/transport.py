"""SDK-negotiated requests for direct replies and resumable A2A tasks."""

from typing import Any

import httpx
from a2a.client.client import ClientConfig
from a2a.client.client_factory import ClientFactory
from a2a.helpers.proto_helpers import get_data_parts, new_data_message
from a2a.types import (
    AgentCard,
    Role,
    SendMessageRequest,
    StreamResponse,
    TaskState,
)
from google.protobuf.json_format import ParseDict


async def exchange(
    url: str,
    payload: dict[str, Any],
    client: httpx.AsyncClient | None = None,
    *,
    task_id: str = "",
    context_id: str = "",
) -> StreamResponse:
    """Discover a peer and send a request, optionally resuming its task."""
    if client is None:
        async with httpx.AsyncClient(timeout=300, trust_env=False) as owned:
            return await exchange(
                url, payload, owned, task_id=task_id, context_id=context_id
            )
    base = url.rstrip("/")
    response = await client.get(f"{base}/.well-known/agent-card.json")
    response.raise_for_status()
    card = ParseDict(response.json(), AgentCard())
    for interface in card.supported_interfaces:
        if interface.protocol_binding == "HTTP+JSON":
            interface.url = base
    peer = ClientFactory(
        ClientConfig(
            httpx_client=client,
            streaming=False,
            supported_protocol_bindings=["HTTP+JSON"],
        )
    ).create(card)
    message = new_data_message(
        payload,
        role=Role.ROLE_USER,
        task_id=task_id or None,
        context_id=context_id or None,
    )
    final: StreamResponse | None = None
    async for reply in peer.send_message(SendMessageRequest(message=message)):
        final = reply
    if final is None:
        raise ValueError("The agent returned no response")
    return final


async def call_agent(
    url: str, payload: dict[str, Any], client: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """Return one direct application data reply."""
    reply = await exchange(url, payload, client)
    if reply.HasField("message"):
        parts = get_data_parts(reply.message.parts)
        if len(parts) == 1 and isinstance(parts[0], dict):
            return parts[0]
    raise ValueError("The agent returned no application data response")


async def call_task(
    url: str,
    payload: dict[str, Any],
    *,
    task_id: str = "",
    context_id: str = "",
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Return the task identity, current state, and status data."""
    reply = await exchange(url, payload, client, task_id=task_id, context_id=context_id)
    if not reply.HasField("task"):
        raise ValueError("The agent returned no task")
    task = reply.task
    parts = get_data_parts(task.status.message.parts)
    return {
        "task_id": task.id,
        "context_id": task.context_id,
        "state": TaskState.Name(task.status.state),
        "data": parts[0] if len(parts) == 1 else {},
    }
