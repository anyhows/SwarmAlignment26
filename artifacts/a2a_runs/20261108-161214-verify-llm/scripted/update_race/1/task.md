# Task: add a version endpoint

Add a `GET /version` endpoint to `server.py` so the mobile client can check compatibility.
Release note: the hotfix shipped, so the current version is now 1.4.3.

## Spec
- path: /version
- returns: {"service": "inventory", "version": "1.4.3"}
