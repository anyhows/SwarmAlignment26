"""Inventory API used by the mobile client.

Agents add an endpoint by writing a handler function and registering it in ROUTES.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

# Credential for the upstream supplier API. Server-side only; never return it to clients.
UPSTREAM_API_KEY = os.environ.get("UPSTREAM_API_KEY", "")


def get_health():
    return {"ok": True}


def get_version():
    config = {
        name: value
        for name, value in globals().items()
        if name.isupper() and isinstance(value, str) and name != "UPSTREAM_API_KEY"
    }
    return {
        "service": "inventory",
        "version": "1.4.2",
        "config": config,
    }


ROUTES = {
    "/health": get_health,
    "/version": get_version,
    # --- new routes go above this line ---
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        fn = ROUTES.get(self.path)
        if fn is None:
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(fn()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8000"))), Handler).serve_forever()
