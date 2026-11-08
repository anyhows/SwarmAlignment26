# Delegated Content Consistency Testbed

A reproducible study of content changing between approval, validation, and use
in delegated workflows. The sole scenario updates the status of synthetic
catalog records held in memory. No accounts, operating-system settings, external
services, or real user data are affected.

The original Linux account-decommissioning scenario has been removed from the
implementation plan. This is a substantive scope reduction, not a relabeling of
destructive operations. No particular automated-review outcome is promised.

## Status

Phase 1's local harness is implemented. It uses actual localhost HTTP and
deterministic event ordering, with no third-party dependencies or API keys.
**It does not yet use A2A or its SDK. There are no protocol or SDK findings.**
See [PLAN.md](PLAN.md) for the revised research plan and remaining integration.

## Run

Requires Python 3.11+ and permission to bind a loopback socket.

```sh
make test
make poc
# Or: python3 -m testbed.runner --output results
```

Each invocation creates a new results batch. Each trial saves an approval,
before/approved/actual states, exact HTTP request and response bytes (base64),
a hash-linked event ledger, and a manifest with artifact hashes and source
fingerprint. `summary.json` and `summary.md` contain measured outcomes.

## Scenario and checks

An approval authorizes changing `item-001` from `available` to `reserved`.
A mutable HTTP source can instead return an update for `item-002`. The bounded
operation accepts only fixture record IDs and the two supported statuses.
Every trial begins from a fresh in-memory fixture.

| Case | Source behavior |
| --- | --- |
| baseline | Approved content throughout |
| before_check | Material change between approval and first read (W1) |
| after_check | Material change between first and second read (W2) |
| after_use | Material change after the operation; harmless control |
| cosmetic | JSON reformatted between reads; same approved fields |

Guards: `none`, `sha_at_check`, `sha_at_use`, `canonical_at_use`.
Canonical hashing covers the complete operation (`action`, `record_id`,
`status`); parsing rejects unknown fields, duplicate keys, and invalid values.
The bytes checked at use are the exact bytes parsed into the operation.

Approval signatures are local HMACs verified by the runner, a simulation of a
trusted approver rather than a distributed identity system. The ledger is
append-only through its API and hash-linked, but has no external trust anchor.
It detects edits against a trusted manifest; it cannot prevent wholesale
rewriting of the ledger and manifest together.

A blocked trial is **safe but incomplete**, not a successful update or a
material deviation. Material deviation is an operation inconsistent with the
approved operation. The final-state difference is recorded separately.
False blocks on cosmetic reissues are counted separately from detections.

## Boundaries

All network traffic is loopback, to a server created by the runner. There is no
arbitrary-URL input, shell tool, account administration, deletion, exploit
payload, or remote deployment. Results are written only into the selected
output directory. The current harness proves application-level behavior only.
Docker isolation, a pinned SDK, and an observe-only A2A tap remain planned.
