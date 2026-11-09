"""Reuse the pinned BashArena Flask APIs and stage their benign data."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

import httpx

from a2a_basharena_testbeds.runtime.pipeline import backup_content
from a2a_basharena_testbeds.runtime.plugins import dependency_plan
from a2a_basharena_testbeds.runtime.storage import (
    atomic_write,
    digest,
    encode_json,
    upstream_record,
)

if TYPE_CHECKING:
    from a2a_basharena_testbeds.runtime.models import Case


class FixtureApplication(Protocol):
    """The narrow server interface exposed by the vendored Flask app."""

    def run(self, *, host: str, port: int, debug: bool, use_reloader: bool) -> None:
        """Serve the local fixture API."""
        ...


def repository_headers() -> dict[str, str]:
    """Return the fixture service's local-development authentication header."""
    return {"X-API-Key": os.environ.get("BASHARENA_API_KEY", "local-fixture-key")}


def create_repository(root: Path, case: Case) -> FixtureApplication:
    """Load the original task API, changing only local fixture configuration."""
    record = upstream_record("43141659" if case == "medium" else "29328278")
    # Only pinned, vendored source is loaded here; no request or staged input
    # can select Python source. Original setup scripts are never run on the host.
    with tempfile.TemporaryDirectory(prefix="basharena-api-") as directory:
        source = Path(directory) / "app.py"
        source.write_text(record["app_file"])
        loader = importlib.machinery.SourceFileLoader(
            f"basharena_{case}_api", str(source)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        if spec is None:
            raise ValueError("Could not load the pinned BashArena API")
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    module.__dict__["API_KEY"] = repository_headers()["X-API-Key"]
    if case == "hard":
        module.__dict__["plugin_data_dir"] = str(
            (root / "repository" / "plugin_data").resolve()
        )
    return cast("FixtureApplication", module.__dict__["app"])


async def stage_from_repository(
    root: Path, case: Case, url: str, subject: str = "docker-plugin"
) -> dict[str, Any]:
    """Fetch benign artifacts through the task's original HTTP API."""
    async with httpx.AsyncClient(
        timeout=30, trust_env=False, headers=repository_headers()
    ) as client:
        if case == "medium":
            source = json.loads(
                (root / "shared" / "medium" / "backup.json").read_text()
            )
            backup_content(encode_json(source))
            response = await client.post(f"{url.rstrip('/')}/backup", json=source)
            response.raise_for_status()
            backup_id = response.json()["backup_id"]
            response = await client.get(f"{url.rstrip('/')}/backup/{backup_id}")
            response.raise_for_status()
            data = response.json()
            backup = {
                key: data[key]
                for key in ("content", "checksum", "filename", "timestamp")
            }
            content = encode_json(backup)
            backup_content(content)
            atomic_write(root / "shared" / "medium" / "backup.json", content)
            return {
                "case": case,
                "backup_id": backup_id,
                "staged": ["backup.json"],
            }
        response = await client.get(f"{url.rstrip('/')}/manifest")
        response.raise_for_status()
        manifest = response.json()
        trusted = json.loads((root / "policy" / "manifest.json").read_text())
        if manifest["plugins"] != trusted["plugins"]:
            raise ValueError(
                "Repository metadata differs from the seeded trusted manifest"
            )
        plan = dependency_plan(trusted, subject)
        downloaded: dict[str, bytes] = {}
        for name in plan:
            response = await client.get(f"{url.rstrip('/')}/plugins/{name}.hpi")
            response.raise_for_status()
            content = response.content
            if digest(content) != trusted["plugins"][name]["sha256"]:
                raise ValueError(f"Repository checksum mismatch: {name}")
            downloaded[f"{name}.hpi"] = content
        for filename, content in downloaded.items():
            atomic_write(root / "shared" / "hard" / "cache" / filename, content)
        return {"case": case, "staged": list(downloaded), "plan": plan}
