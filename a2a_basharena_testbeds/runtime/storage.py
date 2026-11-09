"""Workspace persistence and pinned upstream fixture loading."""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UPSTREAM = Path(__file__).parent / "upstream"


def now() -> str:
    """Return a timezone-aware event timestamp."""
    return datetime.now(timezone.utc).isoformat()


def digest(content: bytes) -> str:
    """Identify the bytes consumed by a pipeline step."""
    return hashlib.sha256(content).hexdigest()


def atomic_write(path: Path, content: bytes) -> None:
    """Publish a complete file using a temporary sibling and atomic rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
        Path(temporary).replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_initial(path: Path, content: bytes) -> None:
    """Initialize a fixture once, preserving existing workspace files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        return


def encode_json(data: Any) -> bytes:
    """Encode readable, stable JSON fixture or result files."""
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()


def upstream_record(task_id: str) -> dict[str, Any]:
    """Load a vendored task after checking its pinned file digest."""
    manifest = json.loads((UPSTREAM / "manifest.json").read_text())
    content = (UPSTREAM / f"{task_id}.json").read_bytes()
    if digest(content) != manifest["tasks"][task_id]["file_sha256"]:
        raise ValueError(f"Vendored BashArena task checksum mismatch: {task_id}")
    return json.loads(content)


def append_event(root: Path, component: str, event: str, **fields: Any) -> None:
    """Append a content-free pipeline event for inspection."""
    path = root / "logs" / f"{component}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        stream.write(json.dumps({"at": now(), "event": event, **fields}) + "\n")
