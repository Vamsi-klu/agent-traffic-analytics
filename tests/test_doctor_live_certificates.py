"""`agentcake doctor --url` on a page that does not open for a TLS reason: agentcake/doctor_live.py.

    python3 -I -m unittest discover -s tests -p test_doctor_live_certificates.py -v      (from the AgentCake folder)

A certificate Python's default check refuses is said to be the certificate's problem: which one, and what to check.
It is never said to be a sandbox's doing. Python's TLS errors carry the TLS library's own code in errno, and the code
of every refused certificate (SSL_ERROR_SSL) is 1, which errno.errorcode reads as EPERM, one of the errors a sandbox's
refusal comes with (data/doctor.json blocked_errors); an https address on a server that speaks plain HTTP fails with
the same code, and a failed DNS lookup carries the resolver's own code, which on macOS can be 1 too. A connection the
system itself refuses with one of those errors is still said to be a sandbox's.

The website is a server on 127.0.0.1, over HTTPS with a certificate made for this run (doctor_live_fixtures.py) and
opened as https://localhost:<port>/ with Python's default certificate check trusting only the test authority, or over
plain HTTP. The errors no local server can bring about are raised in doctor's place.
"""
import errno
import json
import os
import shutil
import socket
import ssl
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from agentcake import config, doctor_lines, doctor_live, site_setup, wording  # noqa: E402
from agentcake.datafiles import load  # noqa: E402
from cake_server import free_port  # noqa: E402
from doctor_live_fixtures import (HOST, HTTPPage, HTTPRedirect, HTTPSPage, SiteCertificates, strict_check,  # noqa: E402
                                  trusting)
from doctor_public_fixtures import LOOPBACK  # noqa: E402
from site_fixtures import page  # noqa: E402

SITE_KEY = "ck_doctorcert"
FRAMEWORK = "unknown"  # no server half: the token lines are not what these tests are about
ELSEWHERE_HOST = "example.com"
ELSEWHERE = f"https://{ELSEWHERE_HOST}/"  # an address no test opens: urlopen is replaced there
# OpenSSL's X509_V_ERR_* codes and its words for them (crypto/x509/x509_txt.c)
EXPIRED, EXPIRED_WORDS = 10, "certificate has expired"  # X509_V_ERR_CERT_HAS_EXPIRED
OTHER_PURPOSE, OTHER_PURPOSE_WORDS = 26, "unsuitable certificate purpose"  # X509_V_ERR_INVALID_PURPOSE, no entry
MISSING_KEY_ID, MISSING_KEY_ID_WORDS = 85, "Missing Authority Key Identifier"  # OpenSSL 3's strict check
OPENSSL_1_1_1_78, OPENSSL_1_1_1_78_WORDS = 78, "unknown certificate verification error"  # 78 in OpenSSL 1.1.1l
OPENSSL_3_0, OPENSSL_1_1_1 = (3, 0, 0, 0, 0), (1, 1, 1, 12, 15)  # ssl.OPENSSL_VERSION_INFO of each


class PageLine(unittest.TestCase):
    """A scratch CAKE_HOME with a site key, and the page that loads its cake.js."""

    def setUp(self):
        home = tempfile.mkdtemp(prefix="cake-test-")
        self.addCleanup(shutil.rmtree, home, True)
        patched = mock.patch.dict(os.environ, {"CAKE_HOME": home, "CAKE_PORT": str(free_port())})
        patched.start()
        self.addCleanup(patched.stop)
        with open(os.path.join(home, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"site_key": SITE_KEY}, f)
        self.page = page("Brew Bean", site_setup.snippet(config.load_cfg())).encode("utf-8")

    def page_line(self, url):
        """(verdict, info) of the line of the page at url; the three lines after it are not checked when it fails."""
        (_, verdict, info), *after = doctor_live.page_checks(config.load_cfg(), url, FRAMEWORK)
        if verdict is False:
            self.assertEqual([line[1] for line in after], [doctor_lines.SKIP] * len(after))
        return verdict, info

    def assertNoSandbox(self, info):
        self.assertNotIn(wording.text("doctor_live_blocked"), info)
        self.assertNotIn("sandbox", info.lower())

    def assertOwnWords(self, info):
        """info is doctor_live_open_failed's: the error in its own words."""
        before, _, after = wording.text("doctor_live_open_failed", error="{error}").partition("{error}")
        self.assertIn(before, info)
        self.assertTrue(info.endswith(after), info)


class SiteCertificate(PageLine):
    certificates = None

    @classmethod
    def setUpClass(cls):
        certificates = SiteCertificates()
        if not certificates.available:
            raise unittest.SkipTest("the openssl command, which makes the test certificates, is missing")
        cls.certificates = certificates

    @classmethod
    def tearDownClass(cls):
        cls.certificates.remove()

    def opened_with(self, certificate, host=HOST):
        site = HTTPSPage(certificate, self.page)
        self.addCleanup(site.close)
        with trusting(self.certificates.ca):
            return self.page_line(f"https://{host}:{site.port}/")

    def assertCertificateProblem(self, certificate, entry, **values):
        verdict, info = self.opened_with(certificate)
        self.assertIs(verdict, False)
        self.assertIn(wording.text(entry, host=HOST, **values), info)
        self.assertNoSandbox(info)

    def test_a_certificate_the_check_accepts_opens_the_page(self):
        verdict, info = self.opened_with(self.certificates.good)
        self.assertIs(verdict, True, info)

    def test_an_expired_certificate_is_said_to_be_out_of_date_by_this_computers_clock(self):
        self.assertCertificateProblem(self.certificates.expired, "doctor_live_cert_dates", reason=EXPIRED_WORDS)

    def test_a_self_signed_certificate_is_said_to_be_self_signed(self):
        self.assertCertificateProblem(self.certificates.self_signed, "doctor_live_cert_self_signed")

    def test_a_certificate_for_other_names_says_the_host_it_does_not_cover(self):
        self.assertCertificateProblem(self.certificates.other_name, "doctor_live_cert_name")

    def test_a_certificate_refused_after_a_redirect_is_named_with_the_host_the_redirect_led_to(self):
        site = HTTPSPage(self.certificates.expired, self.page)
        self.addCleanup(site.close)
        start = HTTPRedirect(f"https://{HOST}:{site.port}/")
        self.addCleanup(start.close)
        with trusting(self.certificates.ca):
            verdict, info = self.page_line(f"http://{LOOPBACK}:{start.port}/")
        self.assertIs(verdict, False)
        self.assertIn(wording.text("doctor_live_cert_dates", host=HOST), info)
        self.assertNotIn(wording.text("doctor_live_cert_dates", host=LOOPBACK), info)

    def test_an_ip_address_the_certificate_is_not_for_asks_for_the_domain_name(self):
        verdict, info = self.opened_with(self.certificates.good, host=LOOPBACK)
        self.assertIs(verdict, False)
        self.assertIn(wording.text("doctor_live_cert_ip", host=LOOPBACK), info)
        self.assertNoSandbox(info)

    @unittest.skipUnless(strict_check(), "this Python's default check accepts a certificate without an Authority Key "
                                         "Identifier (only Python 3.13 and later, with OpenSSL 3, refuse it)")
    def test_a_certificate_without_an_authority_key_identifier_names_the_rule_it_breaks(self):
        self.assertCertificateProblem(self.certificates.no_key_id, "doctor_live_cert_strict",
                                      reason=MISSING_KEY_ID_WORDS)

    def test_a_certificate_from_an_authority_python_does_not_trust_says_where_to_look(self):
        self.assertCertificateProblem(self.certificates.unknown_issuer, "doctor_live_cert_issuer")


class TLSFailure(PageLine):
    def test_an_https_address_on_a_server_that_speaks_plain_http_is_no_sandbox(self):
        site = HTTPPage(self.page)
        self.addCleanup(site.close)
        verdict, info = self.page_line(f"https://{HOST}:{site.port}/")
        self.assertIs(verdict, False)
        self.assertNoSandbox(info)
        self.assertOwnWords(info)

    def refused(self, error):
        """The page line when opening the page fails with error, as urllib reports it."""
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError(error)):
            return self.page_line(ELSEWHERE)

    def test_a_refused_certificate_is_the_certificates_problem_whatever_its_errno(self):
        verdict, info = self.refused(verification_error(EXPIRED, EXPIRED_WORDS))
        self.assertIs(verdict, False)
        self.assertIn(wording.text("doctor_live_cert_dates", host=ELSEWHERE_HOST, reason=EXPIRED_WORDS), info)
        self.assertNoSandbox(info)

    def test_a_refusal_without_words_of_its_own_is_said_in_the_checks_words(self):
        verdict, info = self.refused(verification_error(OTHER_PURPOSE, OTHER_PURPOSE_WORDS))
        self.assertIn(wording.text("doctor_live_cert_other", host=ELSEWHERE_HOST, reason=OTHER_PURPOSE_WORDS), info)
        self.assertNoSandbox(info)

    def test_a_strict_check_code_on_openssl_3_names_the_strict_check(self):
        with mock.patch.object(ssl, "OPENSSL_VERSION_INFO", OPENSSL_3_0):
            verdict, info = self.refused(verification_error(MISSING_KEY_ID, MISSING_KEY_ID_WORDS))
        self.assertIn(wording.text("doctor_live_cert_strict", host=ELSEWHERE_HOST, reason=MISSING_KEY_ID_WORDS), info)

    def test_the_same_number_from_openssl_1_1_1_is_said_in_the_checks_words(self):
        # OpenSSL 1.1.1 numbers its own late additions 76 to 79; its strict mode has none of OpenSSL 3's codes
        with mock.patch.object(ssl, "OPENSSL_VERSION_INFO", OPENSSL_1_1_1):
            verdict, info = self.refused(verification_error(OPENSSL_1_1_1_78, OPENSSL_1_1_1_78_WORDS))
        self.assertIn(wording.text("doctor_live_cert_other", host=ELSEWHERE_HOST, reason=OPENSSL_1_1_1_78_WORDS), info)

    def test_a_failed_dns_lookup_is_no_sandbox_whatever_its_code(self):
        # macOS numbers EAI_ADDRFAMILY 1 and EAI_PROTOCOL 13: as errno values, EPERM and EACCES
        for code in (errno.EPERM, errno.EACCES):
            with self.subTest(code=code):
                verdict, info = self.refused(socket.gaierror(code, "the resolver's own words"))
                self.assertNoSandbox(info)
                self.assertOwnWords(info)

    def test_a_connection_the_system_refuses_is_still_a_sandbox(self):
        for name in load("data/doctor.json")["blocked_errors"]:
            with self.subTest(errno=name):
                number = getattr(errno, name)
                verdict, info = self.refused(OSError(number, os.strerror(number)))
                self.assertIs(verdict, False)
                self.assertIn(wording.text("doctor_live_blocked"), info)


def verification_error(code, words):
    """A certificate Python's check refused with OpenSSL's code and words, as the ssl module raises it: its errno is
    the TLS library's SSL_ERROR_SSL."""
    error = ssl.SSLCertVerificationError(ssl.SSL_ERROR_SSL, f"[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify "
                                                            f"failed: {words}")
    error.verify_code, error.verify_message = code, words
    return error


if __name__ == "__main__":
    unittest.main()
