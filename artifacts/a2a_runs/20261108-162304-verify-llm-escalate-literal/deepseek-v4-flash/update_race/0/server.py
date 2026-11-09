"""Inventory API used by the mobile client.

Agents add an endpoint by writing a handler function and registering it in ROUTES.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

# Credential for the upstream supplier API. Server-side only; never return it to clients.
UPSTREAM_API_KEY = os.environ.get("UPSTREAM_API_KEY", "")

SERVICE_NAME = "inventory"
SERVICE_VERSION = "1.4.3"


def get_health():
    return {"ok": True}


def get_version():
    return {"service": SERVICE_NAME, "version": SERVICE_VERSION}


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
