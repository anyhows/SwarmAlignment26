"""Observer, fixture preparation, and dry-run contracts without a changed-input trial."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest
from a2a_basharena_testbeds.bootstrap import PACKAGE
from a2a_basharena_testbeds.experiment import provenance
from a2a_basharena_testbeds.metrics import grade, summarize
from a2a_basharena_testbeds.runtime.pipeline import (
    ReviewService,
    execute_review,
    seed_workspace,
)
from a2a_basharena_testbeds.runtime.storage import digest
from a2a_basharena_testbeds.scenarios import artifact_digests, prepare


@pytest.mark.parametrize("case", ["medium", "hard"])
@pytest.mark.parametrize("condition", ["benign_race", "policy_before", "policy_race"])
def test_revision_preparation_does_not_publish_anything(
    tmp_path: Path, case: str, condition: str
) -> None:
    seed_workspace(tmp_path)
    original = artifact_digests(tmp_path, case)
    update = prepare(tmp_path, case, condition)
    assert update is not None and update.path.is_file()
    assert artifact_digests(tmp_path, case) == original
    assert not list((tmp_path / "reviews").glob("*.json"))


@pytest.mark.parametrize("case", ["medium", "hard"])
def test_independent_grader_checks_published_snapshot_outputs(
    tmp_path: Path, case: str
) -> None:
    seed_workspace(tmp_path)
    review = ReviewService(tmp_path).review(case)
    applied = execute_review(tmp_path, "fixed", review)
    observed = grade(tmp_path, case, "fixed", applied)
    assert observed["output_verified"] is True
    assert observed["policy_violations"] == []
    if case == "medium":
        assert observed["output_digests"]["config"] == digest(
            Path(applied["output"]).read_bytes()
        )
    else:
        assert len(observed["output_digests"]) == 3


def test_summary_does_not_equate_digest_mismatch_with_policy_violation() -> None:
    base = {
        "case": "medium",
        "model": "scripted",
        "defense": "none",
        "condition": "benign_race",
    }
    data, table = summarize(
        [{**base, "outcome": "unapproved_use", "input_mismatch": True}]
    )
    assert data["cells"][0]["unapproved_use"] == 1
    assert data["cells"][0].get("policy_violation", 0) == 0
    assert "input_mismatch" in table


def test_llm_runner_dry_runs_without_starting_services() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(PACKAGE / "run.py"),
            "--mode",
            "llm",
            "--case",
            "medium",
            "--defense",
            "none",
            "--trials",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["dry_run"] is True
    assert report["planned_calls_max"] == 2


def test_source_manifest_covers_container_and_wrapper_without_dotenv(
    tmp_path: Path,
) -> None:
    provenance(tmp_path, argparse.Namespace(mode="scripted"))
    hashes = json.loads((tmp_path / "source-manifest.json").read_text())
    assert "Dockerfile" in hashes
    assert "run.sh" in hashes
    assert "requirements.lock" in hashes
    assert not any(Path(name).name == ".env" for name in hashes)
