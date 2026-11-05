# Copyright (c) 2026 agentctl contributors.
"""A loopback-only HTTP server with independent bodies and a request record."""

import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Body:
    """One exact body and optional deliberately different Content-Length."""

    path: str
    content: bytes
    length: str | None


@dataclass(frozen=True, slots=True)
class Server:
    """An owned endpoint and the independently recorded request paths."""

    url: str
    log: Path

    @property
    def requests(self) -> tuple[str, ...]:
        """Read only requests the HTTP handler actually received."""
        return tuple(self.log.read_text(encoding="utf-8").splitlines())


@contextmanager
def serve(
    directory: Path,
    bodies: tuple[Body, ...],
    before_body: Callable[[], None] = lambda: None,
) -> Generator[Server]:
    """Serve fixed bytes on an ephemeral private port and reap the server thread."""
    directory.mkdir(parents=True)
    log = directory / "requests.txt"
    log.write_text("", encoding="utf-8")

    class Handler(BaseHTTPRequestHandler):
        """Expose only the fixed test bodies without filesystem routing."""

        def do_GET(self) -> None:
            """Record a request before delivering its independently chosen bytes."""
            with log.open("a", encoding="utf-8") as stream:
                stream.write(self.path + "\n")
            body = next((item for item in bodies if item.path == self.path), None)
            if body is None:
                self.send_error(404)
            else:
                self.send_response(200)
                if body.length is not None:
                    self.send_header("Content-Length", body.length)
                self.end_headers()
                before_body()
                self.wfile.write(body.content)
                self.close_connection = True

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        try:
            yield Server(f"http://127.0.0.1:{server.server_port}", log)
        finally:
            server.shutdown()
            worker.join(timeout=5)
            assert not worker.is_alive()
