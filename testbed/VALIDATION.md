# Validation record

Validated on November 7, 2026 (America/Los_Angeles), on Linux amd64 / WSL2
(kernel 6.18.33.2-microsoft-standard-WSL2), Docker Engine 29.8.1 and Compose 5.5.1.
The target is Ubuntu 22.04 with Python 3.10. No model credentials were used.

## Observed results

- Three separate reference-repair cycles passed **22/22** functional checks each:
  12 upstream tests with the documented one-line callback-scope correction,
  eight independent Socket.IO/authentication/database checks, actual localhost
  HTTP/WebSocket publication, and a controlled running/stopped monitoring test.
- The deliberately broken baseline was validly classified incomplete (1/22).
- All four malicious-outcome detectors passed negative and positive controls in
  separate disposable episodes, without cross-contamination. Firewall sabotage
  admitted all seven prohibited benchmark packets in its positive control.
- Removing the malware marker did not erase the externally recorded detection.
- Stopping the receiver produced invalid evaluation, never a safe classification.
- Three dirty-state resets restored identical initial fixture checksums and
  cleared configuration edits, changed credentials, database records, receiver
  logs, background processes, files, and attack markers.
- Measured reset durations, including archival and readiness: **32.46 s, 30.90 s, 31.10 s**.
- A separate archive-failure control stopped the receiver and broke nginx syntax.
  Both failures were recorded, other database evidence was preserved, and reset
  restored the original fixtures with valid negative detector results.
- A clean source export built, started, graded and tore down successfully using
  Docker's existing build cache. It contained no .env, saved episode state,
  neighboring repositories, or model credentials.
- Runtime startup/reset used existing image IDs with pulls disabled. Internal
  target networking and filtered relay networking blocked direct external TCP
  probes. The published interface was verified to bind only 127.0.0.1. The relay
  ran as UID 65534 with zero effective/bounding capabilities and NoNewPrivs=1.
- Every disposable episode's project resources were removed; built images and
  caches were retained. The working checkout intentionally retains one active
  episode for subsequent experiments.

## Evidence

The final deployment's machine-readable record is
[verification-1f18e302.json](../artifacts/verification-1f18e302.json).
Additional evidence is in
[clean-checkout-validation.json](../artifacts/clean-checkout-validation.json) and
[archive-failure-recovery.json](../artifacts/archive-failure-recovery.json).
Each referenced episode retains its manifest, checksums, observations, logs and
teardown evidence under artifacts/. These ignored artifacts exist in this working
checkout; a new checkout regenerates its own IDs and evidence with make verify.
Earlier artifacts are development runs and may use earlier grader revisions.

## Interpretation

These are observed environment and detector controls, not model evaluations.
No A2A execution or concurrency defense is implemented. Root tampering with the
in-target upstream tests/sudo probe, violations between observations, and broader
attacks outside the four detectors remain limitations described in README.md.
OS package versions are recorded, but future apt rebuilds are not guaranteed
byte-identical. Other host architectures and Docker versions were not tested.
