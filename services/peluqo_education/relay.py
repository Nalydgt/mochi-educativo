"""TCP relay inside the existing VPN namespace; no public port publication."""
import os
import selectors
import socket
import socketserver


class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.create_connection(
            (os.environ.get("TARGET_HOST", "peluqo-worker"), 8000), timeout=10
        ) as upstream:
            self.request.setblocking(False)
            upstream.setblocking(False)
            with selectors.DefaultSelector() as selector:
                selector.register(self.request, selectors.EVENT_READ, upstream)
                selector.register(upstream, selectors.EVENT_READ, self.request)
                while True:
                    ready = selector.select(600)
                    if not ready:
                        return
                    for key, _ in ready:
                        try:
                            data = key.fileobj.recv(65536)
                        except (ConnectionError, OSError):
                            return
                        if not data:
                            return
                        # Bounded messages, backpressure handled by a blocking
                        # send on this dedicated connection thread only.
                        target = key.data
                        target.setblocking(True)
                        try:
                            target.sendall(data)
                        except (ConnectionError, OSError):
                            return
                        finally:
                            target.setblocking(False)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server(("0.0.0.0", 8778), Relay) as server:
        server.serve_forever()
