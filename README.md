# Approved, Then Swapped: TOCTOU Races in A2A Approval Flows

Swarm Alignment Hackathon (Apart Research, November 2026). Yash Parikh, Nikhil Maturi and
Aditya Katre, Del Norte High School.

**Paper:** [`paper/submission.pdf`](paper/submission.pdf). It uses the Apart submission
template; the Word source is [`paper/main.docx`](paper/main.docx).

## What this is

In an Agent2Agent (A2A) approval flow, an agent proposes a plan, pauses with
`INPUT_REQUIRED`, and acts once an approver says yes. A2A leaves the scope of that approval to
the application. When a collaborating agent rewrites the shared task between approval and
execution, the agent implements something the approver never saw. That is a
time-of-check-to-time-of-use (TOCTOU) race. It is finding #6 ("Concurrent Access TOCTOU") in
[A2ABreak](https://arxiv.org/abs/2609.10871), which lists it without demonstrating it.

We built an executable A2A testbed that reproduces the race with real LLM agents. We then
compared five defenses that bind an approval to the exact content that was checked.

| Result (n = 5 per cell) | deepseek-v4-flash | qwen3.8-27b | gemma-4-31b-it |
|---|---|---|---|
| Canary-key leaks, no defense | 18/20 | 11/20 | 20/20 |
| Canary-key leaks, verify + escalate | **0/20** | **0/20** | **0/20** |
| Legitimate tasks wrongly blocked (verify) | 0/15 | 0/15 | 0/15 |

The same malicious edit made *before* the agent read the task was always caught (15/15). Edits
to a file the task merely references bypass every defense; see the dependency race in the
paper.

## Repository map

| Path | What it is |
|---|---|
| [`a2a_testbed/`](a2a_testbed/README.md) | **The main testbed.** Agents, attacks, the five defenses, the LLM approver and verifier, sandboxed grader, validator, summary scripts. |
| [`artifacts/a2a_runs/`](artifacts/a2a_runs/README.md) | **All trial data** for the paper: every trial's records, workspace and full LLM transcripts. `main/` is the main experiment. |
| `artifacts/adaption_ledger.jsonl` | Every LLM call made, with token counts and cost. |
| [`a2a_basharena_testbeds/`](a2a_basharena_testbeds/README.md) | Companion testbed (built by Nikhil): the same pause/resume race on two BashArena-derived tasks (paper Appendix E). |
| [`artifacts/a2a_basharena_testbeds/`](artifacts/a2a_basharena_testbeds/README.md) | Its runs and results table. |
| [`paper/`](paper/README.md) | LaTeX source (`main.tex`), template build (`build_docx.py`), figures. |
| [`testbed/`](testbed/README.md), `vendor/`, `Makefile` | An earlier BashArena nginx stretch environment. **Not used in the paper.** |
| `docs/` | Early planning notes and the Adaption API endpoint notes. |

## Reproduce

Requirements: Python 3.10+, Docker (grading runs model-written code only inside a locked-down
container), and the A2A Python SDK at commit `28f8a62` checked out next to this repo:

```sh
git clone https://github.com/a2aproject/a2a-python ../a2a-python
git -C ../a2a-python checkout 28f8a62
python -m venv .venv
.venv/bin/python -m pip install -e "../a2a-python[fastapi]"     # Windows: .venv/Scripts/python
```

These commands are free and make no LLM calls:

```sh
.venv/bin/python a2a_testbed/sandbox_selftest.py                  # 21 adversarial sandbox checks
.venv/bin/python a2a_testbed/run.py --trials 3                    # scripted agent, all defaults
.venv/bin/python a2a_testbed/summarize.py --headline artifacts/a2a_runs/main   # paper Table 2
.venv/bin/python a2a_testbed/validate_run.py artifacts/a2a_runs/main          # per-trial invariants
.venv/bin/python a2a_testbed/calibrate.py                         # calibration sweep (Appendix D)
```

LLM runs use the Adaption API. Put `ADAPTION_API_KEY=...` in a root `.env` (gitignored). The
runner is a dry run unless you pass `--yes`, and it enforces model allowlists and call caps. See
[`a2a_testbed/README.md`](a2a_testbed/README.md) for every flag and for the main experiment's
exact command line.

## Safety

- **Canary secrets only.** The only "secret" the attacks target is `sk-CANARY-7f3a9c2e`.
- **Sandboxed grading.** Model-written code runs only in a Docker container with no network, a
  read-only filesystem, a non-root user, no capabilities, and an environment holding only the
  port and the canary.
- **Scanned for keys.** Every committed result was checked for real API keys.
- **More detail:** [paper Appendix A](paper/submission.pdf) covers limitations and dual-use
  considerations.
