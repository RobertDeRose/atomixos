#!/usr/bin/env python3
"""Serve the assembled Pages site the way GitHub Pages does.

Docusaurus builds with trailingSlash: false, so a route like /atomixos/docs/building is the file building.html.
GitHub Pages resolves that; Python's plain http.server does not, and lists a directory instead when a route has both
an .html file and a directory of the same name. This handler tries <path>.html first, then <path>/index.html.
"""

import functools
import http.server
import os
import sys
from pathlib import Path


class PagesHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        resolved = super().translate_path(path)
        if not resolved.endswith(os.sep) and Path(resolved + ".html").is_file():
            return resolved + ".html"
        return resolved


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    root = sys.argv[2] if len(sys.argv) > 2 else "_site"
    handler = functools.partial(PagesHandler, directory=root)
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"Serving {root} at http://localhost:{port}/atomixos/")
        server.serve_forever()


if __name__ == "__main__":
    main()
