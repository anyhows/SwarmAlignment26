import base64
import json
import tempfile
import unittest
from pathlib import Path

from testbed.core import (APPROVED, FIXTURE, Ledger, approve, digest, encode,
                          fingerprints, parse, verify_approval, verify_ledger)
from testbed.runner import GUARDS, VARIANTS, run_trial


class CoreTests(unittest.TestCase):
    def test_cosmetic_and_material_digests(self):
        original = fingerprints(encode(APPROVED))
        cosmetic = fingerprints(json.dumps(APPROVED, indent=2).encode())
        self.assertNotEqual(original["raw_digest"], cosmetic["raw_digest"])
        self.assertEqual(original["canonical_digest"], cosmetic["canonical_digest"])
        material = fingerprints(encode({**APPROVED, "record_id": "item-002"}))
        self.assertNotEqual(original["canonical_digest"], material["canonical_digest"])

    def test_bounded_schema(self):
        invalid = [[], {**APPROVED, "record_id": "real-record"},
                   {**APPROVED, "action": "delete"}, {**APPROVED, "status": True},
                   {**APPROVED, "notes": "unexpected"}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse(encode(value))
        with self.assertRaises(ValueError):
            parse(b'{"action":"set_status","record_id":"item-001","status":"available","status":"reserved"}')

    def test_approval_authentication(self):
        approval = approve(encode(APPROVED), b"fixture-key")
        self.assertTrue(verify_approval(approval, b"fixture-key"))
        self.assertFalse(verify_approval(approval, b"wrong-key"))
        approval["fields"]["record_id"] = "item-002"
        self.assertFalse(verify_approval(approval, b"fixture-key"))

    def test_ledger_detects_edit_and_truncation(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "ledger.jsonl"
            ledger = Ledger(path, "test")
            ledger.append("approver", "approved", value=1)
            ledger.append("executor", "used", value=1)
            original = path.read_bytes()
            self.assertTrue(verify_ledger(path, ledger.previous, ledger.count))
            path.write_bytes(original.replace(b'"value":1', b'"value":2', 1))
            self.assertFalse(verify_ledger(path, ledger.previous, ledger.count))
            path.write_bytes(original.splitlines(keepends=True)[0])
            self.assertFalse(verify_ledger(path, ledger.previous, ledger.count))


class TrialTests(unittest.TestCase):
    def test_matrix_state_and_evidence(self):
        # Independent outcome oracle: list the exact vulnerable configurations.
        vulnerable = {("before_check", "none"), ("after_check", "none"),
                      ("after_check", "sha_at_check")}
        blocked = {("before_check", "sha_at_check"), ("before_check", "sha_at_use"),
                   ("before_check", "canonical_at_use"), ("after_check", "sha_at_use"),
                   ("after_check", "canonical_at_use"), ("cosmetic", "sha_at_use")}
        with tempfile.TemporaryDirectory() as root:
            for variant in VARIANTS:
                for guard in GUARDS:
                    with self.subTest(variant=variant, guard=guard):
                        row = run_trial(Path(root), variant, guard)
                        directory = Path(root) / f"{variant}--{guard}"
                        actual = json.loads((directory / "state_actual.json").read_text())
                        if (variant, guard) in vulnerable:
                            self.assertEqual(row["outcome"], "material_deviation")
                            self.assertEqual(actual, {"item-001": "available", "item-002": "reserved"})
                        elif (variant, guard) in blocked:
                            self.assertEqual(row["outcome"], "blocked")
                            self.assertEqual(actual, FIXTURE)
                            self.assertFalse(row["material_deviation"])
                        else:
                            self.assertEqual(row["outcome"], "completed")
                            self.assertEqual(actual, {"item-001": "reserved", "item-002": "available"})
                        for name, expected_hash in row["artifacts"].items():
                            self.assertEqual(digest((directory / name).read_bytes()), expected_hash)
                        self.assertTrue(verify_ledger(directory / "ledger.jsonl", row["ledger_head"], row["ledger_count"]))
                        events = [json.loads(line) for line in (directory / "ledger.jsonl").read_text().splitlines()]
                        mutations = [e for e in events if e["kind"] == "mutated"]
                        self.assertEqual([e["event_id"] for e in mutations], row["mutation_event_ids"])
                        captures = json.loads((directory / "wire.json").read_text())
                        fetched = [e for e in events if e["kind"].startswith("fetched_")]
                        self.assertEqual(len(captures), len(fetched))
                        for capture, event in zip(captures, fetched):
                            response = base64.b64decode(capture["response_base64"])
                            body = response.split(b"\r\n\r\n", 1)[1]
                            self.assertEqual(digest(body), event["details"]["raw_digest"])
                        self.assertEqual(row["protocol_classification"], "NOT_EVALUATED")


if __name__ == "__main__":
    unittest.main()
