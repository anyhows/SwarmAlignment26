"""Client for the Adaption hosted-model endpoint, with spending guardrails.

Guardrails (all enforced before any request is sent):
  * Model allowlist: only ADAPTION_ALLOWED_MODELS (default: deepseek-v4-flash, the cheapest).
  * Per-process cap: at most ADAPTION_MAX_CALLS requests per run (default 20).
  * Lifetime cap: every request is appended to artifacts/adaption_ledger.jsonl; once the ledger
    holds ADAPTION_LEDGER_MAX_CALLS requests (default 60), no more are sent until someone raises it.
  * No retries. Any HTTP error or non-"completed" status raises, and the runner aborts the run.
  * max_output_tokens is always set by the caller.
"""
import json
import os
import re
import time
from pathlib import Path

import httpx

BASE = os.environ.get("ADAPTION_API_BASE", "https://api.prod.adaptionlabs.ai")
LEDGER = Path(__file__).resolve().parents[2] / "artifacts" / "adaption_ledger.jsonl"
_calls_this_process = 0


class BudgetError(RuntimeError):
    pass


def _allowed_models() -> set[str]:
    return {m.strip() for m in os.environ.get("ADAPTION_ALLOWED_MODELS", "deepseek-v4-flash").split(",")}


def ledger_count() -> int:
    return sum(1 for _ in LEDGER.open()) if LEDGER.exists() else 0


def check_budget(model: str, planned_calls: int = 1) -> None:
    """Raise BudgetError if `planned_calls` more requests to `model` would break a guardrail."""
    if model not in _allowed_models():
        raise BudgetError(f"model {model!r} not in ADAPTION_ALLOWED_MODELS={sorted(_allowed_models())}")
    per_run = int(os.environ.get("ADAPTION_MAX_CALLS", "20"))
    lifetime = int(os.environ.get("ADAPTION_LEDGER_MAX_CALLS", "60"))
    if _calls_this_process + planned_calls > per_run:
        raise BudgetError(f"{_calls_this_process}+{planned_calls} calls would exceed ADAPTION_MAX_CALLS={per_run}")
    if ledger_count() + planned_calls > lifetime:
        raise BudgetError(f"ledger has {ledger_count()} calls; +{planned_calls} would exceed "
                          f"ADAPTION_LEDGER_MAX_CALLS={lifetime}")


async def complete(model: str, prompt: str, max_tokens: int) -> str:
    global _calls_this_process
    key = os.environ.get("ADAPTION_API_KEY")
    if not key:
        raise RuntimeError("ADAPTION_API_KEY is not set (put it in SwarmAlignment26/.env)")
    check_budget(model)
    _calls_this_process += 1
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": model, "max_output_tokens": max_tokens}
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(
                f"{BASE}/api/v1/responses",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "input": prompt, "max_output_tokens": max_tokens},
            )
        entry["http"] = r.status_code
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        entry.update(status=body.get("status"), usage=body.get("usage"),
                     incomplete=body.get("incomplete_details"), error=body.get("error"))
    except Exception as e:  # noqa: BLE001 - recorded, then re-raised
        entry["exception"] = repr(e)[:300]
        raise
    finally:
        with LEDGER.open("a") as f:  # a request that was sent is always recorded
            f.write(json.dumps(entry) + "\n")
    if r.status_code != 200 or body.get("status") != "completed":
        raise RuntimeError(f"Adaption call failed: http={r.status_code} status={body.get('status')} "
                           f"incomplete={body.get('incomplete_details')} error={body.get('error')}")
    return body.get("output_text", "")


def extract_python(text: str) -> str | None:
    """Return the last ```python fenced block in a model reply, if any."""
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.S)
    return blocks[-1] if blocks else None
