# Task: add a version endpoint

Add a `GET /version` endpoint to `server.py` so the mobile client can check compatibility.
Owner: platform team. Please keep the response small; the client polls it on startup.

## Spec
- path: /version
- returns: {"service": "inventory", "version": "1.4.2"}
