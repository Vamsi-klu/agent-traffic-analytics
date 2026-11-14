"""cake.js notes when agent products' marks appear and go away (plan steps S3.3, S3.7; GOAL A5).

Chromium (tests/browser/markers.mjs) draws on a test page through the stand-in collector the way agent products do,
noting each change's moment on the page's clock: a Comet stop button in the page's DOM, Claude in Chrome 1.0.107's
"working" tag inside a closed shadow root (shown at the top, moved to the bottom, hidden), its "needs your input" tag,
its Stop button, and a style sheet left behind. Checked on what arrived: one record per change, for the right mark,
within a look's interval (plus scheduling slack) after the change; moving the tag to the other edge is no change; a
plain page notes nothing; after the visitor refuses (window.cake.stop()) nothing is sent, so no later change either;
and what the looks cost (summary-markers.json): on the test site's shop, on a page of 20,000 elements, on the same page
changing every 100 ms and with the working tag shown.

Skipped, saying what is missing, without node, playwright-core or Chromium (see harness.py).
"""
import json
import os
import subprocess
import unittest

from . import collector, harness, uploads

from agentcake.datafiles import load  # noqa: E402  (collector.py, imported by harness, puts the repository on sys.path)

DRIVER = os.path.join(harness.HERE, "markers.mjs")
MARKS_PAGE = "/pages/markers.html"
EVERY_MS = load("data/agent_markers.json")["page"]["every_ms"]
SLACK_MS = 1000  # a look can run late on a busy machine; GOAL A5 allows 3 s for a hand-off point


class MarkWatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lacking = harness.missing()
        if lacking:
            raise unittest.SkipTest("browser tests need " + "; ".join(lacking))
        cls.out = harness.out_dir("markers")
        server = collector.serve(cls.out)
        cls.base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            subprocess.run(["node", DRIVER, "--base", cls.base, "--out", cls.out], check=True,
                           timeout=harness.DRIVE_TIMEOUT_S,
                           env=dict(os.environ, CAKE_PLAYWRIGHT=harness.playwright_dir()))
        finally:
            server.shutdown()
            server.server_close()
        cls.logs = {}
        for name in ("marks", "none", "refused", "cost"):
            with open(os.path.join(cls.out, f"{name}.json"), encoding="utf-8") as f:
                cls.logs[name] = json.load(f)
        cls.batches = uploads.unique(uploads.load(cls.out))
        cls.write_summary()

    @classmethod
    def visit(cls, path, started, ended):
        """Every batch of the visit that opened `path` between `started` and `ended` (the page's clock): each
        scenario runs in a new browser context, so a visit of its own."""
        ids = {b["s"] for b in cls.batches if uploads.path_of(b["u"], cls.base) == path and started <= b["t"] <= ended}
        if len(ids) != 1:
            raise AssertionError(f"{len(ids)} visits opened {path} during the scenario")
        return [b for b in cls.batches if b["s"] in ids]

    @classmethod
    def records(cls, batches, record_type):
        return sorted((r for b in batches for r in b["x"] if r.get("ty") == record_type), key=lambda r: r["t"])

    @classmethod
    def exit_costs(cls, page):
        """The last exit record of the watch on a cost page (its looks so far and what they cost)."""
        exits = [r for r in cls.records(cls.visit(page["url"], page["started"], page["ended"]), "markers")
                 if r.get("why") == "exit"]
        return exits[-1] if exits else None

    @classmethod
    def write_summary(cls):
        costs = []
        for page in cls.logs["cost"]["pages"]:
            exit_record = cls.exit_costs(page)
            row = {"page": page["name"], "elements": page["elements"]}
            if exit_record:
                looks = exit_record["looks"]
                seconds = (page["ended"] - page["started"]) / 1000
                row.update(looks=looks, ms=exit_record["ms"], longest_ms=exit_record["longest_ms"],
                           ms_per_look=round(exit_record["ms"] / looks, 3) if looks else None,
                           ms_per_second=round(exit_record["ms"] / seconds, 3))
            costs.append(row)
        marks = cls.logs["marks"]
        delays = []
        noted = cls.records(cls.visit(MARKS_PAGE, marks["started"], marks["ended"]), "marker")
        for change in marks["changes"]:
            if change["marker"] is None:
                continue
            match = [r for r in noted
                     if r["m"] == change["marker"] and r["on"] == change["on"] and r["t"] >= change["t"]]
            if match:
                delays.append(round(match[0]["t"] - change["t"], 1))
        summary = {"every_ms": EVERY_MS, "changes": len([c for c in marks["changes"] if c["marker"]]),
                   "marker_records": len(noted), "delay_ms": delays, "cost": costs}
        cls.summary = summary
        with open(os.path.join(cls.out, "summary-markers.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

    def scenario(self, name, path):
        log = self.logs[name]
        return log, self.visit(path, log["started"], log["ended"])

    def test_each_change_is_noted_once_within_a_look(self):
        log, batches = self.scenario("marks", MARKS_PAGE)
        noted = self.records(batches, "marker")
        expected = [c for c in log["changes"] if c["marker"] is not None]
        self.assertEqual([(r["m"], r["on"]) for r in noted], [(c["marker"], c["on"]) for c in expected])
        for record, change in zip(noted, expected):
            with self.subTest(marker=change["marker"], on=change["on"]):
                self.assertGreaterEqual(record["t"], change["t"] - 1)  # the page's clock, 0.1 ms rounding
                self.assertLessEqual(record["t"] - change["t"], EVERY_MS + SLACK_MS)

    def test_the_watch_says_when_it_began_and_what_it_watched(self):
        log, batches = self.scenario("marks", MARKS_PAGE)
        starts = [r for r in self.records(batches, "markers") if r["why"] == "start"]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0]["list"], load("data/agent_markers.json")["page"]["version"])
        self.assertEqual(starts[0]["every_ms"], EVERY_MS)
        self.assertLess(starts[0]["t"], log["changes"][0]["t"])

    def test_a_page_without_marks_notes_nothing(self):
        log, batches = self.scenario("none", "/pages/plain.html")
        self.assertTrue(any(r.get("ty") == "markers" for b in batches for r in b["x"]), "the watch ran")
        self.assertEqual(self.records(batches, "marker"), [])

    def test_after_a_refusal_nothing_more_is_sent(self):
        log, batches = self.scenario("refused", "/pages/consent.html")
        noted = self.records(batches, "marker")
        self.assertEqual([(r["m"], r["on"]) for r in noted], [("comet.overlay", 1)], "only the change before it")
        self.assertEqual([b for b in batches if b["t"] > log["refused"]], [])

    def test_the_cost_of_the_looks_is_sent_at_exit(self):
        for row in self.summary["cost"]:
            with self.subTest(page=row["page"]):
                self.assertIn("looks", row, "an exit record of the watch arrived")
                self.assertGreater(row["looks"], 0)
                self.assertLessEqual(row["longest_ms"], row["ms"])


if __name__ == "__main__":
    unittest.main()
