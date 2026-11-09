"""Offline provider contracts; all model responses come from a local HTTP fake."""

import json
from pathlib import Path

import httpx
import pytest
from a2a_basharena_testbeds.runtime.adaption import AdaptionClient
from a2a_basharena_testbeds.runtime.pipeline import ReviewService, seed_workspace
from a2a_basharena_testbeds.runtime.planner import Planner
from a2a_basharena_testbeds.runtime.workflow import snapshot_inputs


@pytest.mark.asyncio
async def test_model_worker_retains_approved_plan_and_criteria(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADAPTION_API_KEY", "offline-test-credential")
    seed_workspace(tmp_path)
    review = ReviewService(tmp_path).review("medium")
    prompts: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/responses"
        assert request.headers["Authorization"] == "Bearer offline-test-credential"
        body = json.loads(request.content)
        prompts.append(body["input"])
        output = (
            {
                "plan": "Restore the approved database configuration.",
                "conditions": ["Preserve TLS."],
            }
            if len(prompts) == 1
            else {
                "action": "execute",
                "explanation": "The selected input matches the approved plan.",
            }
        )
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output_text": json.dumps(output),
                "usage": {"output_tokens": 20},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        planner = Planner(tmp_path, "adaption", "deepseek-v4-flash", True)
        planner.model.http = http
        inputs = snapshot_inputs(review)
        plan = await planner.plan(review, inputs)
        action = await planner.choose(review, plan, inputs)
    assert action.action == "execute"
    assert plan.plan in prompts[1]
    assert "Preserve TLS." in prompts[1]
    assert review.digests["backup.json"] in prompts[1]
    assert "synthetic-demo-password-only" not in "".join(prompts)


@pytest.mark.asyncio
async def test_provider_requires_explicit_enable_before_any_request(
    tmp_path: Path,
) -> None:
    client = AdaptionClient(tmp_path, "deepseek-v4-flash")
    with pytest.raises(ValueError, match="disabled"):
        await client.complete("A request that must never be sent.")
    assert not client.ledger.exists()


@pytest.mark.asyncio
async def test_provider_workspace_budget_survives_client_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADAPTION_API_KEY", "offline-budget-credential")
    monkeypatch.setenv("ADAPTION_LEDGER_MAX_CALLS", "1")
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "completed", "output_text": "OK"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        first = AdaptionClient(tmp_path, "deepseek-v4-flash", enabled=True, http=http)
        assert await first.complete("Reply OK.") == "OK"
        second = AdaptionClient(tmp_path, "deepseek-v4-flash", enabled=True, http=http)
        with pytest.raises(ValueError, match="LEDGER_MAX_CALLS"):
            await second.complete("This request must be blocked before HTTP.")
    assert len(requests) == 1
    assert b"offline-budget-credential" not in first.ledger.read_bytes()
