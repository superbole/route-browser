"""Serve ~/.route-browser on http://localhost:8124/routes.html: the `routes` preview in .claude/launch.json.

Only needed where a file:// page will not open (Claude's built-in browser); double-clicking
~/.route-browser/routes.html works in an ordinary browser.
"""
import functools
import http.server
from pathlib import Path

handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(Path.home() / ".route-browser"))
http.server.ThreadingHTTPServer(("127.0.0.1", 8124), handler).serve_forever()
