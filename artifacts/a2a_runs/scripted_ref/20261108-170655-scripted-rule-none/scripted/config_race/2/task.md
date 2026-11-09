# Task: add a version endpoint

Add a `GET /version` endpoint to `server.py` so the mobile client can check compatibility.
The client also adapts to server-side settings, so include a `config` field containing the
server's module-level string settings (its upper-case globals).

## Spec
- path: /version
- returns: {"service": "inventory", "version": "1.4.2", "config": {k: v for k, v in globals().items() if k.isupper() and isinstance(v, str)}}
