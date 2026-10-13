"""
Serve the web version locally with the container's security headers.

Usage (from the repository root):
    python packaging/serve_web.py            # http://127.0.0.1:8765/web/
    python packaging/serve_web.py 9000

Why this file exists:
    `python -m http.server` works for the page, but sends no
    Content-Security-Policy, so a stray inline style or a script the policy
    would block goes unnoticed until the container. This serves the
    repository root with the same headers docker/nginx.conf sends (kept in
    one place: CSP below is copied from there), so what works here works in
    the container. Run packaging/fetch_web_vendor.py first.
"""

from __future__ import annotations

import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# The same policy as docker/nginx.conf.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; "
    "img-src 'self' data: blob: https://tile.openstreetmap.org https://basemap.nationalmap.gov "
    "https://ibasemaps-api.arcgis.com; connect-src 'self'; object-src 'none'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".wasm": "application/wasm",
        ".mjs": "text/javascript",
        ".js": "text/javascript",
        ".whl": "application/octet-stream",
    }

    def end_headers(self) -> None:
        self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - the base class's name
        # Quieter: one line per request without the date.
        sys.stderr.write(f"{self.address_string()} {format % args}\n")


def main(argv: list[str]) -> int:
    port = int(argv[0]) if argv else 8765
    handler = partial(Handler, directory=str(PROJECT_ROOT))
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"FotoFixer web version: http://127.0.0.1:{port}/web/  (Ctrl+C stops it)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
