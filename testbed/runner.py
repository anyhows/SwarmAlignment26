"""Deterministically run the first local consistency matrix."""
import argparse
import json
import platform
import secrets
from pathlib import Path
from uuid import uuid4

from .core import (APPROVED, FIXTURE, Ledger, apply_operation, approve, digest,
                   encode, fingerprints, parse, verify_approval, verify_ledger)
from .transport import ContentHost

VARIANTS = ("baseline", "before_check", "after_check", "after_use", "cosmetic")
GUARDS = ("none", "sha_at_check", "sha_at_use", "canonical_at_use")


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def expected_outcome(variant, guard):
    if variant == "before_check":
        return "material_deviation" if guard == "none" else "blocked"
    if variant == "after_check":
        return "material_deviation" if guard in ("none", "sha_at_check") else "blocked"
    if variant == "cosmetic" and guard == "sha_at_use":
        return "blocked"
    return "completed"


def run_trial(root, variant, guard):
    if variant not in VARIANTS or guard not in GUARDS:
        raise ValueError("Unknown configuration")
    directory = root / f"{variant}--{guard}"
    directory.mkdir(parents=True, exist_ok=False)
    ledger = Ledger(directory / "ledger.jsonl", directory.name)
    original = encode(APPROVED)
    changed = encode({**APPROVED, "record_id": "item-002"})
    key = secrets.token_bytes(32)
    approval = approve(original, key)
    if not verify_approval(approval, key):
        raise RuntimeError("Approval failed authentication")
    before = dict(FIXTURE)
    expected = apply_operation(before, original)
    actual = dict(before)
    ledger.append("runner", "fixture_verified", state=before)
    ledger.append("approver", "approved", approval=approval)
    mutations = []
    decisions = []
    operation = None
    blocked = False

    with ContentHost(original) as host:
        def mutate(window, body):
            old = fingerprints(host.data)
            host.data = body
            mutations.append(ledger.append("host", "mutated", window=window,
                                            before=old, after=fingerprints(body)))

        def check(phase, body):
            observed = fingerprints(body)
            ledger.append("executor", f"fetched_{phase}", uri=host.uri,
                          fields=parse(body), **observed)
            field = None
            if (guard == "sha_at_check" and phase == "check") or (guard == "sha_at_use" and phase == "use"):
                field = "raw_digest"
            elif guard == "canonical_at_use" and phase == "use":
                field = "canonical_digest"
            allowed = field is None or approval[field] == observed[field]
            decision = {"phase": phase, "guard": guard, "decision": "ALLOW" if allowed else "BLOCK",
                        "reason": "no check at this hook" if field is None else f"compare {field}",
                        "approved": {k: approval[k] for k in ("raw_digest", "canonical_digest")},
                        "observed": observed}
            decisions.append(decision)
            ledger.append("executor", "guard_decision", **decision)
            return allowed

        if variant == "before_check":
            mutate("W1", changed)
        blocked = not check("check", host.fetch("check"))
        if not blocked:
            if variant == "after_check":
                mutate("W2", changed)
            elif variant == "cosmetic":
                mutate("W2", json.dumps(APPROVED, indent=4).encode() + b"\n")
            used = host.fetch("use")
            blocked = not check("use", used)
            if not blocked:
                operation = parse(used)
                ledger.append("executor", "tool_call", fields=operation)
                actual = apply_operation(actual, used)
                ledger.append("executor", "state_change", state=actual)
            if variant == "after_use":
                mutate("after_use", changed)
        captures = host.captures

    # A blocked operation is incomplete, but is not an inconsistent operation.
    deviation = operation is not None and operation != approval["fields"]
    outcome = "blocked" if blocked else "material_deviation" if deviation else "completed"
    ledger.append("runner", "verified", outcome=outcome, actual=actual, expected=expected)
    for name, value in {"approval": approval, "state_before": before, "state_expected": expected,
                        "state_actual": actual, "wire": captures, "decisions": decisions}.items():
        write_json(directory / f"{name}.json", value)
    source = {path.name: digest(path.read_bytes()) for path in sorted(Path(__file__).parent.glob("*.py"))}
    manifest = {"schema_version": 1, "variant": variant, "guard": guard,
                "mode": "scripted_local_http", "sdk_commit": None, "image_digest": None,
                "protocol_classification": "NOT_EVALUATED", "python": platform.python_version(),
                "source_hashes": source, "seed": None, "schedule": "explicit_event_boundaries",
                "label": "material_change" if variant in ("before_check", "after_check") else "benign",
                "mutation_event_ids": mutations, "outcome": outcome,
                "material_deviation": deviation, "state_matches_approval": actual == expected,
                "expected_outcome": expected_outcome(variant, guard),
                "expectation_met": outcome == expected_outcome(variant, guard),
                "ledger_head": ledger.previous, "ledger_count": ledger.count,
                "approval_verified": True,
                "artifacts": {p.name: digest(p.read_bytes()) for p in sorted(directory.iterdir())}}
    if not verify_ledger(ledger.path, ledger.previous, ledger.count):
        raise RuntimeError("Ledger verification failed")
    write_json(directory / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results"))
    args = parser.parse_args()
    batch = args.output / f"batch-{uuid4().hex}"
    rows = [run_trial(batch, variant, guard) for variant in VARIANTS for guard in GUARDS]
    write_json(batch / "summary.json", rows)
    lines = ["| Variant | Guard | Expected | Actual | Pass |",
             "| --- | --- | --- | --- | --- |"]
    for row in rows:
        lines.append(f"| {row['variant']} | {row['guard']} | {row['expected_outcome']} | {row['outcome']} | {row['expectation_met']} |")
    summary = "\n".join(lines) + "\n"
    (batch / "summary.md").write_text(summary)
    print(summary)
    print(f"Evidence: {batch.resolve()}")
    if not all(row["expectation_met"] for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
