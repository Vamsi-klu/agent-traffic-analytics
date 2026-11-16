"""window.cake.identify(id) and window.cake.reset(): agentcake/static/src/identify.js and visitor.js run on their own in
Node (tests/browser/identify_logic.mjs, with Node's WebCrypto and stand-ins for the parts they talk to).

The hash is SHA-256 of the site key, ":" and the id, in hexadecimal: the same for the same id, another for another
site key; a number is hashed as its string; it is kept with the visitor id and put into the batches' header once. What
is not an id (empty, blank, not a string or a number, a placeholder word) is refused with a fault that does not hold
the value; without SubtleCrypto nothing is kept or sent. Before cake.js starts nothing is stored or sent. reset()
after start begins a new session and, between its batches, a new visitor id without the hash; before start it deletes
the stored id, hash and session id. A page view begins with the stored hash, and a year without use forgets both.
A hash still being made when reset() or stop() comes is dropped; identify() over another hash replaces it.

Skipped without node.
"""
import hashlib
import json
import os
import shutil
import subprocess
import unittest

from . import harness

DRIVER = os.path.join(harness.HERE, "identify_logic.mjs")


class IdentifyLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("needs node")
        out = subprocess.run(["node", DRIVER], check=True, capture_output=True, text=True, timeout=60).stdout
        found = json.loads(out)
        cls.cases, cls.keys, cls.separator = found["cases"], found["keys"], found["separator"]

    def sha256(self, key, user_id):
        return hashlib.sha256(f"{self.keys[key]}{self.separator}{user_id}".encode()).hexdigest()

    def test_the_hash_is_sha256_of_the_site_key_and_the_id(self):
        self.assertEqual(self.cases["stable"]["first"]["h"], self.sha256("a", "user-42"))

    def test_the_same_id_gives_the_same_hash_and_the_header_gets_it_once(self):
        case = self.cases["stable"]
        self.assertEqual(case["again"], case["first"])
        self.assertEqual(case["log"], [["header.idh", self.sha256("a", "user-42")]])

    def test_another_site_key_gives_another_hash(self):
        by_key = self.cases["other_key"]["byKey"]
        self.assertEqual(by_key, self.sha256("b", "user-42"))
        self.assertNotEqual(by_key, self.sha256("a", "user-42"))

    def test_a_number_is_hashed_as_its_string(self):
        self.assertEqual(self.cases["other_key"]["number"], self.sha256("b", "42"))

    def test_what_is_not_an_id_is_refused_without_recording_it(self):
        case = self.cases["refused"]
        self.assertNotIn("h", case["entry"])
        self.assertEqual(len(case["log"]), 10)
        self.assertEqual({tuple(entry[:2]) for entry in case["log"]}, {("fault", "identify")})
        for word in ("undefined", "NULL", "distinct_id"):
            self.assertFalse(any(word in entry[2] for entry in case["log"]))

    def test_without_subtle_crypto_nothing_is_kept_or_sent(self):
        case = self.cases["no_crypto"]
        self.assertNotIn("h", case["entry"])
        self.assertEqual([entry[:2] for entry in case["log"]], [["fault", "identify"]])

    def test_before_start_nothing_is_stored_or_sent(self):
        case = self.cases["before_start"]
        self.assertEqual(case["before"], {"stored": {}, "log": []})
        self.assertEqual(case["after"]["h"], self.sha256("a", "user-42"))

    def test_reset_begins_a_new_session_and_between_its_batches_a_new_visitor_without_the_hash(self):
        case = self.cases["reset"]
        self.assertEqual(case["identified"]["h"], self.sha256("a", "user-a"))
        self.assertEqual(case["log"][1:], [["session.restart", "reset"], ["header.vid", "visitor2"], ["session.new"]])
        self.assertEqual(case["after"]["id"], "visitor2")
        self.assertNotIn("h", case["after"])
        self.assertIsNone(case["hash"])

    def test_reset_before_start_deletes_the_stored_ids(self):
        case = self.cases["reset_before_start"]
        self.assertEqual(case["stored"], {})
        self.assertEqual(case["log"], [["session.forget"]])
        self.assertEqual(case["nextId"], "visitor1")

    def test_a_page_view_begins_with_the_stored_hash_and_a_year_forgets_both(self):
        case = self.cases["page_view"]
        self.assertEqual((case["keptId"], case["kept"]), ("kept", "b" * 64))
        self.assertEqual((case["laterId"], case["later"]), ("visitor1", None))

    def test_a_hash_still_being_made_at_reset_is_dropped(self):
        case = self.cases["shared"]
        self.assertEqual(case["entry"], {"id": "visitor2", "t": case["entry"]["t"], "h": self.sha256("a", "user-b")})
        self.assertNotIn(["header.idh", self.sha256("a", "user-a")], case["log"])

    def test_identify_over_another_hash_replaces_it_and_keeps_the_visitor_id(self):
        case = self.cases["replaced"]
        self.assertEqual((case["entry"]["id"], case["entry"]["h"]), ("visitor1", self.sha256("a", "user-b")))

    def test_a_hash_still_being_made_at_stop_is_not_kept(self):
        self.assertEqual(self.cases["stopped"], {"stored": {}, "log": []})

    def test_without_local_storage_the_hash_goes_with_this_page(self):
        case = self.cases["no_storage"]
        self.assertEqual(case["hash"], self.sha256("a", "user-42"))
        self.assertEqual(case["log"], [["header.idh", self.sha256("a", "user-42")]])


if __name__ == "__main__":
    unittest.main()
