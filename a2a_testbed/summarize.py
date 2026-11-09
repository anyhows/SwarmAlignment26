"""Aggregate run results into one Markdown table per agent model.

Usage (from SwarmAlignment26/):
  .venv/Scripts/python a2a_testbed/summarize.py                       # every run under artifacts/a2a_runs
  .venv/Scripts/python a2a_testbed/summarize.py RUN_DIR [RUN_DIR ...]   # selected runs

Columns: outcome counts, mean approval rounds (human or approver effort), mean seconds.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / "artifacts" / "a2a_runs"
OUTCOMES = ["ok", "stale", "LEAK", "rejected", "blocked", "broken", "agent_error"]
COND_ORDER = ["none", "benign_race", "update_race", "malicious_before", "malicious_race"]
DEF_ORDER = ["none", "hash", "snapshot", "replan", "verify"]


def load(dirs):
    for d in dirs:
        f = Path(d) / "results.jsonl"
        if f.exists():
            yield from (json.loads(line) for line in f.open())


def main() -> None:
    dirs = sys.argv[1:] or sorted(p for p in RUNS.iterdir() if p.is_dir())
    groups = defaultdict(list)
    for r in load(dirs):
        defense = r.get("defense", "none")
        if defense == "verify":
            defense += f"({r.get('verifier', 'scripted')})"
        groups[(r["model"], defense, r["condition"])].append(r)

    def order(key):
        model, defense, cond = key
        base = defense.split("(")[0]
        return (model, DEF_ORDER.index(base) if base in DEF_ORDER else 99, defense,
                COND_ORDER.index(cond) if cond in COND_ORDER else 99)

    print("| agent | defense | condition | n | " + " | ".join(OUTCOMES)
          + " | rounds | secs |")
    print("|---|---|---|---|" + "---|" * len(OUTCOMES) + "---|---|")
    for key in sorted(groups, key=order):
        rs = groups[key]
        c = Counter(r["outcome"] for r in rs)
        rounds = [r.get("approval_rounds", 1 if r.get("decision") else 0) for r in rs]
        secs = [r["seconds"] for r in rs if r.get("seconds") is not None]
        print(f"| {key[0]} | {key[1]} | {key[2]} | {len(rs)} | "
              + " | ".join(str(c[o]) if c[o] else "" for o in OUTCOMES)
              + f" | {sum(rounds) / len(rounds):.1f} | "
              + (f"{sum(secs) / len(secs):.1f}" if secs else "") + " |")


if __name__ == "__main__":
    main()
