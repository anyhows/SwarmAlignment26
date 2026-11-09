"""Optional Adaption model access with a shared, persistent request budget."""

import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

import httpx

from a2a_basharena_testbeds.runtime.storage import now


class AdaptionClient:
    """Use the collaborator's hosted endpoint; never load or log raw credentials."""

    def __init__(
        self,
        root: Path,
        model: str,
        *,
        enabled: bool = False,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.ledger = Path(
            os.environ.get(
                "ADAPTION_LEDGER_DB", str(root / "logs" / "adaption-budget.sqlite3")
            )
        )
        self.model = model
        self.enabled = enabled
        self.http = http
        self.calls = 0

    def reserve(self) -> str:
        """Atomically count a request across workers before sending it."""
        allowed = os.environ.get("ADAPTION_ALLOWED_MODELS", "deepseek-v4-flash").split(
            ","
        )
        if self.model not in {item.strip() for item in allowed}:
            raise ValueError("Model is outside ADAPTION_ALLOWED_MODELS")
        if not self.enabled:
            raise ValueError(
                "Model calls are disabled; enable them explicitly on the worker"
            )
        if not os.environ.get("ADAPTION_API_KEY"):
            raise ValueError("ADAPTION_API_KEY is required for the Adaption worker")
        per_worker = int(os.environ.get("ADAPTION_MAX_CALLS", "20"))
        if self.calls >= per_worker:
            raise ValueError("ADAPTION_MAX_CALLS reached for this worker process")
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        request_id = str(uuid.uuid4())
        with sqlite3.connect(self.ledger, timeout=10) as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, at TEXT, model TEXT, status TEXT, usage TEXT)"
            )
            database.execute("BEGIN IMMEDIATE")
            count = database.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
            if count >= int(os.environ.get("ADAPTION_LEDGER_MAX_CALLS", "60")):
                raise ValueError("ADAPTION_LEDGER_MAX_CALLS reached for this workspace")
            database.execute(
                "INSERT INTO calls VALUES (?, ?, ?, ?, ?)",
                (request_id, now(), self.model, "reserved", "{}"),
            )
        self.calls += 1
        return request_id

    def record(self, request_id: str, status: str, usage: Any = None) -> None:
        """Record only status and provider usage; omit prompts and key material."""
        with sqlite3.connect(self.ledger, timeout=10) as database:
            database.execute(
                "UPDATE calls SET status = ?, usage = ? WHERE id = ?",
                (status, json.dumps(usage or {}), request_id),
            )

    async def complete(self, prompt: str) -> str:
        """Make one bounded request without retries or fallback models."""
        request_id = self.reserve()
        if self.http is None:
            async with httpx.AsyncClient(timeout=240, trust_env=False) as client:
                return await self.send(client, request_id, prompt)
        return await self.send(self.http, request_id, prompt)

    async def send(
        self, client: httpx.AsyncClient, request_id: str, prompt: str
    ) -> str:
        """Send a reserved request, retaining its budget charge on failure."""
        base = os.environ.get(
            "ADAPTION_API_BASE", "https://api.prod.adaptionlabs.ai"
        ).rstrip("/")
        try:
            response = await client.post(
                f"{base}/api/v1/responses",
                headers={"Authorization": f"Bearer {os.environ['ADAPTION_API_KEY']}"},
                json={
                    "model": self.model,
                    "input": prompt,
                    # deepseek-v4-flash reasoning alone can exhaust 2,000 tokens on the resume
                    # decision (status "incomplete"); a2a_testbed uses 6,000.
                    "max_output_tokens": int(
                        os.environ.get("ADAPTION_MAX_OUTPUT_TOKENS", "2000")
                    ),
                },
            )
            response.raise_for_status()
            body = response.json()
            self.record(
                request_id,
                str(body.get("status", "missing")),
                body.get("usage"),
            )
        except (httpx.HTTPError, ValueError, KeyError):
            self.record(request_id, "error")
            raise
        if (
            body.get("status") != "completed"
            or not isinstance(body.get("output_text"), str)
            or not body["output_text"].strip()
        ):
            raise ValueError("Adaption did not return a complete nonempty response")
        return body["output_text"]
