"""A small stand-in for cake's /collect, for the browser tests of cake.js.

It serves cake.js with runtime values filled in (as cake does), the test site's shop (tests/site) and the test pages in
tests/browser/pages, and stores every upload exactly as it arrived (after gunzip) as one line of collect.ndjson. The
real collector is agentcake/collect.py, built from docs/collect-format.md; this one only keeps what arrives so the tests can
check it.

Every HTML page gets a Server-Timing token (cake;desc="tok-<n>") and a cookie, and served.ndjson records which page
got which token, so the tests can check that every page's token reached /collect and that no upload carried a cookie.
A page asked for with ?nocake=1 is served without the cake.js tag (to time pages with and without it).

    python3 -I tests/browser/collector.py --out DIR [--port 0]     prints {"port": N} on its first line

Python standard library only.
"""
import argparse
import gzip
import itertools
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

sys.path.insert(0, os.path.join(ROOT, "tests", "site"))
from agentcake import build_js  # noqa: E402  (the repository root is put on sys.path first)
import site_server  # noqa: E402  (tests/site: the shop's pages and files)

SITE_KEY = "test-site-key"
PAGES = os.path.join(HERE, "pages")
CAKE_TAG = re.compile(r'<script src="/cake\.js"[^>]*></script>\n?')
MAX_BODY = 50_000_000
SHUTDOWN_POLL_S = 0.01  # how often serve_forever looks for shutdown(): the harness stops the collector after each run


def read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


class Collector:
    def __init__(self, out_dir, runtime=None):
        self.out_dir = out_dir
        os.makedirs(out_dir, exist_ok=True)
        script = read(os.path.join(ROOT, "agentcake", "static", "cake.js"))
        self.script = build_js.with_runtime(script, runtime or {}).encode()
        self.tokens = itertools.count(1)
        self.lock = threading.Lock()

    def log(self, name, record):
        with self.lock:
            with open(os.path.join(self.out_dir, name), "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")

    def html(self, path, query):
        if path in site_server.PAGES:
            text = site_server.page(site_server.PAGES[path], "", SITE_KEY)  # cake.js from this collector
        elif path.startswith("/pages/") and path.endswith(".html") and "/" not in path[len("/pages/"):]:
            file = os.path.join(PAGES, path[len("/pages/"):])
            if not os.path.isfile(file):
                return None
            text = read(file)
        else:
            return None
        text = text.replace("{{SITE_KEY}}", SITE_KEY)
        if query.get("nocake") == ["1"]:
            text = CAKE_TAG.sub("", text)
        return text

    def handler(self):
        collector = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                return

            def reply(self, code, body=b"", ctype="text/plain", headers=None):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                if body and self.command != "HEAD":
                    self.wfile.write(body)

            def do_GET(self):
                url = urlsplit(self.path)
                if url.path == "/cake.js":
                    return self.reply(200, collector.script, "application/javascript")
                if site_server.asset(url.path):  # the shop's shop.js and shop.css
                    return self.reply(200, *site_server.asset(url.path))
                text = collector.html(url.path, parse_qs(url.query))
                if text is None:
                    return self.reply(404, b"not found")
                token = f"tok-{next(collector.tokens)}"
                collector.log("served.ndjson", {"at": time.time() * 1000, "path": self.path, "token": token})
                headers = {"Server-Timing": f'cake;desc="{token}"', "Set-Cookie": "visitor=test; Path=/; SameSite=Lax"}
                self.reply(200, text.encode(), "text/html; charset=utf-8", headers)

            def do_POST(self):
                url = urlsplit(self.path)
                if url.path != "/collect":
                    return self.reply(404, b"not found")
                wire = self.rfile.read(min(int(self.headers.get("Content-Length") or 0), MAX_BODY))
                gzipped = parse_qs(url.query).get("z") == ["gzip"]
                try:
                    batch = json.loads(gzip.decompress(wire) if gzipped else wire)
                except ValueError as e:
                    collector.log("rejected.ndjson", {"at": time.time() * 1000, "error": str(e), "bytes": len(wire)})
                    return self.reply(400, b"bad body")
                collector.log("collect.ndjson", {
                    "at": time.time() * 1000, "gz": gzipped, "wire_bytes": len(wire),
                    "cookie": "Cookie" in self.headers, "content_type": self.headers.get("Content-Type"),
                    "batch": batch})
                self.reply(204)

        return Handler


def serve(out_dir, port=0, runtime=None):
    """Starts the collector in a background thread; returns the server (server.server_address[1] is the port)."""
    server = ThreadingHTTPServer(("127.0.0.1", port), Collector(out_dir, runtime).handler())
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": SHUTDOWN_POLL_S}, daemon=True).start()
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description="Stand-in /collect for the cake.js browser tests.")
    parser.add_argument("--out", required=True, help="directory for collect.ndjson and served.ndjson")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    server = serve(args.out, args.port)
    print(json.dumps({"port": server.server_address[1]}), flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
