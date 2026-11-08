"""A local-only mutable HTTP fixture with exact client-side byte capture."""
import base64
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class ContentHost:
    def __init__(self, data):
        self.data = data
        host = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = host.data
                if self.path != "/request.json":
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.captures = []

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    @property
    def uri(self):
        return f"http://127.0.0.1:{self.server.server_port}/request.json"

    def fetch(self, phase):
        request = (f"GET /request.json HTTP/1.0\r\nHost: 127.0.0.1:{self.server.server_port}\r\n"
                   "Connection: close\r\n\r\n").encode()
        with socket.create_connection(self.server.server_address, timeout=5) as client:
            client.sendall(request)
            chunks = []
            while chunk := client.recv(65536):
                chunks.append(chunk)
        response = b"".join(chunks)
        headers, body = response.split(b"\r\n\r\n", 1)
        if not headers.startswith(b"HTTP/1.0 200 "):
            raise RuntimeError("Unexpected fixture HTTP response")
        self.captures.append({"phase": phase, "uri": self.uri,
                              "request_base64": base64.b64encode(request).decode(),
                              "response_base64": base64.b64encode(response).decode()})
        return body
