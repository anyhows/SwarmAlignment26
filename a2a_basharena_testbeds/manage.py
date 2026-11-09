"""Build, inspect, or manually operate the testbed without starting an experiment."""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from a2a_basharena_testbeds.bootstrap import (  # noqa: E402
    PACKAGE,
    configure,
    load_dotenv,
)

configure()

from a2a_basharena_testbeds.stack import ARTIFACTS, Stack, build_image  # noqa: E402


def main() -> None:
    """Keep a named manual environment alongside isolated trial projects."""
    parser = argparse.ArgumentParser(
        description="Manage BashArena A2A containers and manual task handoffs"
    )
    parser.add_argument(
        "command", choices=["build", "up", "down", "status", "logs", "local", "cli"]
    )
    parser.add_argument("--port", type=int, default=47200)
    parser.add_argument("--mode", choices=["scripted", "llm"], default="scripted")
    parser.add_argument("--model", default="deepseek-v4-flash")
    args, rest = parser.parse_known_args()
    load_dotenv(PACKAGE.parent / ".env")
    if args.command == "build":
        build_image()
        return
    stack = Stack(
        ARTIFACTS / "manual-state",
        port=args.port,
        mode=args.mode,
        model=args.model,
        project="swarm-a2a-basharena-manual",
    )
    if args.command == "local":
        command = [
            sys.executable,
            "-m",
            "a2a_basharena_testbeds.runtime",
            "local",
            "--root",
            str(stack.root),
            "--base-port",
            str(args.port),
        ]
        raise SystemExit(subprocess.call(command, env=stack.environment))
    if args.command == "cli":
        command = [sys.executable, "-m", "a2a_basharena_testbeds.runtime", *rest]
        raise SystemExit(subprocess.call(command))
    if args.command == "up":
        try:
            stack.start()
        except BaseException:
            stack.stop()
            raise
        finally:
            if stack.log is not None:
                stack.log.close()
        print(f"Ready at http://127.0.0.1:{args.port}; state: {stack.root}")
        return
    stack.configure_docker()
    if args.command == "down":
        stack.stop()
    else:
        stack.command(["ps"] if args.command == "status" else ["logs", "--tail", "100"])


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
