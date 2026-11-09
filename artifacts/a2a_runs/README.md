# A2A testbed run data

Each run directory holds:
- `config.json`: git SHA and arguments (runs from 16:30 onwards);
- `results.jsonl`: one record per trial;
- `transcripts.jsonl`: full LLM prompts and replies, tagged by trial (runs from 16:50
  onwards);
- `summary.md`;
- the per-trial workspaces (`<agent>/<condition>/<trial>/task.md`, `server.py`).

Summarize any folder with `.venv/Scripts/python a2a_testbed/summarize.py [--headline] <dir>`.
Every LLM call is also in `../adaption_ledger.jsonl` (model, tokens, cost, status).

| folder | what |
|---|---|
| `main/` | **Main experiment** (frozen design, n = 5, LLM approver and verifier). |
| `calibration/` | Scripted agent + glm verifier, 10 × 6 race conditions (`calibrate.py`). |
| `scripted_ref/` | Scripted reference matrix: all 5 defenses × 8 conditions, n = 3, keyword approver. |
| `dependency_demo/` | Scripted dependency race: every defense leaks via an unhashed file. |
| `prelaunch_checks/` | Scripted check of all 5 defenses (1 trial per condition) at the launch commit, run just before the main experiment. |
| `smoke/` | Pre-launch end-to-end LLM smoke test (deepseek, n = 1 per condition). |
| `canary/` | One-trial checks of qwen and gemma as agent A. |
| `aborted/` | First main launch, killed by the API rate limit (16:37). |
| `aborted_no_transcripts/` | Relaunch, stopped so it could be redone with transcripts. |
| `aborted_old_grader/` | Relaunch, stopped: its grader passed the host environment to the server under test. |
| `aborted_host_grader/` | Relaunch, stopped: model-written code was graded on the host instead of in the sandbox. Also holds the earlier host-graded `scripted_ref_old/` and `dependency_demo_old/`. |
| `2026110x-…` (top level) | Development pilots, in chronological order (see `a2a_testbed/README.md`). |

**Redaction:** before the grader fix (commit `93f02a6`), the `subtle_race` attack's
`dict(os.environ)` response captured the host environment. Those `version_response` fields are
replaced with `[redacted: response contained a host-environment dump]`. Outcomes are
unaffected.
