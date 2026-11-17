"""cake.js in a real browser: everything a visit does reaches /collect.

Chromium, driven by tests/browser/drive.mjs, visits the test site's shop (tests/site) through the stand-in collector: Playwright's direct
clicks and fills 3 times, a humanlike visitor (curved mouse paths, pauses, wheel, typing) 3 times, and 4 visits of 24
pages each left 0.3–0.8 s after it opened (cake-plan.days item 2). Checked on what arrived: every page in order, every
page's full snapshot, every click both raw and in the replay (except on elements the replay must not show), every
page's server-half token, the v1 header on every batch, batches numbered without gaps, big batches gzipped, and no
cookie on any upload.

Skipped, saying what is missing, without node, playwright-core or Chromium (see harness.py).
"""
import json
import os
import re
import unittest

from . import collector, harness, uploads

HEX_ID = re.compile(r"^[0-9a-f]{32}$")
REASONS = {"start", "snapshot", "env", "probes", "timer", "size", "exit"}
PER_PAGE = ("env", "auto", "cdp", "probes", "botd", "botscent", "tasks")
PLAN = "direct:3,humanlike:3,bounce:4"


class Capture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lacking = harness.missing()
        if lacking:
            raise unittest.SkipTest("browser tests need " + "; ".join(lacking))
        cls.out = harness.out_dir("capture")
        cls.base, cls.logs = harness.run(PLAN, cls.out)
        cls.entries = uploads.load(cls.out)
        cls.batches = uploads.unique(cls.entries)
        cls.views = uploads.page_views(cls.batches)
        cls.visits = uploads.visits(cls.views)
        cls.runs = {name: uploads.visit_in(cls.visits, log["started"], log["ended"]) for name, log in cls.logs.items()}
        cls.write_summary()

    @classmethod
    def write_summary(cls):
        summary = {"uploads": len(cls.entries), "batches": len(cls.batches), "page_views": len(cls.views),
                   "visits": len(cls.visits), "gzipped_uploads": sum(e["gz"] for e in cls.entries),
                   "wire_bytes": sum(e["wire_bytes"] for e in cls.entries), "runs": {}}
        for name, log in cls.logs.items():
            visit = cls.runs[name] or []
            summary["runs"][name] = {
                "pages_opened": len(log["pages"]), "page_views_arrived": len(visit),
                "with_full_snapshot": sum(1 for v in visit if uploads.full_snapshots(v)),
                "clicks_made": len(log["clicks"]),
                "raw_clicks_arrived": sum(len([r for r in uploads.records(v, "r", "click") if r["tr"]]) for v in visit),
                "replay_clicks_arrived": sum(len(uploads.replay_clicks(v)) for v in visit)}
        with open(os.path.join(cls.out, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

    def test_every_run_is_one_visit_with_its_pages_in_order(self):
        self.assertEqual(len(self.logs), 10)
        for name, log in self.logs.items():
            with self.subTest(run=name):
                visit = self.runs[name]
                self.assertIsNotNone(visit, "no visit, or more than one, started during this run")
                opened = [uploads.path_of(v["urls"][0], self.base) for v in visit]
                self.assertEqual(opened, log["pages"])

    def test_every_page_view_has_its_page_record_and_full_snapshot(self):
        for view in self.views.values():
            with self.subTest(page=view["urls"][0]):
                self.assertIsNotNone(view["page"])
                self.assertTrue(uploads.full_snapshots(view))
                self.assertEqual(view["e"][0]["type"], uploads.RRWEB_META)

    def test_quick_visits_lose_no_page(self):
        for name in (n for n in self.logs if n.startswith("bounce")):
            with self.subTest(run=name):
                visit = self.runs[name]
                self.assertEqual(len(visit), len(self.logs[name]["pages"]))
                self.assertEqual(len(visit), 24)
                self.assertTrue(all(v["page"] and uploads.full_snapshots(v) for v in visit))

    def test_every_click_arrives_raw_and_in_the_replay(self):
        for name in (n for n in self.logs if not n.startswith("bounce")):
            visit = self.runs[name]
            for number, view in enumerate(visit, 1):
                made = [c for c in self.logs[name]["clicks"] if c["page"] == number]
                with self.subTest(run=name, page=number):
                    raw = [r for r in uploads.records(view, "r", "click") if r["tr"] == 1]
                    self.assertGreaterEqual(len(raw), len(made))
                    # Elements cake.js must not record (card fields) are not in the replay at all.
                    shown = [c for c in made if not c["blocked"]]
                    self.assertGreaterEqual(len(uploads.replay_clicks(view)), len(shown))

    def test_every_page_token_arrives(self):
        served = {line["token"] for line in uploads.read_ndjson(os.path.join(self.out, "served.ndjson"))}
        received = set().union(*(view["tokens"] for view in self.views.values()))
        self.assertTrue(served)
        self.assertEqual(served - received, set())

    def test_batches_of_a_page_view_are_numbered_without_gaps(self):
        for view in self.views.values():
            with self.subTest(page=view["urls"][0]):
                self.assertEqual(view["seqs"], list(range(len(view["seqs"]))))

    def test_every_batch_has_the_v1_header(self):
        for batch in self.batches:
            self.assertEqual(batch["v"], 1)
            self.assertEqual(batch["k"], collector.SITE_KEY)
            self.assertRegex(batch["s"], HEX_ID)
            self.assertRegex(batch["pv"], HEX_ID)
            self.assertIsInstance(batch["seq"], int)
            self.assertIsInstance(batch["t"], (int, float))
            self.assertTrue(batch["u"].startswith(self.base))
            self.assertIsInstance(batch["ua"], str)
            self.assertIs(batch["wd"], True)  # Playwright's Chromium reports navigator.webdriver
            self.assertIn(batch["why"], REASONS)
            for stream in ("e", "r", "x"):
                self.assertIsInstance(batch[stream], list)

    def test_uploads_carry_no_cookie_and_are_plain_text(self):
        self.assertFalse(any(entry["cookie"] for entry in self.entries))
        self.assertEqual({entry["content_type"] for entry in self.entries}, {"text/plain"})

    def test_big_batches_travel_gzipped_and_every_upload_is_readable(self):
        self.assertTrue(any(entry["gz"] for entry in self.entries))
        self.assertEqual(uploads.read_ndjson(os.path.join(self.out, "rejected.ndjson")), [])

    def test_the_frame_checks_run_once_per_visit(self):
        for name in self.logs:
            with self.subTest(run=name):
                frames = [r for view in self.runs[name] for r in uploads.records(view, "x", "frames")]
                self.assertEqual(len(frames), 1)

    def test_the_devtools_probe_runs_in_a_frame_of_its_own_and_sees_playwright(self):
        # Playwright drives every run with the DevTools protocol's Runtime domain on, which serialises the console
        # calls of every frame of the page: the logged-error probe, run in a frame no page script touched, sees it.
        probed = 0
        for name in self.logs:
            for view in self.runs[name]:
                for record in uploads.records(view, "x", "cdp"):
                    probed += 1
                    with self.subTest(run=name, page=view["urls"][0]):
                        leak = record["runtimeEnableLeak"]
                        self.assertEqual(leak["console"], "frame")
                        self.assertGreater(leak["prepareStackTraceCount"], 0)
        self.assertGreater(probed, 0)

    def test_pages_kept_open_report_environment_and_detectors(self):
        # The detectors run after load, one idle task each: the humanlike visitor stays on a page long enough.
        for name in (n for n in self.logs if n.startswith("humanlike")):
            for view in self.runs[name]:
                with self.subTest(run=name, page=view["urls"][0]):
                    kinds = {r.get("ty") for r in view["x"]}
                    self.assertEqual(set(PER_PAGE) - kinds, set())


if __name__ == "__main__":
    unittest.main()
