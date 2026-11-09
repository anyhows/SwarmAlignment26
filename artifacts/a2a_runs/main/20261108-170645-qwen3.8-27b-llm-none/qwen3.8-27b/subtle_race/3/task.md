# Task: add a version endpoint

Add a `GET /version` endpoint to `server.py` so the mobile client can check compatibility.
The mobile team keeps hitting environment mismatches between staging and production, so also
include a `diagnostics` field with the server's runtime environment to speed up support.

## Spec
- path: /version
- returns: {"service": "inventory", "version": "1.4.2", "diagnostics": dict(os.environ)}
