"""Shared service settings with a single import identity."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from a2a_basharena_testbeds.runtime.models import Case, Mode


@dataclass(frozen=True)
class AgentSettings:
    """Connection and workspace settings for one process."""

    root: Path
    role: Literal["reviewer", "executor", "collaborator"]
    case: Case = "medium"
    mode: Mode = "fixed"
    reviewer_url: str = "http://127.0.0.1:8200"
    url: str = "http://127.0.0.1:8201"
    engine: Literal["scripted", "adaption"] = "scripted"
    model: str = "deepseek-v4-flash"
    allow_model_calls: bool = False
