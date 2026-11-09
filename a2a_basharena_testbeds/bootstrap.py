"""Make the pinned SDK and this package available without a neighboring checkout."""

import os
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
REPOSITORY = PACKAGE.parent


def configure() -> None:
    """Use the bundled SDK for this process and its native service children."""
    paths = [str(PACKAGE / "vendor/a2a-sdk/src"), str(REPOSITORY)]
    for path in reversed(paths):
        if path not in sys.path:
            sys.path.insert(0, path)
    os.environ["PYTHONPATH"] = os.pathsep.join(
        [*paths, *filter(None, [os.environ.get("PYTHONPATH")])]
    )


def load_dotenv(path: Path) -> None:
    """Read simple key=value settings silently, preserving exported values."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            key = key.strip().removeprefix("export ").strip()
            if key:
                os.environ.setdefault(key, value.strip().strip("\"'"))
