# Revised plan: delegated content consistency

## Goal and scope

Measure whether the data used by a delegated worker matches the approved data,
using harmless updates to synthetic catalog records. Preserve two windows:
W1 (approval to first read) and W2 (validation to use). Remove Linux account
management, destructive actions, privileged fixtures, shell access, and any
real deployment target from every phase.

The approver, runner, worker code, and state verifier are trusted. A test
controller changes the source document at explicit event boundaries. Only
synthetic data fields change. The source has no access to the approval key.

## Research questions

1. Which checks detect material changes in W1 and W2?
2. What false-block rate do byte-level checks cause on cosmetic reissues?
3. Does using the exact approved snapshot prevent inconsistent operations?
4. Which change schedules defeat check-only or retrospective validation?
5. Once integrated, what content-binding mechanisms does the pinned A2A
   specification/SDK provide, and which checks belong in application code?

Protocol and SDK classifications require pinned-source inspection and actual
A2A captures; local HTTP behavior alone cannot support those conclusions.

## Phase 1: deterministic local foundation

- [x] Fresh synthetic fixture for each trial; fixed operation vocabulary.
- [x] Approvals signing raw and canonical digests with a local HMAC key.
- [x] Real loopback HTTP source; exact application-level HTTP byte captures.
- [x] Explicit sequence boundaries without sleeps for W1 and W2 changes.
- [x] Baseline, before-check, after-check, after-use, and cosmetic controls.
- [x] No guard, check-only raw hash, use-time raw hash, use-time canonical hash.
- [x] Hash-linked ledger, mutation event IDs, state comparison, artifact hashes.
- [x] Automated checks for schedules, outcomes, and ledger tampering.
- [ ] Integrate the SDK at an exact reviewed commit and record the applicable
      specification version; inspect URI resolution and binding semantics.
- [ ] Add an observe-only A2A tap; keep content-fetch and A2A evidence separate.
- [ ] Package the synthetic worker in an unprivileged, digest-pinned container
      with an internal network, limits, no host mounts, and no Docker socket.
- [ ] Repeat trials through that integration before classifying SDK behavior.

The local foundation is a runnable first increment, not completion of the A2A
experiment. No placeholder result is presented as a finding.

## Phase 2: stronger consistency and benign changes

Add an approval-bound snapshot, signed correction with explicit approval-version
handoff, a scenario interface, and full labeled decision exports. Define which
approval is authoritative at each event. Report inconsistent-operation rate,
detection rate, benign false-block rate, and safe-but-incomplete outcomes with
counts and denominators. Never count a blocked operation as a material change.

## Phase 3: additional schedules

Add change-and-restore, requester-dependent responses, and staged field changes.
Use explicit barriers for reproducible trials; measure natural timing in a
separate nondeterministic mode. Add optional model-driven workers limited to
the same synthetic update tool. Keep claims scoped to observed configurations.

## Phase 4: decision and delay policies

Add deterministic and fixture-backed typed judges first. Any external adapter
requires current provider documentation and opt-in configuration. Compare
freeze periods and quarantine delays using a virtual clock before real-time
experiments. Record calibration, decision latency, benign delay, and localization
against known mutation events. Deterministic state comparison remains ground
truth; model verdicts never determine whether a material deviation occurred.

## Evidence and reporting

Each trial records configuration, source fingerprint, approval, exact fetched
bytes, raw/canonical digests at approval/check/use, actual operations, mutation
IDs, and before/expected/actual states. The ledger commits to previous entries.
No claim of externally anchored or adversary-proof logging is made.

Local results describe this harness. Future SDK conclusions distinguish
protocol gap, SDK gap, application responsibility, and not reproduced, supported
by exact versions and evidence. Responsible upstream reporting applies only if
later integration establishes an actual upstream issue.
