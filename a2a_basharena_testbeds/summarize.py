"""Regenerate summaries from an existing results.jsonl without running agents."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from a2a_basharena_testbeds.bootstrap import configure  # noqa: E402

configure()
from a2a_basharena_testbeds.metrics import summarize  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    records = [
        json.loads(line)
        for line in args.results.read_text().splitlines()
        if line.strip()
    ]
    data, table = summarize(records)
    args.results.with_name("summary.json").write_text(json.dumps(data, indent=2) + "\n")
    args.results.with_name("summary.md").write_text(table)
    print(table)


if __name__ == "__main__":
    main()
