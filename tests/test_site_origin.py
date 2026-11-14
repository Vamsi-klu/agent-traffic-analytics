"""Where an upload came from (S2.1): agentcake/site_origin.py.

    python3 -I -m unittest discover -s tests -p test_site_origin.py -v      (from the Agent Cake folder)

The website (site_domain and its subdomains; on the local listener also a dev server on this computer) or another site,
read from the Origin header, else the Referer, else the batch's own URL. There is no demo shop any more (D37): a page
under /demo on AgentCake's own port is a page like any other.
"""
import http.client
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake import site_origin  # noqa: E402
from agentcake.site_origin import OTHER, SITE  # noqa: E402

PORT = 7878
DEMO_URL = f"http://127.0.0.1:{PORT}/demo/product?id=tote"


def headers(**values):
    message = http.client.HTTPMessage()
    for name, value in values.items():
        message[name.replace("_", "-")] = value
    return message


def classify(batch_url=None, domain="", public=False, **header_values):
    return site_origin.classify(headers(**header_values), batch_url, {"port": PORT, "site_domain": domain}, public)


class NoDemoShop(unittest.TestCase):
    def test_a_page_under_demo_on_agentcakes_own_port_counts_as_the_site_on_the_local_listener(self):
        self.assertEqual(classify(DEMO_URL), SITE, "a page on this computer: a dev server")
        self.assertEqual(classify(DEMO_URL, Origin=f"http://127.0.0.1:{PORT}"), SITE)
        self.assertEqual(classify(f"http://localhost:{PORT}/demo", domain="example.com"), SITE)

    def test_on_the_public_listener_it_is_another_site(self):
        self.assertEqual(classify(DEMO_URL, domain="example.com", public=True), OTHER)

    def test_a_demo_url_sent_from_another_origin_is_another_site(self):
        self.assertEqual(classify(DEMO_URL, domain="example.com", Origin="https://evil.example"), OTHER)

    def test_there_are_two_answers_only(self):
        for url in (DEMO_URL, "https://example.com/", "https://evil.test/", None):
            for public in (False, True):
                self.assertIn(classify(url, domain="example.com", public=public), (SITE, OTHER), (url, public))


class Site(unittest.TestCase):
    def test_without_a_site_domain_nothing_is_flagged(self):
        for public in (False, True):
            self.assertEqual(classify("https://anything.example/", public=public, Origin="https://else.example"), SITE)

    def test_the_site_domain_and_its_subdomains(self):
        for origin in ("https://example.com", "https://www.example.com", "https://shop.example.com:8443",
                       "https://EXAMPLE.com", "http://example.com."):
            self.assertEqual(classify(domain="example.com", public=True, Origin=origin), SITE, origin)

    def test_other_sites_are_flagged(self):
        for origin in ("https://example.com.evil.test", "https://notexample.com", "https://evil.test", "null",
                       "file://", "garbage"):
            self.assertEqual(classify("https://example.com/", domain="example.com", public=True, Origin=origin), OTHER,
                             origin)

    def test_the_referer_counts_when_there_is_no_origin_then_the_batch_url(self):
        self.assertEqual(classify(domain="example.com", Referer="https://example.com/cart"), SITE)
        self.assertEqual(classify(domain="example.com", Referer="https://evil.test/"), OTHER)
        self.assertEqual(classify("https://www.example.com/", domain="example.com"), SITE)
        self.assertEqual(classify("https://evil.test/", domain="example.com"), OTHER)
        self.assertEqual(classify(None, domain="example.com"), OTHER, "nothing says where it came from")
        self.assertEqual(classify("https://evil.test/", domain="example.com", Origin="https://example.com"), SITE,
                         "the browser's Origin header outranks what the batch says")

    def test_a_site_domain_written_with_www_covers_the_bare_domain(self):
        self.assertEqual(classify(domain="www.example.com", Origin="https://example.com"), SITE)

    def test_a_dev_server_on_this_computer_counts_as_the_site_only_on_the_local_listener(self):
        for origin in ("http://localhost:3000", "http://127.0.0.1:5173", "http://[::1]:8080", "http://shop.localhost:3000"):
            self.assertEqual(classify(domain="example.com", Origin=origin), SITE, origin)
            self.assertEqual(classify(domain="example.com", public=True, Origin=origin), OTHER, origin)

    def test_a_url_with_a_broken_port_is_just_another_site(self):
        self.assertEqual(classify("http://127.0.0.1:99999/demo", domain="example.com"), OTHER)
        self.assertEqual(classify("http://[::1", domain="example.com"), OTHER)


if __name__ == "__main__":
    unittest.main()
