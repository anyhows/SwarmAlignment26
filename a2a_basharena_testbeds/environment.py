"""Record execution dependencies without dumping process environment variables."""

import importlib.metadata
import platform
import re
from pathlib import Path
from typing import Any

import a2a


def report() -> dict[str, Any]:
    """Describe only the interpreter, SDK location, and declared dependency versions."""
    versions = {}
    requirements = Path(__file__).with_name("requirements.in").read_text()
    for line in requirements.splitlines():
        match = re.match(r"([A-Za-z0-9_.-]+)", line)
        if match:
            name = match.group(1)
            try:
                versions[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                versions[name] = None
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "sdk_module": a2a.__file__,
        "packages": versions,
    }
