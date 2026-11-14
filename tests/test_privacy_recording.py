"""What cake.js must never record, and that it records only after consent (plan step S1.4; GOAL G4, G12, T10, S1).

    python3 -I -m unittest discover -s tests -v      (from the repository root; needs CAKE_PLAYWRIGHT, see below)

Chromium (tests/browser/drive.mjs) types a made-up canary string into every kind of field on a test page (an ordinary
input, a data-cake-private input, a password, a payment card field, a textarea, an editable element, the fields of a
payment form in a frame) and a made-up card number only this run knows into the card fields, then checks out in the
demo shop with the canary and the test card 4242 4242 4242 4242. Every upload the stand-in collector received is then
searched: the canary, this run's card number and 4242 4242 4242 4242 appear nowhere (the shop's checkout no longer
prints a card number, S5.6, so the search makes no exception); no record holds a key's name or a typed value; private
fields send nothing typed. Then GOAL T10's three cases on a page with
a consent bar (data-consent="required"): refused at once, nothing is sent; accepted and refused later, from the
moment the click on Reject reaches the page cake.js makes no batch and starts no upload, and the visit id is gone;
accepted, every page is recorded. The refusal's moment and the uploads the page started are taken in the page itself,
on the clock cake.js stamps its batches with (tests/browser/consent.mjs, watchRefusal): a mark taken by the driver
before it clicks is up to a second early under load, which once made a batch from before the refusal look like one from
after it. And refusals while uploads are under way (GOAL G12, "refused = stopped and forgotten"): a gzip or an upload
that fails after the refusal sends nothing and parks nothing in sessionStorage, a batch parked before it is dropped,
and a "yes" on the next page starts a new visit that carries nothing from before.

Skipped, saying what is missing, without node, playwright-core or Chromium (tests/browser/harness.py).
CAKE_CPU_THROTTLE=<n> runs the pages n times slower, as on a loaded machine (drive.mjs).
"""
import json
import os
import secrets
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from browser import harness, uploads  # noqa: E402  (tests/ is put on sys.path first)

CARD = "4242 4242 4242 4242"
PRIVATE_FIELDS = {"#secret", "#pw", "#cc", "#cardnumber", "#expiry", "#cvc"}
KEY_FIELDS = {"t", "ty", "tr", "hf", "vs", "kc", "ce", "rp", "s", "r"}
INPUT_FIELDS = {"t", "ty", "tr", "hf", "vs", "it", "ic", "len", "s", "r"}
NAMING_FIELDS = {"key", "code", "keyCode", "which", "charCode", "char", "data", "value", "text"}
PLAN = ("privacy:1,consent_reject:1,consent_accept_reject:1,consent_accept:1,"
        "consent_reject_while_zipping:1,consent_reject_in_flight:1")


def made_up_card():
    """A random 16-digit number with a valid Luhn check digit (test prefix 4000), grouped like a card number."""
    digits = [4, 0, 0, 0] + [secrets.randbelow(10) for _ in range(11)]
    total = 0
    for position, digit in enumerate(reversed(digits)):  # the check digit goes to the right of these
        doubled = digit * 2 if position % 2 == 0 else digit
        total += doubled - 9 if doubled > 9 else doubled
    digits.append((10 - total % 10) % 10)
    text = "".join(map(str, digits))
    return " ".join(text[i:i + 4] for i in range(0, 16, 4))


def strings_in(value):
    """Every string inside a JSON value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings_in(item)


def privacy_page():
    with open(os.path.join(harness.ROOT, "agentcake", "data", "privacy.json"), encoding="utf-8") as f:
        return json.load(f)["page"]


class PrivacyRecording(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lacking = harness.missing()
        if lacking:
            raise unittest.SkipTest("browser tests need " + "; ".join(lacking))
        cls.canary = "cake-canary-" + secrets.token_hex(8)
        cls.card = made_up_card()
        cls.out = harness.out_dir("privacy")
        cls.base, cls.logs = harness.run(PLAN, cls.out, extra=["--canary", cls.canary, "--card", cls.card])
        with open(os.path.join(cls.out, "collect.ndjson"), encoding="utf-8") as f:
            cls.upload_text = f.read()
        cls.entries = uploads.load(cls.out)
        cls.views = uploads.page_views(uploads.unique(cls.entries))
        cls.visits = uploads.visits(cls.views)
        cls.runs = {name: uploads.visit_in(cls.visits, log["started"], log["ended"]) for name, log in cls.logs.items()}

    def entries_during(self, name):
        log = self.logs[name]
        return [e for e in self.entries if log["started"] <= e["at"] <= log["ended"]]

    def raw_records(self, kinds):
        return [r for view in self.views.values() for r in view["r"] if r.get("ty") in kinds]

    # ---------------------------------------------------------------- never recorded (G4, S1)
    def test_the_privacy_visit_was_recorded(self):
        visit = self.runs["privacy-1"]
        self.assertIsNotNone(visit)
        self.assertGreaterEqual(len(visit), 4)  # the test page, the product, the checkout, the order page

    def test_the_canary_is_in_no_upload(self):
        self.assertTrue(self.canary)
        self.assertNotIn(self.canary, self.upload_text)

    def test_this_runs_card_number_is_in_no_upload(self):
        self.assertNotIn(self.card, self.upload_text)
        self.assertNotIn(self.card.replace(" ", ""), self.upload_text)

    def test_the_demo_card_number_is_in_no_upload(self):
        found = [s for entry in self.entries for s in strings_in(entry["batch"])
                 if CARD in s or CARD.replace(" ", "") in s]
        self.assertEqual(found, [])

    def test_key_records_hold_a_class_never_the_key(self):
        classes = privacy_page()["key_classes"]
        allowed = {c["class"] for c in classes["single_character"]} | set(classes["named"].values())
        allowed |= set(classes["prefixes"].values()) | {classes["single_character_other"], classes["other"]}
        keys = self.raw_records({"keydown", "keyup"})
        self.assertTrue(keys)
        for record in keys:
            self.assertLessEqual(set(record), KEY_FIELDS)
            self.assertIn(record["kc"], allowed)

    def test_input_records_hold_the_input_type_and_length_only(self):
        inputs = self.raw_records({"input"})
        self.assertTrue(inputs)
        for record in inputs:
            self.assertLessEqual(set(record), INPUT_FIELDS)
        self.assertTrue(any(isinstance(r.get("len"), int) and r["len"] > 0 for r in inputs))

    def test_no_raw_record_names_a_key_or_a_value(self):
        for view in self.views.values():
            for record in view["r"]:
                self.assertEqual(set(record) & NAMING_FIELDS, set())

    def test_only_the_fields_that_may_be_recorded_send_key_events(self):
        # On the test page the canary is typed into three fields cake.js may record (#name, #notes, the editable
        # #note) and into #secret, #pw, and this run's card number into #cc: only the first three's keys arrive.
        page = next(view for view in self.runs["privacy-1"] if view["urls"][0].endswith("/pages/private.html"))
        keydowns = [r for r in page["r"] if r.get("ty") == "keydown"]
        self.assertEqual(len(keydowns), 3 * len(self.canary))

    def test_private_fields_send_nothing_typed_and_are_never_named(self):
        for view in self.views.values():
            for record in view["r"]:
                self.assertNotIn(record.get("s"), PRIVATE_FIELDS)

    # ---------------------------------------------------------------- consent (G12, T10)
    def test_refused_at_once_nothing_is_sent(self):
        log = self.logs["consent_reject-1"]
        self.assertEqual(self.entries_during("consent_reject-1"), [])
        self.assertIsNone(log["visit_id_after_reject"])

    # The refusal is log["refusal"]: when the click on Reject reached the page, on cake.js's clock, before the button's
    # handler called window.cake.stop(); with how many uploads the page had started by then (consent.mjs, watchRefusal).
    def test_refused_later_no_batch_is_made_from_the_refusal_on(self):
        refusal = self.logs["consent_accept_reject-1"]["refusal"]
        during = self.entries_during("consent_accept_reject-1")
        self.assertTrue(refusal["cake_loaded"], "cake.js had loaded: the Reject button called window.cake.stop()")
        self.assertTrue(during, "the part before the refusal is recorded")
        made_after = [(e["batch"]["seq"], e["batch"]["why"], round(e["batch"]["t"] - refusal["t"], 1))
                      for e in during if e["batch"]["t"] > refusal["t"]]
        self.assertEqual(made_after, [], "(seq, why, ms after the refusal) of batches made after it")

    def test_refused_later_no_upload_starts_from_the_refusal_on(self):
        log = self.logs["consent_accept_reject-1"]
        before = log["refusal"]["started"]
        self.assertEqual(log["uploads_started"] - before, 0, "uploads the page started after the refusal")
        # Nor did cake receive one the page had not started before it (sent some other way, or as the page was left).
        self.assertLessEqual(len(self.entries_during("consent_accept_reject-1")), before)

    def test_refused_later_the_visit_id_is_gone(self):
        log = self.logs["consent_accept_reject-1"]
        self.assertIsNotNone(log["visit_id_before_reject"])
        self.assertIsNone(log["visit_id_after_reject"])

    # Refused while uploads were under way (tests/browser/consent.mjs): what was already on its way may still arrive,
    # but cake.js sends nothing after the refusal and keeps nothing for later.
    def test_refused_while_zipping_a_gzip_that_fails_afterwards_sends_nothing(self):
        log = self.logs["consent_reject_while_zipping-1"]
        self.assertTrue(log["refusal"]["cake_loaded"])
        self.assertEqual(log["uploads_started"] - log["refusal"]["started"], 0, "uploads started after the refusal")
        self.assertEqual(log["parked_after_failures"], 0, "batches parked in sessionStorage after the refusal")

    def test_refused_in_flight_nothing_starts_after_the_refusal(self):
        log = self.logs["consent_reject_in_flight-1"]
        self.assertTrue(log["refusal"]["cake_loaded"])
        self.assertEqual(log["uploads_started"] - log["refusal"]["started"], 0, "uploads started after the refusal")

    def test_refused_in_flight_parked_batches_are_dropped_and_failed_ones_not_parked(self):
        log = self.logs["consent_reject_in_flight-1"]
        self.assertEqual(log["parked_at_refusal"], 0, "batches parked before the refusal and kept")
        self.assertEqual(log["parked_after_failures"], 0, "uploads that failed after the refusal, parked")

    def test_accepted_again_after_a_refusal_nothing_from_before_goes(self):
        log = self.logs["consent_reject_in_flight-1"]
        refused, new = log["visit_id_before_reject"], log["visit_id_after_accept"]
        batches = uploads.unique(self.entries_during("consent_reject_in_flight-1"))
        self.assertIsNotNone(refused)
        self.assertIsNotNone(new)
        self.assertNotEqual(new, refused)
        self.assertEqual([b["seq"] for b in batches if b["s"] == refused], [], "batches of the refused visit")
        pages = [r for b in batches if b["s"] == new for r in b["x"] if r.get("ty") == "page"]
        self.assertEqual([page["n"] for page in pages], [1], "the new visit counts its pages from 1 again")

    def test_accepted_every_page_is_recorded(self):
        visit = self.runs["consent_accept-1"]
        self.assertIsNotNone(visit)
        self.assertEqual(len(visit), 2)
        self.assertTrue(all(view["page"]["consent"] == "start" for view in visit))
        self.assertTrue(all(uploads.full_snapshots(view) for view in visit))


class HiddenByTheOwner(unittest.TestCase):
    """What the site owner hides in AgentCake's settings (S5.5: hide_selectors, carried by /cake.js like cake serves it)
    is recorded as cake.js's own private elements are: an empty box in the replay, nothing typed kept. A list the browser
    cannot read is left out, said in a fault, and the page is still recorded."""
    OWNER = ".account, #owner-note"
    SHOWN, HIDDEN = "Everyone's replay shows this sentence.", ("The owner hides this heading", "keep this paragraph out")

    @classmethod
    def setUpClass(cls):
        lacking = harness.missing()
        if lacking:
            raise unittest.SkipTest("browser tests need " + "; ".join(lacking))
        cls.canary = "cake-canary-" + secrets.token_hex(8)
        cls.runs = {}
        for name, selectors in (("hidden", cls.OWNER), ("unreadable", "#owner-note {")):
            out = harness.out_dir(f"hidden-{name}")
            harness.run("hidden:1", out, runtime={"hide_selectors": selectors}, extra=["--canary", cls.canary])
            with open(os.path.join(out, "collect.ndjson"), encoding="utf-8") as f:
                text = f.read()
            cls.runs[name] = (text, uploads.page_views(uploads.unique(uploads.load(out))))

    def raw(self, run, kind):
        return [r for view in self.runs[run][1].values() for r in view["r"] if r.get("ty") == kind]

    def test_the_hidden_parts_never_reach_cake_and_the_rest_does(self):
        text = self.runs["hidden"][0]
        self.assertIn(self.SHOWN, text, "the page itself is recorded")
        for words in self.HIDDEN:
            self.assertNotIn(words, text)
        self.assertNotIn(self.canary, text)

    def test_nothing_typed_into_a_hidden_field_is_kept(self):
        typed = self.raw("hidden", "input")
        self.assertEqual({r.get("s") for r in typed}, {"#open"}, "only the ordinary field's input")
        self.assertEqual(len(self.raw("hidden", "keydown")), len(self.canary), "the keys of the ordinary field only")

    def test_a_list_the_browser_cannot_read_is_left_out_and_the_page_still_recorded(self):
        text, views = self.runs["unreadable"]
        self.assertIn(self.SHOWN, text)
        faults = [r for view in views.values() for r in view["x"] if r.get("ty") == "err"]
        self.assertIn("hide_selectors", {fault.get("where") for fault in faults})


if __name__ == "__main__":
    unittest.main()
