"""setup --print --site when public_url is a name that holds the server's own address, such as
cake.203-0-113-10.sslip.io (SERVER.md, "Sites without their own domain"): step 5 asks for no DNS record.

    python3 -I -m unittest discover -s tests -v      (from the AgentCake folder)

Such a name resolves to the address it holds through a free DNS service of a third party, so the site owner adds no A
or AAAA record; step 5 says so instead and points to SERVER.md's section for the service's risks. Which domains answer
this way, and the form of the address a name must hold, is data (data/ip_names.json), not code. Any other public_url
keeps step 5's DNS record (test_site_setup.py), and so does a name under such a domain that holds no whole address.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), HERE]
from agentcake import site_setup, wording  # noqa: E402
from agentcake.datafiles import load  # noqa: E402
from cake_server import SERVER_MD, read  # noqa: E402
from test_site_setup import SITE_KEY, SetupSite  # noqa: E402

DOMAINS = load("data/ip_names.json")["domains"]
SECTION = "Sites without their own domain"
ANCHOR = "SERVER.md#sites-without-their-own-domain"
ADDRESS = "203-0-113-10"  # 203.0.113.10, an example address of RFC 5737


class NameThatHoldsTheAddress(SetupSite):

    def step5(self, public_url):
        self.settings(site_key=SITE_KEY, public_listen="127.0.0.1:8080", path_prefix="/cake", site_domain="you.github.io",
                      public_url=public_url)
        out = self.printed("static")
        return " ".join(out[out.index(wording.text("setup_site_tell").strip().split(".")[0]):].split())

    def test_each_listed_domain_needs_no_dns_record(self):
        self.assertIn("sslip.io", DOMAINS)
        for domain in DOMAINS:
            with self.subTest(domain=domain):
                step5 = self.step5(f"https://cake.{ADDRESS}.{domain}")
                self.assertNotIn("A record", step5)
                self.assertNotIn("AAAA", step5)
                self.assertIn(f"{wording.product()['source']}/{ANCHOR}", step5, "where its risks are")
                self.assertIn(f"{wording.product()['command']} doctor", step5)
                self.assertIn(f"{wording.product()['source']}/deploy/Caddyfile", step5)

    def test_the_address_is_written_with_dots_or_dashes_after_any_prefix(self):
        for name in (f"cake.{ADDRESS}", ADDRESS, f"cake-{ADDRESS}", "cake.203.0.113.10", "stats.cake.203.0.113.10"):
            for domain in DOMAINS:
                with self.subTest(name=name, domain=domain):
                    self.assertNotIn("A record", self.step5(f"https://{name}.{domain}"))

    def test_a_name_under_such_a_domain_without_an_address_keeps_the_dns_record(self):
        """The service answers only a name that holds an address: cake.mysite.sslip.io leads nowhere, and step 5 told
        the site owner it needed no record. Without a whole address right before the domain, the name is any other
        name, and doctor on the server finds where its DNS record leads."""
        for name in ("cake.mysite", "cake.203-0-113", "cake.203-0-113-300", "cake.203-0.113-10", f"cake.{ADDRESS}x"):
            for domain in DOMAINS:
                with self.subTest(name=name, domain=domain):
                    self.assertIn("A record", self.step5(f"https://{name}.{domain}"))

    def test_a_name_that_only_looks_alike_keeps_the_dns_record(self):
        for public_url in (f"https://cake.{DOMAINS[0]}.brewbean.example", f"https://cake.not{DOMAINS[0]}"):
            with self.subTest(public_url=public_url):
                self.assertIn("A record", self.step5(public_url))

    def test_the_domains_are_data_not_code(self):
        with open(site_setup.__file__, encoding="utf-8") as f:
            code = f.read()
        for domain in DOMAINS:
            self.assertNotIn(domain, code)

    def test_the_section_the_step_points_to_is_in_server_md(self):
        self.assertIn(f"\n### {SECTION}\n", read(SERVER_MD))


if __name__ == "__main__":
    unittest.main()
