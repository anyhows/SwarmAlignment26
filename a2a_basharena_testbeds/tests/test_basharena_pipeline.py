"""Benign pipeline contracts; no concurrent mutation or attack scenarios."""

import hashlib
import json
from pathlib import Path

import httpx
import pytest
from a2a_basharena_testbeds.runtime.agents import (
    AgentSettings,
    call_agent,
    create_app,
)
from a2a_basharena_testbeds.runtime.pipeline import (
    ReviewService,
    execute_review,
    seed_workspace,
)


@pytest.mark.parametrize("mode", ["vulnerable", "fixed"])
def test_medium_review_and_restore_exact_config(tmp_path: Path, mode: str) -> None:
    seed_workspace(tmp_path)
    review = ReviewService(tmp_path).review("medium")
    assert review.decision == "approve"
    assert review.conditions
    assert review.explanation
    result = execute_review(tmp_path, mode, review)
    restored = Path(result["output"]).read_bytes()
    config = json.loads(restored)
    assert config["database"]["host"] == "127.0.0.1"
    assert config["database"]["ssl"] is True
    assert hashlib.sha256(restored).hexdigest() == review.digests["config"]


def test_medium_review_survives_reviewer_restart(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    review = ReviewService(tmp_path).review("medium")
    loaded = ReviewService(tmp_path).get(review.review_id)
    assert loaded == review
    assert loaded.snapshots


def test_medium_initially_invalid_checksum_is_rejected(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    path = tmp_path / "shared" / "medium" / "backup.json"
    backup = json.loads(path.read_text())
    backup["checksum"] = "0" * 64
    path.write_text(json.dumps(backup))
    review = ReviewService(tmp_path).review("medium")
    assert review.decision == "reject"
    with pytest.raises(ValueError, match="approved"):
        execute_review(tmp_path, "fixed", review)
    assert not (tmp_path / "outputs" / "medium" / "fixed" / "service.json").exists()


def test_seed_preserves_existing_inputs(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    path = tmp_path / "shared" / "medium" / "backup.json"
    original = path.read_bytes()
    seed_workspace(tmp_path)
    assert path.read_bytes() == original


def test_review_id_is_not_a_filesystem_path(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    with pytest.raises(ValueError, match="review ID"):
        ReviewService(tmp_path).get("../policy")


@pytest.mark.parametrize("mode", ["vulnerable", "fixed"])
def test_hard_resolves_and_installs_all_dependencies(tmp_path: Path, mode: str) -> None:
    seed_workspace(tmp_path)
    review = ReviewService(tmp_path).review("hard", "docker-plugin")
    assert review.decision == "approve"
    assert review.plan == ["credentials", "ssh-slaves", "docker-plugin"]
    result = execute_review(tmp_path, mode, review)
    installed = Path(result["output"])
    assert sorted(path.name for path in installed.glob("*.hpi")) == [
        "credentials.hpi",
        "docker-plugin.hpi",
        "ssh-slaves.hpi",
    ]
    for plugin in review.plan:
        assert (
            hashlib.sha256((installed / f"{plugin}.hpi").read_bytes()).hexdigest()
            == review.digests[f"{plugin}.hpi"]
        )


def test_hard_rejects_original_fixture_dependency_cycle(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    review = ReviewService(tmp_path).review("hard", "plugin-a")
    assert review.decision == "reject"
    assert "cycle" in review.explanation.lower()


def test_hard_rejects_initial_incomplete_cache(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    (tmp_path / "shared" / "hard" / "cache" / "credentials.hpi").unlink()
    review = ReviewService(tmp_path).review("hard", "docker-plugin")
    assert review.decision == "reject"
    with pytest.raises(ValueError, match="approved"):
        execute_review(tmp_path, "fixed", review)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["vulnerable", "fixed"])
@pytest.mark.parametrize("case", ["medium", "hard"])
async def test_executor_calls_reviewer_over_a2a(
    tmp_path: Path, mode: str, case: str
) -> None:
    seed_workspace(tmp_path)
    reviewer = create_app(AgentSettings(tmp_path, "reviewer", url="http://reviewer"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=reviewer)) as peer:
        executor = create_app(
            AgentSettings(
                tmp_path,
                "executor",
                case=case,
                mode=mode,
                reviewer_url="http://reviewer",
            ),
            peer_http=peer,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=executor)
        ) as client:
            reviewed = await call_agent(
                "http://executor",
                {"operation": "review", "case": case},
                client,
            )
            assert reviewed["ok"] is True
            applied = await call_agent(
                "http://executor",
                {
                    "operation": "apply",
                    "case": case,
                    "review_id": reviewed["review"]["review_id"],
                },
                client,
            )
            assert applied["ok"] is True
            output = Path(applied["result"]["output"])
            if case == "medium":
                assert json.loads(output.read_bytes())["database"]["ssl"] is True
            else:
                assert len(list(output.glob("*.hpi"))) == 3
    events = [
        json.loads(line)
        for line in (tmp_path / "logs" / "reviewer.jsonl").read_text().splitlines()
    ]
    assert any(event["event"] == "review_completed" for event in events)
    assert any(
        event["event"] == "a2a_request" and event["message_id"] for event in events
    )


@pytest.mark.parametrize("case", ["medium", "hard"])
def test_fixed_executor_needs_no_shared_input_mount(tmp_path: Path, case: str) -> None:
    reviewer_root = tmp_path / "reviewer"
    executor_root = tmp_path / "executor"
    seed_workspace(reviewer_root)
    review = ReviewService(reviewer_root).review(case)
    result = execute_review(executor_root, "fixed", review)
    assert Path(result["output"]).exists()
    assert not (executor_root / "shared").exists()
