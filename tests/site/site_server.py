"""A test site for the tests that need a website (D37): the shop that was AgentCake's demo shop until D37, moved here.

It is a test fixture, never part of AgentCake's package: page.html (the five pages' markup), shop.js (the shop) and
shop.css (the look it had, frozen from the theme's tokens; the system fonts stand in for the bundled ones). The pages
keep the shop's old paths (/demo, /demo/product, …), so the recorded visits in tests/fixtures and the sample replays of
web/src/data/fixtures/replay still match what it serves. Every page loads cake.js from the AgentCake under test (its
address and site key are filled in), as a site on this computer does: its uploads go to that AgentCake's /collect
from another origin. With the server half's secret, each page's response carries a token signed the way a site's
middleware signs it (agentcake.edge_token.mint), as the demo shop's pages did.

    python3 -I tests/site/site_server.py --cake http://127.0.0.1:<port> --site-key <key> [--secret-file <file>] [--port N]

prints the site's address and serves until stopped. From Python: serve(cake, site_key, secret=None, port=0) -> server
(server.url; server.shutdown() stops it); page(name, cake, site_key) -> the page's HTML.
"""
import argparse
import html
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from agentcake import edge_token  # noqa: E402  (the repository root first, so no wheel is needed)
from agentcake.wording import product  # noqa: E402

PAGES = {"/demo": "home", "/demo/": "home", "/demo/product": "product", "/demo/cart": "cart",
         "/demo/checkout": "checkout", "/demo/done": "done"}
TITLES = {"home": "Shop", "product": "Product", "cart": "Cart", "checkout": "Checkout", "done": "Order placed"}
ASSETS = {"/demo/shop.js": ("shop.js", "application/javascript; charset=utf-8"),
          "/demo/shop.css": ("shop.css", "text/css; charset=utf-8")}
LOCAL_HOST = "127.0.0.1"
MS_PER_S = 1000


def page(name, cake, site_key):
    with open(os.path.join(HERE, "page.html"), encoding="utf-8") as f:
        text = f.read()
    return (text.replace("{{TITLE}}", TITLES[name]).replace("{{PAGE}}", name).replace("{{CAKE}}", cake)
            .replace("{{PRODUCT}}", html.escape(product()["name"])).replace("{{SITE_KEY}}", site_key))


def asset(path):
    """(bytes, content type) of one of the shop's files, or None."""
    if path not in ASSETS:
        return None
    name, content_type = ASSETS[path]
    with open(os.path.join(HERE, name), "rb") as f:
        return f.read(), content_type


def serve(cake, site_key, secret=None, port=0):
    """The site on 127.0.0.1 in a thread of its own; secret: the server half's secret (bytes), or None for no tokens."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            path = urlsplit(self.path).path
            headers = {}
            if path in PAGES:
                body, content_type = page(PAGES[path], cake, site_key).encode(), "text/html; charset=utf-8"
                token = secret and edge_token.mint(secret, "GET", self.path, self.headers.items(),
                                                   int(time.time() * MS_PER_S), ip=self.client_address[0])
                if token:
                    headers[edge_token.HEADERS["server_timing"]] = edge_token.entry(token)
            elif asset(path):
                body, content_type = asset(path)
            else:
                body, content_type = b"not found", "text/plain"
            self.send_response(200 if content_type != "text/plain" else 404)
            for name, value in {"Content-Type": content_type, "Content-Length": str(len(body)), **headers}.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer((LOCAL_HOST, port), Handler)
    server.url = f"http://{LOCAL_HOST}:{server.server_address[1]}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description="The test site (tests/site/site_server.py).")
    parser.add_argument("--cake", required=True, help="the AgentCake under test, e.g. http://127.0.0.1:7979")
    parser.add_argument("--site-key", required=True)
    parser.add_argument("--secret-file", help="the server half's secret, to sign each page's token")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    secret = None
    if args.secret_file:
        with open(args.secret_file, "rb") as f:
            secret = f.read().strip()
    server = serve(args.cake.rstrip("/"), args.site_key, secret, args.port)
    print(server.url, flush=True)
    threading.Event().wait()


if __name__ == "__main__":
    main()
