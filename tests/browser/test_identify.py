"""window.cake.identify() and window.cake.reset() in Chromium (tests/browser/identify.mjs) against the stand-in collector.

After identify(id) the browser keeps SHA-256(site key + ":" + id) with its visitor id and every batch from then on
carries it, on the next page view from its first batch; another profile signing in with the same id sends the same
hash with another visitor id; a call queued before cake.js loaded works too. The id itself is in no request any page
made (address, headers or body). reset() keeps a new visitor id without the hash and begins a new session (its first
record says reset), whose batches carry no hash; stop() deletes the visitor entry. With data-consent="required",
identify() before Accept stores and sends nothing, and the hash goes once the visitor agrees.

Skipped, saying what is missing, without node, playwright-core or Chromium (see harness.py).
"""
import hashlib
import json
import os
import subprocess
import unittest

from . import collector, harness, uploads

DRIVER = os.path.join(harness.HERE, "identify.mjs")
SITE_ID = "raw-visitor-id-Q7K2"  # the site's own id for the visitor: it must never leave the browser
HASH = hashlib.sha256(f"{collector.SITE_KEY}:{SITE_ID}".encode()).hexdigest()


class Identify(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lacking = harness.missing()
        if lacking:
            raise unittest.SkipTest("browser tests need " + "; ".join(lacking))
        cls.out = harness.out_dir("identify")
        server = collector.serve(cls.out)
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            subprocess.run(["node", DRIVER, "--base", base, "--out", cls.out, "--id", SITE_ID], check=True,
                           timeout=harness.DRIVE_TIMEOUT_S, env=dict(os.environ, CAKE_PLAYWRIGHT=harness.playwright_dir()))
        finally:
            server.shutdown()
            server.server_close()
        cls.logs = {}
        for name in ("signin", "other", "queued", "consent"):
            with open(os.path.join(cls.out, f"{name}.json"), encoding="utf-8") as f:
                cls.logs[name] = json.load(f)
        cls.batches = uploads.unique(uploads.load(cls.out))
        with open(os.path.join(cls.out, "collect.ndjson"), encoding="utf-8") as f:
            cls.wire = f.read()
        with open(os.path.join(cls.out, "requests.ndjson"), encoding="utf-8") as f:
            cls.requests = f.read()

    def visitor(self, scenario, step):
        return self.logs[scenario][step]["visitor"]

    def batches_of(self, visitor_id):
        return [batch for batch in self.batches if batch.get("vid") == visitor_id]

    def test_identify_keeps_the_hash_with_the_visitor_id(self):
        before, after = self.visitor("signin", "before"), self.visitor("signin", "signedIn")
        self.assertNotIn("h", before)
        self.assertEqual((after["id"], after["h"]), (before["id"], HASH))

    def test_batches_carry_the_hash_once_identified(self):
        sent = {batch.get("idh") for batch in self.batches_of(self.visitor("signin", "before")["id"])}
        self.assertEqual(sent, {None, HASH}, "before and after identify()")

    def test_the_next_page_view_carries_the_hash_from_its_first_batch(self):
        second = [batch for batch in self.batches_of(self.visitor("signin", "before")["id"])
                  if batch["u"].endswith("?page=2")]
        self.assertTrue(second)
        self.assertEqual({batch.get("idh") for batch in second}, {HASH})
        self.assertIn(0, [batch["seq"] for batch in second])

    def test_another_profile_with_the_same_id_sends_the_same_hash_with_another_visitor_id(self):
        mine, theirs = self.visitor("signin", "signedIn"), self.visitor("other", "signedIn")
        self.assertEqual(theirs["h"], HASH)
        self.assertNotEqual(theirs["id"], mine["id"])
        self.assertIn(HASH, {batch.get("idh") for batch in self.batches_of(theirs["id"])})

    def test_a_call_queued_before_cake_js_loaded_identifies_too(self):
        queued = self.visitor("queued", "signedIn")
        self.assertEqual(queued["h"], HASH)
        self.assertEqual({batch.get("idh") for batch in self.batches_of(queued["id"])} - {None}, {HASH})

    def test_the_id_is_in_no_request(self):
        self.assertIn(HASH, self.wire)
        self.assertNotIn(SITE_ID, self.wire)
        self.assertNotIn(SITE_ID, self.requests)
        self.assertNotIn(SITE_ID.lower(), self.requests.lower())

    def test_reset_keeps_a_new_visitor_id_without_the_hash_and_begins_a_new_session(self):
        before, after = self.logs["signin"]["secondPage"], self.logs["signin"]["afterReset"]
        self.assertNotEqual(after["visitor"]["id"], before["visitor"]["id"])
        self.assertNotIn("h", after["visitor"])
        self.assertNotEqual(after["session"], before["session"])

    def test_after_reset_batches_carry_the_new_visitor_id_the_new_session_and_no_hash(self):
        after = self.logs["signin"]["afterReset"]
        batches = self.batches_of(after["visitor"]["id"])
        self.assertTrue(batches)
        self.assertEqual({batch.get("idh") for batch in batches}, {None})
        self.assertEqual({batch["s"] for batch in batches}, {after["session"]})
        whys = [record.get("why") for batch in batches for record in batch.get("x", []) if record["ty"] == "session"]
        self.assertEqual(whys, ["reset"])

    def test_stop_deletes_the_visitor_entry_and_its_hash(self):
        self.assertEqual(self.logs["signin"]["afterStop"], {"visitor": None, "session": None})

    def test_before_consent_identify_stores_and_sends_nothing(self):
        log = self.logs["consent"]
        self.assertEqual(log["beforeAccept"], {"visitor": None, "session": None})
        accepted = log["afterAccept"]["visitor"]
        self.assertEqual(accepted["h"], HASH)
        self.assertIn(HASH, {batch.get("idh") for batch in self.batches_of(accepted["id"])})


if __name__ == "__main__":
    unittest.main()
