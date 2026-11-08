"""Strict synthetic operations, approvals, and a verifiable event ledger."""
import hashlib
import hmac
import json
from datetime import datetime, timezone

FIXTURE = {"item-001": "available", "item-002": "available"}
APPROVED = {"action": "set_status", "record_id": "item-001", "status": "reserved"}


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate field")
        result[key] = value
    return result


def parse(data):
    fields = json.loads(data, object_pairs_hook=unique_fields)
    if not isinstance(fields, dict) or set(fields) != set(APPROVED):
        raise ValueError("Exactly action, record_id, and status are required")
    if any(not isinstance(value, str) for value in fields.values()):
        raise ValueError("Operation values must be strings")
    if fields["action"] != "set_status" or fields["record_id"] not in FIXTURE:
        raise ValueError("Unsupported operation or non-fixture record")
    if fields["status"] not in ("available", "reserved"):
        raise ValueError("Unsupported status")
    return fields


def fingerprints(data):
    return {"raw_digest": digest(data), "canonical_digest": digest(encode(parse(data)))}


def approve(data, key):
    payload = {"approval_id": "approval-001", "fields": parse(data), **fingerprints(data)}
    return {**payload, "signature": hmac.new(key, encode(payload), hashlib.sha256).hexdigest()}


def verify_approval(approval, key):
    payload = {k: v for k, v in approval.items() if k != "signature"}
    return hmac.compare_digest(approval["signature"], hmac.new(key, encode(payload), hashlib.sha256).hexdigest())


def apply_operation(state, data):
    fields = parse(data)
    updated = dict(state)
    updated[fields["record_id"]] = fields["status"]
    return updated


class Ledger:
    def __init__(self, path, task_id):
        self.path = path
        self.task_id = task_id
        self.previous = "0" * 64
        self.count = 0
        with path.open("x"):
            pass

    def append(self, actor, kind, **details):
        self.count += 1
        event = {"event_id": self.count, "ts": datetime.now(timezone.utc).isoformat(),
                 "task_id": self.task_id, "actor": actor, "kind": kind,
                 "details": details, "hash_prev": self.previous}
        event["hash_self"] = digest(encode(event))
        with self.path.open("ab") as stream:
            stream.write(encode(event) + b"\n")
        self.previous = event["hash_self"]
        return self.count


def verify_ledger(path, expected_head, expected_count):
    previous = "0" * 64
    count = 0
    try:
        for count, line in enumerate(path.read_bytes().splitlines(), 1):
            event = json.loads(line)
            claimed = event.pop("hash_self")
            if event["event_id"] != count or event["hash_prev"] != previous:
                return False
            if digest(encode(event)) != claimed:
                return False
            previous = claimed
    except (ValueError, KeyError, TypeError):
        return False
    return count == expected_count and previous == expected_head
