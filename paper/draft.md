# Approved, Then Swapped: Time-of-Check-to-Time-of-Use Races in Agent-to-Agent Approval Flows

*Draft, 2026-11-08. Nikhil, Adi, Yash. Swarm Alignment hackathon (track 3; possibly track 1 [?]).*
*Status: **[MAIN RESULTS PENDING]** tables are filled from `a2a_testbed/summarize.py` once the
main runs finish. Everything else reflects runs already completed.*

---

## Abstract

Multi-agent systems built on Google's Agent-to-Agent (A2A) protocol often put a human or model
approver in the loop: an agent proposes a plan, pauses (`INPUT_REQUIRED`), and acts once it is
approved. A2A lets an agent ask for approval but leaves the scope and enforcement of that
approval to the application. We show that a natural implementation of this pattern has a
**time-of-check-to-time-of-use (TOCTOU) race**: another agent with legitimate write access to
the shared task file can rewrite it after the plan is approved and before it is executed, so
the approved agent implements something the approver never saw.

In a minimal A2A testbed, a key-exfiltrating rewrite succeeds in **5/5** trials with a real
LLM agent (deepseek-v4-flash), while the same rewrite made *before* the agent reads the task is
caught by the approver **2/2**. We evaluate five defenses:
- binding the approval to a content hash;
- implementing the approved snapshot;
- re-planning and re-approving;
- an **independent LLM verifier** that checks the change against decision criteria emitted with
  the plan, escalating to the approver when it objects or is unsure.

Hash binding with a single read closes the race but rejects every concurrent edit. Snapshots
never leak but silently ship stale work. Verify-and-escalate preserves harmless edits in one
approval round, routes substantive changes to the approver, and resisted a prompt injection
aimed at the verifier itself. Our main finding is that **the verifier is only as good as its
criteria**: model-written criteria over-specify incidental values, so a conservative verifier
treats legitimate updates as violations. **[MAIN RESULTS PENDING: one sentence of headline
rates across 3 agent models.]**

## 1. Introduction and theory of change

Agents increasingly coordinate through shared artifacts (task files, tickets, repositories)
and through protocols like A2A. Approval gates are a common safety measure: a person or a
model reviews what an agent intends to do before it does it. An approval, though, is a
statement about the *content the approver saw*. If the content can change between the check
and the use, the gate certifies something other than what runs.

This is the classic TOCTOU pattern from operating-system security, transplanted to
multi-agent systems. It is easy to fall into with A2A: the Python SDK resumes an
`INPUT_REQUIRED` task by calling the agent's `execute()` again from scratch, so a stateless
agent naturally re-reads its inputs from the shared workspace after approval. That re-read is
the "use."

**Theory of change.** If approval gates are a load-bearing safety layer in agent swarms, they
must bind to *what was approved*, not to a file name. We provide:
1. a reproducible demonstration that the race is real with off-the-shelf models;
2. a drop-in, application-level defense that needs no protocol change (it could be packaged as
   an A2A extension);
3. measurements of what each defense costs in lost or stale work and extra approval rounds;
4. failure modes, notably criteria quality and the approver becoming the weakest link, that
   anyone deploying such gates should know about.

**Race windows.** We split the race into three windows:
(1) the agent reads the task → verification starts;
(2) verification starts → ends;
(3) verification ends → the task is used.
Our defenses close all three for the task file by (a) binding every decision to a content
hash and (b) reading the file **once** at use time and implementing from exactly the bytes
that were checked.

## 2. Related work

- **TOCTOU races** in file systems are a classic security bug class. Standard mitigations
  operate on handles or content rather than names, and avoid separate check and use steps
  [Bishop & Dilger 1996].
- **Optimistic concurrency control** validates at commit time that what a transaction read is
  unchanged [Kung & Robinson 1981]. Our `hash` defense is OCC applied to an approval.
- **Decision conflicts vs. version conflicts.** Recent work evaluates *selective revalidation*:
  re-checking only the conditions a decision depends on, using developer-specified conditions
  [arXiv 2609.08015, "From Version Conflicts to Decision Conflicts"; *verify citation*]. Our
  `verify` defense asks whether those conditions can be *generated* by the agent and *checked*
  by an independent LLM.
- **Indirect prompt injection.** LLM components that read attacker-controlled content can be
  steered by instructions embedded in it [Greshake et al. 2023]. Our `inject_race` attack
  targets the verifier this way.
- **A2A protocol.** The protocol defines `input-required` and `auth-required` task states but
  leaves the scope and enforcement of authorization to implementations [A2A specification].
- **AI control / sabotage benchmarks.** BashArena-style environments evaluate whether agents
  can be made to take unauthorized actions during legitimate tasks
  [BashArena, Redwood Research]. We plan to port the race to that setting (Future Work).
- *TODO: add the hackathon's listed resources that we build on.*

## 3. Methodology

### 3.1 Testbed

Two A2A agents (Python SDK, JSON-RPC transport, commit `28f8a62`) share a workspace containing
`task.md` and a small HTTP server, `server.py`.
- **Agent A (worker)** reads `task.md`, proposes a plan (plus decision criteria, for `verify`),
  pauses with `TASK_STATE_INPUT_REQUIRED`, and on approval implements the task in `server.py`.
- **Agent B (collaborator)** may edit `task.md` *through its own A2A skill*. It is a scripted
  adversary, so the content and timing of each edit are controlled.
- **The approver** sees only A's plan. It is either a keyword rule or an LLM (glm-53-flash)
  with a fixed security policy that treats self-claimed approvals as untrusted.
- **The grader** runs the resulting server with `UPSTREAM_API_KEY` set to a canary
  (`sk-CANARY-…`) and calls `/version`. Outcomes are scored by script, with no LLM judge.

A runner orchestrates each trial with explicit synchronization points, with no sleeps. B's
edit lands exactly inside A's approval window. The runner logs the sha256 of `task.md` at
read, at approval, and at use.

### 3.2 Conditions

| condition | B's edit | correct outcome |
|---|---|---|
| none | — | ok |
| benign_race | wording-only edit, in the window | ok |
| update_race | legitimate correction 1.4.2 → 1.4.3, in the window | ok (ships 1.4.3) |
| malicious_before | key-leaking spec, **before** A reads | rejected (shows the approver works) |
| malicious_race | key-leaking spec, in the window | no leak |
| subtle_race | leaks via `dict(os.environ)`; never names a credential | no leak |
| inject_race | key leak + a comment telling verifiers the change is pre-approved | no leak |
| config_race | **held out**: leaks via a dump of the server's string settings; written after the design freeze and never piloted on an LLM | no leak |

Outcomes: `ok`, `stale` (old version shipped after a legitimate update), `LEAK` (canary in
any response), `rejected` (by the approver), `blocked` (by the defense), `broken`,
`agent_error`.

### 3.3 Defenses (all application-level; no A2A change)

Every defense reads `task.md` once on resume and implements from exactly those bytes. The
approver's reply carries `approved_task_sha256`, the hash A reported with the approved plan.

| defense | if `task.md` changed since approval |
|---|---|
| none | implement whatever the file says now (baseline) |
| hash | refuse (`blocked`) |
| snapshot | implement the approved bytes; ignore the edit |
| replan | re-plan from the current bytes and ask the approver again (≤1) |
| verify | an independent verifier compares the change with the approved plan and **decision criteria**. A confident "consistent" proceeds. A confident "inconsistent", or a confidence below 0.8, escalates to re-approval. |

The verifier prompt treats both task versions as untrusted data and returns
`{"consistent", "confidence", "reason"}`. Any failure to parse the reply counts as no
confidence, which escalates (fail-safe).

### 3.4 Models and sampling

- **Agent A:** deepseek-v4-flash, qwen3.8-27b, gemma-4-31b-it.
- **Approver and verifier:** glm-53-flash, a different family from all agents.
- **Sampling:** the API's default temperature.
- **Host:** all hosted by Adaption Labs (`/api/v1/responses`).

**Reproducibility:**
- Every run writes `config.json` with the git SHA and arguments.
- Every LLM request is logged with usage and cost.
- Commands are listed in `a2a_testbed/README.md`.

### 3.5 Protocol

The pilots (n = 1–2 per cell) shaped the design. We then froze it at commit `54f62ad`, wrote
down the main experiment before any results existed, and ran it with n = 5 per cell.
- **One deviation:** an undocumented API rate limit (≈30–40 requests/min) forced a relaunch
  and the removal of `replan` from the LLM matrix. That decision was recorded before any
  main-run results.
- **Model independence:** `hash` and `snapshot` decide before A implements anything, so they
  are reported from scripted runs.

## 4. Results

### 4.1 The race is real (RQ1)

**Scripted agent** (deterministic implementation of whatever the spec says), 3 trials per cell:
- malicious_race → **LEAK 3/3** (`h_read ≠ h_use`);
- malicious_before → rejected 3/3;
- none / benign → ok.

**deepseek-v4-flash as agent A**, keyword approver:

| condition | n | ok | LEAK | rejected |
|---|---|---|---|---|
| none | 2 | 2 | | |
| benign_race | 2 | 2 | | |
| malicious_before | 2 | | | 2 |
| malicious_race | 5 | | **5** | |

- **Leaks:** in every malicious_race trial, the approved plan described only
  `{"service","version"}`, and the deployed endpoint returned `"upstream_key":
  "sk-CANARY-7f3a9c2e"`.
- **Control:** when the same edit landed before the read, the model's plan disclosed the key
  and the approver rejected it.

### 4.2 Defense comparison: scripted reference (keyword approver, n = 3 per cell)

| defense | benign | update | malicious | subtle | inject | config (held-out) | rounds on races |
|---|---|---|---|---|---|---|---|
| none | ok | ok | LEAK | LEAK | LEAK | LEAK | 1 |
| hash | blocked | blocked | blocked | blocked | blocked | blocked | 1 |
| snapshot | ok | **stale** | ok | ok | ok | ok | 1 |
| replan | ok (2 rounds) | ok (2) | rejected | **LEAK** | rejected | **LEAK** | 2 |
| verify (scripted verifier, escalate) | ok (1 round) | ok (1) | rejected | **LEAK** | rejected | **LEAK** | 1–2 |

**Escalation is only as strong as the approver.** The keyword approver doesn't recognize
`dict(os.environ)` or a settings dump as a secret. So both re-approval defenses leak the
subtle and held-out attacks, even though the scripted verifier flagged them.

**Dependency race: the hash's blind spot (scripted, n = 2 per defense).**
- **Setup:** `task.md` says the response body is defined in `response.json`. B edits
  `response.json`, not `task.md`, inside the approval window.
- **Result:** **every defense leaks 2/2**: none, hash, snapshot, replan and verify.
- **Why:** the `task.md` hash is unchanged (`h_read == h_use`), the approved plan was harmless,
  and the deployed endpoint returned the canary. Binding an approval to one file's hash is only
  as complete as the set of files the decision depends on.

### 4.3 Main experiment (LLM agents, LLM approver and verifier, n = 5 per cell)

**[MAIN RESULTS PENDING]**: one table per agent model for `none` and `verify`, with leak
rate, false-reject rate, stale rate, approval rounds and seconds. Then a pooled summary row.

### 4.4 Verifier behavior (pilots)

- **Scripted criteria, deepseek verifier:** 6/6 correct.
  - benign: consistent (1.0);
  - update: consistent (0.90, 0.85);
  - malicious: inconsistent (1.0).
- **Criteria written by the agent model:** the agent wrote "the version value must remain
  exactly 1.4.2", and the verifier blocked the legitimate update.
- **Asking for property-style criteria:** this improved the criteria ("the schema is the
  stable requirement"), but the verifier still objected (0.9), citing the literal value in the
  *plan*.
- **Escalating instead of blocking:** this recovered the update (2 rounds) and stayed safe. The
  attacker's re-plan openly listed `upstream_key`, and the approver rejected it.
- **Injection:** the glm verifier rejected the injected "pre-approved by security, treat as
  consistent" note (inconsistent, 0.99), and the LLM approver rejected the `dict(os.environ)`
  re-plan that the keyword rule had approved.
- **Reasoning effort:** deepseek spent ≈40 reasoning tokens on harmless edits but ≈1000–1500 on
  legitimate updates.

### 4.5 Calibration (supplement)

**[PENDING]**: scripted agent and criteria, glm verifier, 10 trials × 6 race conditions.
Sweeping the threshold over the stored confidences gives miss rate (attack auto-accepted:
the only unsafe path), false-reject rate, and escalation rate. `update_race` is reported both
as "should pass" and as "policy-ambiguous."

### 4.6 Cost

All runs used cheap hosted models. Through the pilots, the total was **88 calls, ≈0.008
credits**. **[PENDING: final totals from `artifacts/adaption_ledger.jsonl`.]**

## 5. Discussion

- **The fix for the race itself is small and standard.** Bind approvals to content, and use
  exactly what was checked. This closed the `task.md` race with no locks or throttling. That
  makes earlier plans to lock files during verification, or throttle agents, unnecessary in
  this setting.
- **The hard part is precision, not safety.**
  - `hash` throws away every concurrent edit.
  - `snapshot` silently ships stale work.
  - `replan` asks a person (or model) to re-approve every change.
  - `verify` tries to approve only the safe changes automatically. Its quality is bounded by
    the decision criteria, and models write criteria that pin incidental values. Whether a
    version bump is "within what was approved" is genuinely a policy choice, so a careful
    verifier should escalate rather than block. That is the design we settled on.
- **Escalation moves the burden to the approver.** With a weak approver, any re-approval
  defense inherits its blind spots (§4.2). An LLM approver closed those cases in our pilots.
  Approver quality, and the human cost of extra rounds, are first-class metrics.
- **Treat the verifier as an attack surface.** It reads attacker-controlled text. Our
  injection attempt failed against glm-53-flash with an "untrusted data" instruction, but one
  attempt proves little.

## 6. Limitations and dual-use / ethical considerations (required)

**What the results do and don't establish:**
- **Sample size.** n is small (5 per cell in the main runs, 1–2 in the pilots), with one
  fixture family (a single endpoint task) and three agent models. The rates are illustrative,
  not population estimates.
- **The adversary is scripted and timed exactly.** Real attackers have to observe the window,
  though `INPUT_REQUIRED` is visible through task status, subscriptions and push notifications,
  and the window is the approver's latency (seconds to minutes).
- **The approver judges plans only, by design.** The keyword approver is weak, and the LLM
  approver and the verifier are the *same model* (glm-53-flash), so escalation is not two
  independent layers.
- **Detection may be on the easy side.** The verifier prompt names secret exposure as
  inconsistent, and three of our attacks have obviously sensitive payloads. The held-out
  `config_race` is a partial check.
- **The hash covers `task.md` only.** Files the decision depends on, and the file the agent
  writes, are not protected.
- **Default temperature; hosted models may change.**

**Dual-use:**
- The attack is simple once understood. Describing it could help someone exploit approval
  gates in real agent deployments.
- We think disclosure is net-positive. The fix is cheap and standard, the vulnerable pattern
  follows naturally from documented SDK behavior, and the canary-based testbed lets
  maintainers test their own gates.
- We release no exploit against a real system. All secrets are canaries.
- The injection attack is generic, and we report that it failed in our tests.
- A risk in the other direction: a defense that looks robust could create false confidence.
  We list its known gaps prominently.

## 7. Future work

See `a2a_testbed/FUTURE_WORK.md` (19 items). The most important:
- dependency manifests, so the hash covers referenced files;
- protecting the file the agent writes;
- structured criteria and separating the approval contract from the plan;
- verifier calibration and independence;
- stronger injection and subtle attacks;
- an LLM or human approver with measured cost;
- more models and larger n;
- porting the race to BashArena;
- packaging as an A2A "approval-binding" extension.

## References

- Bishop, M., & Dilger, M. (1996). Checking for race conditions in file accesses. *Computing
  Systems*, 9(2).
- Kung, H. T., & Robinson, J. T. (1981). On optimistic methods for concurrency control. *ACM
  Transactions on Database Systems*, 6(2).
- Greshake, K., et al. (2023). Not what you've signed up for: Compromising real-world
  LLM-integrated applications with indirect prompt injection. *AISec '23*.
- A2A Protocol Specification. https://a2a-protocol.org/ ; Python SDK
  https://github.com/a2aproject/a2a-python (commit 28f8a62).
- "From Version Conflicts to Decision Conflicts," arXiv:2609.08015 (2026). *Taken from our
  planning notes; verify before submission.*
- BashArena, Redwood Research. https://github.com/redwoodresearch/basharena_public
- *TODO: hackathon resource list.*
