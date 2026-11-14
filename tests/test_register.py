"""Registering with Tartini AI (S5.8, D32): agentcake/register.py.

    python3 -I -m unittest discover -s tests -p test_register.py -v      (from the AgentCake folder)

A POST body is a registration only in the one form the page writes (the JSON "See what's sent" shows: two-space
indent, the fields in order, company only when given), with an e-mail address and a company that pass the rules in
data/register.json; anything else is Invalid, naming what is wrong. send() makes one POST of those bytes to the
receiving address and nothing more: no redirect followed, no retry; a receiver that is down, refuses, redirects or
never answers is NotSent, saying why. What a data folder sent is kept in its database, once.
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from receiver import Receiver, closed_url  # noqa: E402
from agentcake import config, register, store  # noqa: E402
from agentcake.wording import product  # noqa: E402

VERSION = "2026-11-13"


def written(**fields):
    """A registration as the page writes it: JSON.stringify(payload, null, 2), the fields in the page's order."""
    payload = {"email": "owner@example.com", "company": "Example Shop", "product_updates": False,
               "consent_version": VERSION}
    payload.update(fields)
    return json.dumps({k: v for k, v in payload.items() if v is not None}, indent=2, ensure_ascii=False)


class Payload(unittest.TestCase):
    def invalid(self, body):
        with self.assertRaises(register.Invalid) as refused:
            register.payload(body.encode() if isinstance(body, str) else body)
        return refused.exception.entry

    def test_a_body_the_page_writes_is_the_text_that_is_sent(self):
        body = written()
        self.assertEqual(register.payload(body.encode()), body)

    def test_company_is_optional_and_left_out_when_not_given(self):
        body = written(company=None)
        self.assertNotIn("company", body)
        self.assertEqual(register.payload(body.encode()), body)

    def test_text_beyond_ascii_is_kept_as_written(self):
        body = written(company="Bäckerei Ünal 東京")
        self.assertEqual(register.payload(body.encode()), body)

    def test_an_email_address_must_look_like_one(self):
        for bad in ("", "owner", "owner@", "@example.com", "owner@example", "owner @example.com",
                    "owner@exa mple.com", "owner@-example.com", "a" * 250 + "@example.com"):
            with self.subTest(email=bad):
                self.assertEqual(self.invalid(written(email=bad)), "register_bad_email")

    def test_a_company_given_must_be_some_printable_text_of_a_sensible_length(self):
        rules = register.rules()
        for bad in ("", "   ", "Shop\nName", "Shop ", "x" * (rules["company_max_chars"] + 1)):
            with self.subTest(company=bad):
                self.assertEqual(self.invalid(written(company=bad)), "register_bad_company")
        self.assertEqual(register.payload(written(company="x" * rules["company_max_chars"]).encode()),
                         written(company="x" * rules["company_max_chars"]))

    def test_product_updates_is_true_or_false(self):
        for bad in ("yes", 1, None):
            with self.subTest(product_updates=bad):
                body = written()
                body = body.replace('"product_updates": false', f'"product_updates": {json.dumps(bad)}')
                self.assertEqual(self.invalid(body), "register_bad_updates")

    def test_the_consent_version_is_a_date(self):
        for bad in ("", "v1", "2026-11-13T00:00", 20261113):
            with self.subTest(consent_version=bad):
                self.assertEqual(self.invalid(written(consent_version=bad)), "register_bad_version")

    def test_nothing_but_the_four_fields(self):
        self.assertEqual(self.invalid(written(site="shop.example.com")), "register_unknown_field")
        self.assertEqual(self.invalid(written(email=None)), "register_bad_email")

    def test_only_the_form_the_page_writes(self):
        payload = json.loads(written())
        for other in (json.dumps(payload),  # compact
                      json.dumps(dict(reversed(list(payload.items()))), indent=2),  # another order
                      written().replace('"email": "owner@example.com",',
                                        '"email": "other@example.com",\n  "email": "owner@example.com",'),
                      written() + "\n"):
            with self.subTest(body=other):
                self.assertEqual(self.invalid(other), "register_not_as_shown")

    def test_not_json_or_not_utf8(self):
        self.assertEqual(self.invalid(b"email=owner@example.com"), "bad_json")
        self.assertEqual(self.invalid(written().encode("utf-16")), "bad_json")


class Send(unittest.TestCase):
    def receiver(self, **kwargs):
        receiver = Receiver(**kwargs)
        self.addCleanup(receiver.close)
        return receiver

    def test_one_post_carries_the_body_byte_for_byte(self):
        receiver, body = self.receiver(), written(company="Bäckerei")
        register.send(body, receiver.url)
        self.assertEqual(len(receiver.requests), 1)
        got = receiver.requests[0]
        self.assertEqual((got["method"], got["body"]), ("POST", body.encode("utf-8")))
        self.assertEqual(got["headers"]["Content-Type"], "application/json")
        self.assertEqual(got["headers"]["User-Agent"], product()["name"], "the product's name, no version")

    def test_a_receiver_that_refuses_is_not_sent_and_asked_once(self):
        for status in (404, 500, 503):
            with self.subTest(status=status):
                receiver = self.receiver(status=status)
                with self.assertRaises(register.NotSent) as failed:
                    register.send(written(), receiver.url)
                self.assertEqual((failed.exception.entry, failed.exception.values["code"]),
                                 ("register_refused", status))
                self.assertEqual(len(receiver.requests), 1)

    def test_a_redirect_is_not_followed(self):
        for status in (301, 302, 307, 308):
            with self.subTest(status=status):
                receiver = self.receiver(status=status)
                with self.assertRaises(register.NotSent):
                    register.send(written(), receiver.url)
                self.assertEqual([r["path"] for r in receiver.requests], ["/register"], "nothing sent elsewhere")

    def test_nothing_listening_is_not_sent(self):
        with self.assertRaises(register.NotSent) as failed:
            register.send(written(), closed_url())
        self.assertEqual(failed.exception.entry, "register_unreachable")

    def test_a_receiver_that_never_answers_is_given_up_on(self):
        receiver = self.receiver(hang=True)
        with self.assertRaises(register.NotSent) as failed:
            register.send(written(), receiver.url, timeout_s=0.2)
        self.assertEqual(failed.exception.entry, "register_unreachable")
        self.assertEqual(len(receiver.requests), 1)

    def test_an_address_that_is_not_one_is_not_sent(self):
        for url in ("tartini", "ftp://example.com/register", "http://"):
            with self.subTest(url=url), self.assertRaises(register.NotSent) as failed:
                register.send(written(), url)
            self.assertEqual(failed.exception.entry, "register_unreachable")


class Kept(unittest.TestCase):
    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        os.environ.pop("CAKE_PORT", None)
        config.save_user(site_key="ck_registration", disk_min_free_mb=0)

    def test_what_was_sent_is_kept_once_per_data_folder(self):
        con = store.db()
        try:
            self.assertIsNone(register.kept(con))
            register.keep(con, written(), 1_794_475_800_000)
            self.assertEqual(register.kept(con), {"body": written(), "sent_ms": 1_794_475_800_000})
        finally:
            con.close()
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        con = store.db()
        try:
            self.assertIsNone(register.kept(con), "another data folder has not registered")
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
