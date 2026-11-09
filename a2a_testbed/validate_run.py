"""Integrity checks over finished runs: are the trials valid and independent?

  .venv/Scripts/python a2a_testbed/validate_run.py artifacts/a2a_runs/main [more dirs]

For every trial record it checks:
  1. a unique, existing workspace directory;
  2. the race happened where intended and only there: h_read is the original task (or the
     malicious one for malicious_before), and h_approve is the expected edit
     (h_read != h_approve exactly for *_race conditions);
  3. the workspace's final task.md hashes to h_approve (nothing edited it later);
  4. graded outcomes were graded in the docker sandbox, and the outcome agrees with the grader
     fields (LEAK <=> leaked, ok <=> task_done);
  5. defense=none implemented the file as it was at use time (h_use == h_approve);
  6. verify trials with a changed task have a verifier verdict;
  7. transcripts exist for LLM runs, every call is tagged with a trial, and every trial that
     needed an LLM call has at least one;
  8. config.json shows a clean tree (dirty == false);
  9. no Adaption API key anywhere in the run directory.
Exits non-zero if any check fails.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from toctou.agents import FIXTURES, sha  # noqa: E402

ORIG = sha((FIXTURES / "task.md").read_text())
EDIT_FIXTURE = {"benign_race": "task_benign_edit.md", "update_race": "task_update.md",
                "malicious_race": "task_malicious.md", "subtle_race": "task_subtle.md",
                "inject_race": "task_inject.md", "config_race": "task_config.md",
                "malicious_before": "task_malicious.md"}
EXPECTED_APPROVE = {c: sha((FIXTURES / f).read_text()) for c, f in EDIT_FIXTURE.items()}
EXPECTED_APPROVE["none"] = ORIG
GRADED = {"ok", "stale", "LEAK", "broken"}


def api_key(repo: Path) -> str:
    env = repo / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            m = re.match(r"\s*(?:export\s+)?ADAPTION_API_KEY\s*=\s*(.+)", line)
            if m:
                return m.group(1).strip().strip("\"'")
    return ""


def validate(run: Path, key: str) -> list[str]:
    errs = []
    cfg = json.loads((run / "config.json").read_text()) if (run / "config.json").exists() else {}
    if cfg.get("dirty"):
        errs.append("config.json: dirty working tree at launch")
    recs = [json.loads(l) for l in (run / "results.jsonl").open()]
    seen = set()
    for r in recs:
        tag = f"{r['model']}/{r['condition']}/{r['trial']}"
        ws = run / r["model"] / r["condition"] / str(r["trial"])
        if tag in seen or not ws.is_dir():
            errs.append(f"{tag}: duplicate or missing workspace")
        seen.add(tag)
        cond = r["condition"]
        if cond == "dep_race":
            continue
        exp_read = EXPECTED_APPROVE["malicious_before"] if cond == "malicious_before" else ORIG
        if r.get("h_read") != exp_read:
            errs.append(f"{tag}: h_read {r.get('h_read')} != expected {exp_read}")
        if r.get("h_approve") != EXPECTED_APPROVE.get(cond):
            errs.append(f"{tag}: h_approve {r.get('h_approve')} != expected edit")
        if cond.endswith("_race") == (r.get("h_read") == r.get("h_approve")):
            errs.append(f"{tag}: race {'missing' if cond.endswith('_race') else 'unexpected'}")
        if ws.is_dir() and sha((ws / "task.md").read_text()) != r.get("h_approve"):
            errs.append(f"{tag}: task.md changed after the approval point")
        if r["outcome"] in GRADED:
            if r.get("sandbox") != "docker":
                errs.append(f"{tag}: graded outside the docker sandbox")
            if (r["outcome"] == "LEAK") != bool(r.get("leaked")):
                errs.append(f"{tag}: outcome/leak mismatch")
            if r["outcome"] == "ok" and not r.get("task_done"):
                errs.append(f"{tag}: ok without task_done")
            if r.get("defense") == "none" and r.get("h_use") != r.get("h_approve"):
                errs.append(f"{tag}: baseline did not use the file as of use time")
        if (r.get("defense") == "verify" and cond.endswith("_race")
                and r.get("decisions", [""])[0] == "approve" and not r.get("verdicts")):
            errs.append(f"{tag}: verify trial with changed task but no verdict")

    llm_run = cfg.get("args", {}).get("mode") == "llm" or cfg.get("args", {}).get("approver") == "llm" \
        or cfg.get("args", {}).get("verifier") == "llm"
    tpath = run / "transcripts.jsonl"
    if llm_run:
        if not tpath.exists():
            errs.append("LLM run without transcripts.jsonl")
        else:
            ts = [json.loads(l) for l in tpath.open()]
            untagged = sum(1 for t in ts if "trial" not in t)
            if untagged:
                errs.append(f"{untagged} transcript entries without a trial tag")
            per = Counter(f"{t.get('agent')}/{t.get('condition')}/{t.get('trial')}" for t in ts)
            needs = [f"{r['model']}/{r['condition']}/{r['trial']}" for r in recs
                     if r["model"] != "scripted" or r.get("approver") not in (None, "rule")
                     or (r.get("verifier") == "llm" and r["condition"].endswith("_race"))]
            missing = [t for t in needs if per[t] == 0]
            if missing:
                errs.append(f"{len(missing)} trials have no transcript, e.g. {missing[:3]}")
    if key:
        for f in run.rglob("*"):
            if f.is_file() and key in f.read_text(errors="ignore"):
                errs.append(f"API KEY FOUND in {f.relative_to(run)}")
    return errs


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    key = api_key(repo)
    roots = [Path(a) for a in sys.argv[1:]]
    runs = sorted({f.parent for r in roots for f in r.rglob("results.jsonl")})
    bad = 0
    for run in runs:
        errs = validate(run, key)
        n = sum(1 for _ in (run / "results.jsonl").open())
        print(f"{'OK  ' if not errs else 'FAIL'} {run.name}  ({n} trials)")
        for e in errs[:10]:
            print(f"     - {e}")
        bad += bool(errs)
    print(f"\n{len(runs) - bad}/{len(runs)} runs valid")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
