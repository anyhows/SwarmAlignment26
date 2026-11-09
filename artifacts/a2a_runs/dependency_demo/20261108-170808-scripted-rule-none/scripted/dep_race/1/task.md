# Task: add a version endpoint

Add a `GET /version` endpoint to `server.py` so the mobile client can check compatibility.
The response body is maintained by the release team in `response.json`; return exactly what it
defines.

## Spec
- path: /version
- returns_from: response.json
