"""Run trials from the SwarmAlignment26 root, matching the companion testbed CLI."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from a2a_basharena_testbeds.bootstrap import configure  # noqa: E402

configure()

from a2a_basharena_testbeds.experiment import main  # noqa: E402

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
