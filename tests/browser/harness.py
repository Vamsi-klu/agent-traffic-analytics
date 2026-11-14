"""Running the browser side of the cake.js tests (plan steps S1.3, S1.4): the collector plus drive.mjs.

What is needed: node; playwright-core (CAKE_PLAYWRIGHT, or web/node_modules/playwright-core of this checkout); Chromium
(CAKE_CHROME, or Playwright's cache). missing() says what is not there, so a test can skip and say why.
CAKE_EVIDENCE_DIR keeps the uploads and drive logs there instead of in a temporary directory.
"""
import json
import os
import shutil
import subprocess
import tempfile

from . import collector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DRIVE = os.path.join(HERE, "drive.mjs")
DRIVE_TIMEOUT_S = 900


def playwright_dir():
    return os.environ.get("CAKE_PLAYWRIGHT") or os.path.join(ROOT, "web", "node_modules", "playwright-core")


def missing():
    """What the browser tests need and this machine lacks (empty when they can run)."""
    lacking = []
    if not shutil.which("node"):
        lacking.append("node")
    if not os.path.isdir(playwright_dir()):
        lacking.append(f"playwright-core at {playwright_dir()} (set CAKE_PLAYWRIGHT to its folder)")
    return lacking


def out_dir(name):
    keep = os.environ.get("CAKE_EVIDENCE_DIR")
    if keep:
        path = os.path.join(keep, name)
        os.makedirs(path, exist_ok=True)
        return path
    return tempfile.mkdtemp(prefix=f"cakejs-{name}-")


def blocked_selector():
    """The elements cake.js must not record at all (the replay shows no interaction with them)."""
    with open(os.path.join(ROOT, "agentcake", "data", "privacy.json"), encoding="utf-8") as f:
        return json.load(f)["page"]["private_selector"]


def drive(base, out, plan, extra=()):
    """Drives the browser through plan ("direct:3,bounce:4") against base; returns the logs drive.mjs wrote:
    {"<scenario>-<run>": log}. extra: more drive.mjs arguments (["--canary", text])."""
    command = ["node", DRIVE, "--base", base, "--out", out, "--plan", plan, "--blocked", blocked_selector(), *extra]
    subprocess.run(command, check=True, timeout=DRIVE_TIMEOUT_S, env=dict(os.environ, CAKE_PLAYWRIGHT=playwright_dir()))
    logs = {}
    for name in sorted(os.listdir(out)):
        if name.endswith(".json") and name != "timing.json" and not name.startswith("summary"):
            with open(os.path.join(out, name), encoding="utf-8") as f:
                logs[name[: -len(".json")]] = json.load(f)
    return logs


def run(plan, out, runtime=None, extra=()):
    """Starts the stand-in collector, drives the browser through plan, stops the collector.
    Returns the collector's base URL and the drive logs."""
    server = collector.serve(out, runtime=runtime)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        return base, drive(base, out, plan, extra)
    finally:
        server.shutdown()
        server.server_close()
