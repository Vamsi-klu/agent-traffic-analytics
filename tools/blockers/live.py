#!/usr/bin/env python3
"""check.py's question in a real browser: with uBO Lite in Chromium, does cake.js run and do its uploads arrive?

    CAKE_PLAYWRIGHT=<web/node_modules/playwright-core> python3 -I tools/blockers/live.py

Needs the internet (the latest uBO Lite release, its sha256 printed), node, playwright-core and Playwright's Chromium.
Everything runs in a new temporary folder, removed at the end: an AgentCake from this checkout in server mode (its own
CAKE_HOME, free ports of 127.0.0.1, path_prefix as SERVER.md sets it); a test site standing in for the website and
its load balancer, which sends AgentCake's paths to the public listener as SERVER.md's path rules do; and Chromium in
a fresh profile with uBO Lite's default rulesets (live.mjs), the site's host mapped to this computer. Chromium opens
SERVER.md's page script line on the site, and a page loading cake.js from the local page's address, as a site on
this computer does.

Exit code 0: uBO Lite filters (a canary path EasyPrivacy blocks is blocked), and on every page cake.js ran, no request
to AgentCake failed and AgentCake stored the page's uploads with its replay snapshot; 1: something of that did not
happen, and the lines say what; 2: it could not be checked (no extension, no browser, or uBO Lite did not filter).
"""
import hashlib
import io
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agentcake import config, paths, site_setup  # noqa: E402  (the repository is put on sys.path first)
from tools.blockers import check, targets  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = paths.MAIN_FILE
LOOPBACK = config.LOCAL_HOST
HEALTH = "/healthz"  # protocol: the public listener's health check (routes.py)
SNAPSHOT = "snapshot"  # protocol: the batch reason of the replay's first snapshot (docs/collect-format.md)
POLL_S = 0.2
OK, FAILED, UNDECIDED = 0, 1, 2


def free_port():
    with socket.socket() as s:
        s.bind((LOOPBACK, 0))
        return s.getsockname()[1]


def extension(conf, folder):
    """The latest uBO Lite for Chromium, unpacked into folder; (folder, release name, sha256 of the zip)."""
    live = conf["live"]
    release = json.loads(check.fetch(live["extension_releases"]))
    asset = next(a for a in release["assets"] if a["name"].endswith(live["extension_asset"]))
    body = check.fetch(asset["browser_download_url"])
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        z.extractall(folder)
    return folder, asset["name"], hashlib.sha256(body).hexdigest()


class Cake:
    """`agentcake serve` from this checkout in server mode, in its own CAKE_HOME on free ports."""

    def __init__(self, home, prefix, start_wait_s):
        self.env = dict(os.environ, CAKE_HOME=home)
        self.env.pop("CAKE_PORT", None)
        self.local_port, self.public_port = free_port(), free_port()
        for key, value in (("port", self.local_port), ("public_listen", f"{LOOPBACK}:{self.public_port}"),
                           ("path_prefix", prefix), ("lists_auto_update", "false")):  # its own downloads only
            subprocess.run([sys.executable, "-I", MAIN, "config", "set", key, str(value)], env=self.env, check=True,
                           capture_output=True)
        with open(os.path.join(home, os.path.basename(paths.config_file())), encoding="utf-8") as f:
            self.site_key = json.load(f)["site_key"]
        self.home, self.prefix = home, prefix
        self.process = subprocess.Popen([sys.executable, "-I", MAIN, "serve"], env=self.env,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.public = f"http://{LOOPBACK}:{self.public_port}"
        deadline = time.monotonic() + start_wait_s
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(self.public + prefix + HEALTH, timeout=start_wait_s).close()
                return
            except OSError:
                time.sleep(POLL_S)
        self.stop()
        raise OSError("AgentCake did not start")

    def stop(self):
        self.process.terminate()
        self.process.wait()

    def stored(self, page_url):
        """(batches, batches with the replay's snapshot, replay events) AgentCake kept for visits of this page."""
        db = sqlite3.connect(os.path.join(self.home, os.path.basename(paths.db_file())))
        try:
            row = db.execute("SELECT COUNT(*), SUM(b.why = ?), SUM(b.n_rrweb) FROM batches b JOIN sessions s"
                             " ON s.id = b.session_id WHERE s.url LIKE ?", (SNAPSHOT, page_url + "%")).fetchone()
        finally:
            db.close()
        return tuple(n or 0 for n in row)


def site_handler(cake, conf):
    """The test site: three pages, and AgentCake's paths sent to its public listener as a load balancer would."""
    prefix = cake.prefix
    forwarded = {prefix + path for _, path in targets.browser_routes(conf)}
    tag = site_setup.SNIPPET
    pages = {"/server.html": tag.format(src=prefix + site_setup.SCRIPT_PATH, site_key=cake.site_key),
             "/local.html": tag.format(src=f"http://{LOOPBACK}:{cake.local_port}{site_setup.SCRIPT_PATH}",
                                       site_key=cake.site_key),
             "/blank.html": ""}

    class Site(BaseHTTPRequestHandler):
        def answer(self, status, body=b"", kind="text/plain"):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def forward(self, body=None):
            req = urllib.request.Request(cake.public + self.path, data=body, method=self.command,
                                         headers={"Content-Type": self.headers.get("Content-Type", "text/plain")})
            try:
                with urllib.request.urlopen(req) as r:
                    self.answer(r.status, r.read(), r.headers.get("Content-Type", "text/plain"))
            except urllib.error.HTTPError as e:
                self.answer(e.code, e.read())

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in forwarded:
                return self.forward()
            if path in pages:
                html = f"<!doctype html><title>Shop</title>{pages[path]}<h1>Shop</h1><button>Buy</button>"
                return self.answer(200, html.encode(), "text/html; charset=utf-8")
            return self.answer(200, b"", "text/javascript")  # a canary or any other script: loads when not blocked

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            return self.forward(body) if self.path.split("?")[0] in forwarded else self.answer(204)

        def log_message(self, *args):
            pass
    return Site


def judge(answer, cake, site, prefix):
    """Lines saying what went wrong on each page ([] when nothing did)."""
    problems = []
    agentcake = (f"{site}{prefix}/", f"http://{LOOPBACK}:{cake.local_port}/")
    for page in answer["pages"]:
        url = f"{site}/{page['name']}.html"
        if page["cake"] != "object":
            problems.append(f"{page['name']}: cake.js did not run (window.cake is {page['cake']})")
        failures = Counter((f["url"], f["error"]) for f in page["failed"] if f["url"].startswith(agentcake))
        for (failed_url, error), times in failures.items():
            problems.append(f"{page['name']}: {failed_url} failed {times} time(s): {error}")
        batches, snapshots, events = cake.stored(url)
        if not (batches and snapshots and events):
            problems.append(f"{page['name']}: AgentCake stored {batches} uploads, {snapshots} with the snapshot")
        else:
            print(f"{page['name']}: cake.js ran; AgentCake stored {batches} uploads, {events} replay events")
    return problems


def run(folder):
    conf = targets.settings()
    live, host = conf["live"], conf["site"]["page_host"]
    try:
        ext, name, digest = extension(conf, os.path.join(folder, "extension"))
    except (OSError, StopIteration, zipfile.BadZipFile) as e:
        print(f"blockers live: no uBO Lite, nothing decided: {e}")
        return UNDECIDED
    print(f"uBO Lite: {name}, sha256 {digest}")
    prefix = targets.documented_prefix()
    try:
        cake = Cake(os.path.join(folder, "cake"), prefix, live["start_wait_s"])
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"blockers live: AgentCake did not start, nothing decided: {e}")
        return UNDECIDED
    server =ThreadingHTTPServer((LOOPBACK, 0), site_handler(cake, conf))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    site = f"http://{host}"
    job = {"extension": ext, "profile": os.path.join(folder, "profile"), "site_host": host,
           "site_port": server.server_address[1], "blank_page": f"{site}/blank.html",
           "canaries": [f"{site}/canary{path}" for path in live["canaries"]],
           "pages": [{"name": n, "url": f"{site}/{n}.html"} for n in ("server", "local")],
           **{k: live[k] for k in ("settle_ms", "linger_ms", "start_wait_s")}}
    job_file, answer_file = os.path.join(folder, "job.json"), os.path.join(folder, "answer.json")
    with open(job_file, "w", encoding="utf-8") as f:
        json.dump(job, f)
    try:
        subprocess.run(["node", os.path.join(HERE, "live.mjs"), job_file, answer_file], check=True)
        with open(answer_file, encoding="utf-8") as f:
            answer = json.load(f)
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"blockers live: the browser did not run, nothing decided: {e}")
        return UNDECIDED
    finally:
        server.shutdown()
        cake.stop()
    if not answer["filtering"]:
        print("blockers live: uBO Lite blocked no canary, so it did not filter: nothing decided")
        return UNDECIDED
    problems = judge(answer, cake, site, prefix)
    for line in problems:
        print(line)
    print(f"blockers live: {len(problems)} problem(s) with uBO Lite filtering")
    return FAILED if problems else OK


def main():
    folder = tempfile.mkdtemp(prefix="agentcake-blockers-live-")
    try:
        return run(folder)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
