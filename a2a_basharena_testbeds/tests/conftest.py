"""Load the bundled SDK for offline contracts."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from a2a_basharena_testbeds.bootstrap import configure

configure()


@pytest.fixture(autouse=True)
def isolated_budget(monkeypatch):
    monkeypatch.delenv("ADAPTION_LEDGER_DB", raising=False)
