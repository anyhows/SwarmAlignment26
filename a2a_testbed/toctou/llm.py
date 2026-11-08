"""Minimal client for the Adaption hosted-model endpoint (see ../../adaption-llm-endpoints.md)."""
import os
import re

import httpx

BASE = os.environ.get("ADAPTION_API_BASE", "https://api.prod.adaptionlabs.ai")


async def complete(model: str, prompt: str, max_tokens: int = 2048) -> str:
    key = os.environ.get("ADAPTION_API_KEY")
    if not key:
        raise RuntimeError("ADAPTION_API_KEY is not set (put it in SwarmAlignment26/.env)")
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(
            f"{BASE}/api/v1/responses",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "input": prompt, "max_output_tokens": max_tokens},
        )
        r.raise_for_status()
        return r.json()["output_text"]


def extract_python(text: str) -> str | None:
    """Return the last ```python fenced block in a model reply, if any."""
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.S)
    return blocks[-1] if blocks else None
