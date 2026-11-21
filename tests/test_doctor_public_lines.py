"""`agentcake doctor` on a server, the lines that need no server: agentcake/doctor_public.py given an exchange's
outcome or /api/health's answer (test_doctor_public.py runs the checks through a real `agentcake serve`).

    python3 -I -m unittest discover -s tests -p test_doctor_public_lines.py -v      (from the AgentCake folder)

The certificate line from a handshake's error; the self-check's line when the upload arrived and the front door
answered with a status cake.js sends it again on; the recent visitors' line from the protection net's state.
"""
import errno
import os
import ssl
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from agentcake import config, doctor_lines, doctor_public  # noqa: E402
from agentcake.doctor_net import Answer, Exchange  # noqa: E402
from cake_server import PREFIX  # noqa: E402
from test_doctor_public import (BETWEEN_TWO_SENTENCES, NO_CDN, ORIGIN, PUBLIC_HOST, PUBLIC_URL, SITE_DOMAIN,  # noqa: E402
                                text)


class Certificate(unittest.TestCase):
    """The 2nd line from an exchange's outcome, without a server."""
    VALUES = {"host": PUBLIC_HOST, "prefix": PREFIX}

    def line(self, error=None, root=PUBLIC_URL + PREFIX):
        answer = None if error else Answer(200, [], b"")
        return doctor_public.certificate_check(root, Exchange(answer, error, None), self.VALUES)[1:]

    def test_a_handshake_without_a_certificate_for_the_name_fails_with_its_reason(self):
        error = ssl.SSLError(1, "[SSL: TLSV1_ALERT_INTERNAL_ERROR] tlsv1 alert internal error")
        error.reason = "TLSV1_ALERT_INTERNAL_ERROR"
        self.assertEqual(self.line(error), (False, text("doctor_public_cert_bad", reason="TLSV1_ALERT_INTERNAL_ERROR",
                                                        hint=text("doctor_public_cert_hint", host=PUBLIC_HOST))))

    def test_nothing_answering_on_443_fails_and_says_so(self):
        refused = ConnectionRefusedError(errno.ECONNREFUSED, "Connection refused")
        self.assertEqual(self.line(refused), (False, text(
            "doctor_public_cert_no_connection", host=PUBLIC_HOST, error="Connection refused",
            hint=text("doctor_public_cert_hint", host=PUBLIC_HOST))))

    def test_an_http_public_url_is_a_warning(self):
        root = "http://" + PUBLIC_HOST + PREFIX
        self.assertEqual(self.line(root=root), (doctor_lines.WARN, text("doctor_public_cert_http", url=root,
                                                                        host=PUBLIC_HOST)))


class AnswerAfterArrival(unittest.TestCase):
    """The upload reached AgentCake as sent, and the front door answered: a status cake.js sends the upload again on
    (a proxy that gave up waiting, 504) fails the line, since every visit is then sent over and over; 204, and the 200
    some proxies make of it, pass."""
    C = {"site_domain": SITE_DOMAIN, "path_prefix": PREFIX, "public_url": PUBLIC_URL, "trust_lb": True}
    URL = f"{PUBLIC_URL}{PREFIX}/collect"

    def upload_line(self, status, removed=(), **arrived):
        sent = {"accept-language": "en-x-doctor", "user-agent": "agentcake-doctor/test", "host": PUBLIC_HOST,
                "origin": ORIGIN}
        came = [name for name in sent if name not in removed]
        arrival = dict({"headers": [[name, sent[name]] for name in came], "names": came, "ip_hash": "0"}, **arrived)
        answer = Exchange(Answer(status, [("Server", "Caddy")], b""), None, None)
        return doctor_public.upload_lines(self.C, doctor_public.Upload(self.URL, sent, answer, arrival), path=False)[0]

    def test_an_answer_cake_js_sends_again_on_fails_the_line(self):
        verdict, info = self.upload_line(504)[1:]
        self.assertIs(verdict, False)
        self.assertEqual(info, text("doctor_public_upload_retried", url=self.URL, status=504,
                                    through=text("doctor_public_through", platforms="Caddy")))

    def test_several_problems_are_sentences_with_no_semicolon_between_them(self):
        """A changed header, an answer cake.js sends again on and a made-up JA4: each problem in sentences of its own."""
        info = self.upload_line(504, removed=("accept-language",), ja4=doctor_public.made_up_value())[2]
        ja4, through = "X-Cake-JA4", text("doctor_public_through", platforms="Caddy")
        problems = [text("doctor_public_upload_changed", changes=text("doctor_public_removed", header="Accept-Language"),
                         through=through, fix=text("doctor_public_fix_caddy", host=PUBLIC_HOST, prefix=PREFIX)),
                    text("doctor_public_upload_retried", url=self.URL, status=504, through=through),
                    text("doctor_public_made_up", header=ja4, fix=text("doctor_public_made_up_fix", header=ja4))]
        self.assertEqual(info, " ".join(problems))
        self.assertTrue(all(problem.endswith(".") for problem in problems), problems)
        self.assertNotRegex(info, BETWEEN_TWO_SENTENCES)

    def test_204_and_200_pass(self):
        for status in (204, 200):
            self.assertIs(self.upload_line(status)[1], True, status)


class RecentVisitors(unittest.TestCase):
    """The 7th line reads the protection net's state that /api/health gives."""

    def line(self, health, public_url=PUBLIC_URL):
        c = dict(config.DEFAULTS, public_url=public_url, site_domain=SITE_DOMAIN, path_prefix=PREFIX)
        return doctor_public.visitors_check(c, health)

    def test_most_sessions_from_a_cdn_fail_with_the_routes_change(self):
        state = {"sessions": 25, "cdn": 22, "misconfigured": True}
        self.assertEqual(self.line({"address_check": state}), (text("doctor_public_visitors"), False, text(
            "doctor_public_visitors_cdn", cdn=22, sessions=25,
            fix=text("doctor_public_fix_address", host=PUBLIC_HOST, prefix=PREFIX))))
        self.assertIn(text("doctor_public_fix_address_path", host=SITE_DOMAIN, prefix=PREFIX),
                      self.line({"address_check": state}, public_url="")[2])

    def test_a_few_from_a_cdn_pass(self):
        state = {"sessions": 25, "cdn": 2, "misconfigured": False}
        self.assertEqual(self.line({"address_check": state})[1:],
                         (True, text("doctor_public_visitors_info", cdn=2, sessions=25)))

    def test_no_sessions_yet_pass(self):
        self.assertEqual(self.line({"address_check": NO_CDN})[1:], (True, text("doctor_public_visitors_none")))

    def test_an_agentcake_that_does_not_report_it_or_does_not_answer_is_skipped(self):
        self.assertEqual(self.line({"ok": True})[1:], (doctor_lines.SKIP, text("doctor_public_visitors_unknown")))
        self.assertEqual(self.line(None)[1:], (doctor_lines.SKIP, text(
            "doctor_public_not_checked", why=text("doctor_public_why_down"))))


if __name__ == "__main__":
    unittest.main()
