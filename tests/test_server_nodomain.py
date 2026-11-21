"""SERVER.md's "Sites without their own domain": a site that has only its platform's address, such as you.github.io,
gets a free name for AgentCake's server, with no domain to buy and no DNS record to add.

    python3 -I -m unittest discover -s tests -v      (from the AgentCake folder)

The section once said only "use another domain that you control", which meant buying one. sslip.io answers a name
that holds an IPv4 address, written with dashes for its dots, with that address: cake.<the server's address>.sslip.io
points at the server as step 2's DNS record would, and Caddy obtains its certificate for that name as for any other.
The section gives that name first, with the commands that differ from steps 3 and 5: the name in deploy/Caddyfile in
place of the site there, the same name in public_url, and site_domain set to the platform's address. Because the
name holds the address, the section says that the server needs a static IP address. sslip.io is a third party's free
service, so the section then lists what that means (its operators decide where the name points; if it stops, no visit
is recorded) and keeps a domain of your own for a site that relies on AgentCake over time; INSTALL.md's line that
links here tells the coding agent to explain this to the site owner in its plan. test_server_docs.py checks the rest
of SERVER.md; nothing here goes online.
"""
import ipaddress
import os
import re
import sys
import unittest
from urllib.parse import urlsplit

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from cake_server import ROOT, SERVER_MD, read  # noqa: E402  (needs the path above)
from deploy_files import caddyfile  # noqa: E402
from test_server_docs import PLACEHOLDERS, agentcake_commands, code_block_lines, section  # noqa: E402

HEADING = "Sites without their own domain"
# A name of sslip.io's: labels of your own, then an IPv4 address with dashes for its dots (sslip.io's own examples,
# such as www.192-168-0-1.sslip.io, resolve to the address in the name).
FREE_NAME = re.compile(r"\b((?:[a-z0-9-]+\.)+?)(\d{1,3}(?:-\d{1,3}){3})\.sslip\.io\b")
# RFC 5737: the IPv4 ranges for examples in documents, so the example is nobody's server.
EXAMPLE_RANGES = [ipaddress.ip_network(r) for r in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]
CADDYFILE_SED = re.compile(r"sed -i 's/([^/]+)/([^/]+)/' deploy/Caddyfile")
OWN_DOMAIN = re.compile(r"\bdomain (?:that )?you (?:control|own)\b")
INSTALL_MD = os.path.join(ROOT, "INSTALL.md")
ANCHOR = "SERVER.md#sites-without-their-own-domain"


def fill(text):
    """text with each of SERVER.md's placeholders replaced by the made-up value test_server_docs.py runs it with."""
    for placeholder, value in PLACEHOLDERS.items():
        text = text.replace(placeholder, value)
    return text


def caddyfile_names(markdown, site):
    """The names that the `sed` commands of a text write into deploy/Caddyfile in place of its site."""
    return {fill(name) for line in code_block_lines(markdown) for pattern, name in CADDYFILE_SED.findall(line)
            if pattern == re.escape(site)}


def settings(markdown):
    """{setting: [values]} of the `agentcake config set` commands in a text's code blocks."""
    found = {}
    for command in agentcake_commands(markdown):
        if command[:2] == ["config", "set"] and len(command) == 4:
            found.setdefault(command[2], []).append(command[3])
    return found


class SitesWithoutTheirOwnDomain(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server_md = read(SERVER_MD)
        cls.text = section(cls.server_md, HEADING, level=3)
        cls.site = caddyfile()["site"]
        cls.names = {match.group(0) for match in FREE_NAME.finditer(cls.text)}

    def free_name(self):
        self.assertEqual(len(self.names), 1, "one sslip.io name for AgentCake's server, the same everywhere")
        return next(iter(self.names))

    def test_the_section_gives_a_free_name_made_from_the_servers_address(self):
        dashed = FREE_NAME.fullmatch(self.free_name()).group(2)
        address = ipaddress.ip_address(dashed.replace("-", "."))
        self.assertTrue(any(address in network for network in EXAMPLE_RANGES), "an example address of RFC 5737")
        self.assertIn(str(address), self.text, "the address with its dots, so the reader sees how the name is made")

    def test_the_free_name_replaces_the_subdomain_of_steps_3_and_5(self):
        """The Caddyfile serves the name, public_url is the name, and site_domain stays the platform's address."""
        name = self.free_name()
        self.assertEqual(caddyfile_names(self.text, self.site), {name}, "step 3's sed, with the free name")
        found = settings(self.text)
        self.assertEqual(found.get("public_url"), [f"https://{name}"])
        platform = re.findall(r"`([a-z0-9.-]+\.[a-z]+)`", self.text.strip().split("\n\n")[0])
        self.assertIn(found.get("site_domain", [None])[0], platform, "the site's address from its platform")

    def test_every_public_url_of_server_md_is_a_name_the_caddyfile_serves(self):
        public_urls = settings(self.server_md).get("public_url", [])
        self.assertGreater(len(public_urls), 1, "step 5's and this section's")
        hosts = {urlsplit(url).hostname for url in public_urls}
        self.assertLessEqual(hosts, caddyfile_names(self.server_md, self.site))

    def test_the_free_name_comes_first_and_the_section_says_what_it_needs(self):
        first = self.text.index(self.free_name())
        own = OWN_DOMAIN.search(self.text)
        self.assertIsNotNone(own, "a domain of your own stays a choice")
        self.assertLess(first, own.start(), "the free name comes first")
        self.assertRegex(self.text, r"\bstatic IP address", "the name holds the address: it must not change")

    def test_the_risks_of_a_third_partys_name_come_before_your_own_domain(self):
        """A list after the commands: who runs sslip.io decides where the name points, what a script from elsewhere can
        do on the pages and that the server's data isn't affected; then a domain of your own, with a CAA record."""
        risks = re.search(r"((?:^- .*\n(?:  .*\n)*)+)", self.text[self.text.index("agentcake config set public_url"):], re.M)
        self.assertIsNotNone(risks, "the risks, as a list after the commands")
        self.assertRegex(risks.group(1), r"\bthird party\b|\bwhoever runs\b|\boperators?\b")
        self.assertRegex(risks.group(1), r"\bmasking\b", "AgentCake's masking is its own script's, not another one's")
        self.assertRegex(risks.group(1), r"\b(?:isn't|doesn't|aren't) affect|\bdoesn't give anyone access",
                         "the data on the server isn't reached")
        self.assertLess(self.text.index(risks.group(1)), OWN_DOMAIN.search(self.text).start())
        self.assertRegex(self.text, r"\btrial\b", "the name suits a trial; a domain of your own, a site that relies on it")
        self.assertIn("CAA record", self.text, "your own domain can limit which authorities issue its certificates")

    def test_install_md_has_the_agent_explain_the_free_name_to_the_site_owner(self):
        bullet, = [block for block in re.split(r"\n(?=- |\n)", read(INSTALL_MD)) if ANCHOR in block]
        for word in ("sslip.io", "risk", "site owner"):  # before the setup, so the site owner hears it before approving
            self.assertIn(word, bullet)


if __name__ == "__main__":
    unittest.main()
