"""Fixed-destination TCP relay; no HTTP routing, shell execution, or arbitrary targets."""
import select
import socket
import socketserver

class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            with socket.create_connection(('target', 80), timeout=5) as backend:
                self.request.settimeout(30)
                backend.settimeout(30)
                while True:
                    readable, _, _ = select.select([self.request, backend], [], [], 60)
                    for source in readable:
                        data = source.recv(65536)
                        if not data:
                            return
                        destination = backend if source is self.request else self.request
                        destination.sendall(data)
        except (OSError, ValueError):
            return

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

Server(('0.0.0.0', 8000), Handler).serve_forever()
