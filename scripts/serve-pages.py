#!/usr/bin/env python3
"""Serve the assembled Pages site the way GitHub Pages does.

Docusaurus builds with trailingSlash: false, so a route like /atomixos/docs/building is the file building.html.
GitHub Pages resolves that; Python's plain http.server does not, and lists a directory instead when a route has both
an .html file and a directory of the same name. This handler tries <path>.html first, then <path>/index.html.

Given a live directory, the handler serves the product page from it instead of the assembled copy, so edits to the
product page show on the next browser refresh without a rebuild. Responses are never cached for the same reason.
"""

import functools
import http.server
import os
import sys
from pathlib import Path


# Pages serves the site from /atomixos/, and site:build assembles it under the same path.
SITE_PATH = "atomixos"


class PagesHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, live=None, **kwargs):
        self.live = live
        super().__init__(*args, **kwargs)

    def translate_path(self, path):
        resolved = super().translate_path(path)
        live = self.live_path(resolved)
        if live is not None:
            return live
        if not resolved.endswith(os.sep) and Path(resolved + ".html").is_file():
            return resolved + ".html"
        return resolved

    def live_path(self, resolved):
        """Map a path in the assembled site to the live product page, or return None to serve the assembled copy."""
        if self.live is None:
            return None
        try:
            rel = Path(resolved).relative_to(Path(self.directory, SITE_PATH))
        except ValueError:
            return None
        if not rel.parts:
            return str(self.live) + os.sep
        if rel.parts[0] == "docs":
            return None
        candidate = self.live / rel
        return str(candidate) if candidate.is_file() else None

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    root = sys.argv[2] if len(sys.argv) > 2 else "_site"
    live = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else None
    handler = functools.partial(PagesHandler, directory=root, live=live)
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"Serving {root} at http://localhost:{port}/{SITE_PATH}/")
        if live is not None:
            print(f"Serving the product page live from {live}; refresh the browser to see edits")
        server.serve_forever()


if __name__ == "__main__":
    main()
