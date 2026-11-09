"""Client for the Adaption hosted-model endpoint, with spending guardrails.

Guardrails (all enforced before any request is sent):
  * Model allowlist: only ADAPTION_ALLOWED_MODELS (default: the five cheap hosted models;
    glm-5.2 and qwen3.5-397b are excluded because they cost 10-30x more).
  * Per-process cap: at most ADAPTION_MAX_CALLS requests per run (default 250).
  * Lifetime cap: every request is appended to artifacts/adaption_ledger.jsonl; once the ledger
    holds ADAPTION_LEDGER_MAX_CALLS requests (default 1500), no more are sent until someone raises it.
  * No retries, except HTTP 429 (rate limited: refused before inference, so never billed),
    which waits ~60-90 s and retries up to RATE_LIMIT_RETRIES times, and HTTP 500/502/503/504
    (transient), retried at most SERVER_ERROR_RETRIES times. Any other HTTP error or
    non-"completed" status raises, and the runner aborts the run.
  * max_output_tokens is always set by the caller.
"""
import asyncio
import json
import os
import random
import re
import time
from pathlib import Path

import httpx

BASE = os.environ.get("ADAPTION_API_BASE", "https://api.prod.adaptionlabs.ai")
LEDGER = Path(__file__).resolve().parents[2] / "artifacts" / "adaption_ledger.jsonl"
_calls_this_process = 0
RATE_LIMIT_RETRIES = 6
SERVER_ERROR_RETRIES = 2
# Full prompt/response transcripts. The runner sets TRANSCRIPT to <run_dir>/transcripts.jsonl and
# CURRENT_TRIAL before each trial. Trials run sequentially in one process, and the in-process
# agents call complete() during that trial, so each call is tagged with its trial.
TRANSCRIPT: Path | None = None
CURRENT_TRIAL: dict = {}
CHEAP_MODELS = "deepseek-v4-flash,qwen3.8-27b,gemma-4-31b-it,gemma-4-26b-a4b-it,glm-53-flash"


class BudgetError(RuntimeError):
    pass


def _allowed_models() -> set[str]:
    return {m.strip() for m in os.environ.get("ADAPTION_ALLOWED_MODELS", CHEAP_MODELS).split(",")}


def ledger_count() -> int:
    return sum(1 for _ in LEDGER.open()) if LEDGER.exists() else 0


def check_budget(model: str, planned_calls: int = 1) -> None:
    """Raise BudgetError if `planned_calls` more requests to `model` would break a guardrail."""
    if model not in _allowed_models():
        raise BudgetError(f"model {model!r} not in ADAPTION_ALLOWED_MODELS={sorted(_allowed_models())}")
    per_run = int(os.environ.get("ADAPTION_MAX_CALLS", "250"))
    lifetime = int(os.environ.get("ADAPTION_LEDGER_MAX_CALLS", "1500"))
    if _calls_this_process + planned_calls > per_run:
        raise BudgetError(f"{_calls_this_process}+{planned_calls} calls would exceed ADAPTION_MAX_CALLS={per_run}")
    if ledger_count() + planned_calls > lifetime:
        raise BudgetError(f"ledger has {ledger_count()} calls; +{planned_calls} would exceed "
                          f"ADAPTION_LEDGER_MAX_CALLS={lifetime}")


async def complete(model: str, prompt: str, max_tokens: int) -> str:
    key = os.environ.get("ADAPTION_API_KEY")
    if not key:
        raise RuntimeError("ADAPTION_API_KEY is not set (put it in SwarmAlignment26/.env)")
    rate_limited = server_errors = 0
    while True:
        r, body = await _send_once(key, model, prompt, max_tokens)
        if r.status_code == 429 and rate_limited < RATE_LIMIT_RETRIES:
            # Rate limited: refused before inference (no usage, no cost). Wait as instructed
            # (60 s), with jitter so parallel runner processes don't retry in lockstep.
            rate_limited += 1
            await asyncio.sleep(60 + random.uniform(0, 30))
        elif r.status_code in (500, 502, 503, 504) and server_errors < SERVER_ERROR_RETRIES:
            # Transient gateway/server error. Retried at most twice; the upstream call may
            # occasionally have been billed anyway (accepted: costs are tiny, and a single
            # hiccup must not abort a 40-trial run).
            server_errors += 1
            await asyncio.sleep(10 + random.uniform(0, 10))
        else:
            break
    if TRANSCRIPT is not None:
        with TRANSCRIPT.open("a") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **CURRENT_TRIAL,
                                "model": model, "max_output_tokens": max_tokens, "prompt": prompt,
                                "http": r.status_code, "status": body.get("status"),
                                "output_text": body.get("output_text"), "usage": body.get("usage"),
                                "error": body.get("error")}) + "\n")
    if r.status_code != 200 or body.get("status") != "completed":
        raise RuntimeError(f"Adaption call failed: http={r.status_code} status={body.get('status')} "
                           f"incomplete={body.get('incomplete_details')} error={body.get('error')}")
    return body.get("output_text", "")


async def _send_once(key: str, model: str, prompt: str, max_tokens: int):
    global _calls_this_process
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
    return r, body


def extract_python(text: str) -> str | None:
    """Return the last ```python fenced block in a model reply, if any."""
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.S)
    return blocks[-1] if blocks else None
