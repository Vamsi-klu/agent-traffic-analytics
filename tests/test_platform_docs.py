"""What SERVER.md, INSTALL.md and docs/hosting.md say about a platform or a setup option, against the code that decides it.

    python3 -I -m unittest discover -s tests -v      (from the AgentCake folder)

Three facts the documents had drifted from, found when docs/hosting.md was written. A Next.js row names the files that
`agentcake setup --print --site` edits (data/frameworks.json): one file of each router that setup recognizes, and no
other file. With Cloudflare's proxy on AgentCake's record, the shipped Caddyfile reads each visitor's address and doctor
answers with a warning, not a failure, so a document can recommend DNS only but never require it. The path option's
server doesn't need an external address for connections that come in, but it does need a way out: Docker pulls the base
image when it builds AgentCake's image, and AgentCake downloads the lists and the city database once a month
(updates.py, with lists_auto_update on by default).
"""
import json
import os
import re
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from agentcake import config, doctor_lines, doctor_public  # noqa: E402  (needs the path above)
from cake_server import PREFIX, ROOT, SERVER_MD, read  # noqa: E402
from deploy_files import caddyfile, dockerfile_instructions  # noqa: E402
from doctor_public_fixtures import FakeNet, cdn_addresses  # noqa: E402
from test_hosting_docs import FENCE, HOSTING_MD, table_rows  # noqa: E402
from test_server_docs import section  # noqa: E402

INSTALL_MD = os.path.join(ROOT, "INSTALL.md")
FRAMEWORKS = os.path.join(ROOT, "agentcake", "data", "frameworks.json")
DOCUMENTS = {"SERVER.md": SERVER_MD, "INSTALL.md": INSTALL_MD, "docs/hosting.md": HOSTING_MD}
NEXT_ROW = "Next.js"
NEXT_SCRIPT = "next"  # frameworks.json: the "script" of every Next.js router
SOURCE_FOLDER = "src/"  # Next.js reads app/ and pages/ from src/ too; a document names the file without it
FILE_PATH = re.compile(r"`([\w.-]+/[\w./-]+)`")  # a path in code: app/layout.tsx, pages/_app
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
BLANK_LINE = re.compile(r"\n\s*\n")
REQUIRED = re.compile(r"\b(?:must|required?|requires)\b", re.I)
PROXIED_HOST = "cake.example.com"
HTTPS_PORT = 443  # protocol: the port of an https:// address without one


def stem(path):
    """A file's path without the src/ folder and the extension: what a document names for every variant setup reads."""
    path = path[len(SOURCE_FOLDER):] if path.startswith(SOURCE_FOLDER) else path
    return os.path.splitext(path)[0]


def next_routers():
    """{framework name: the stems of the files setup adds the page script to}, for each Next.js router."""
    with open(FRAMEWORKS, encoding="utf-8") as f:
        frameworks = json.load(f)["frameworks"]
    return {spec["name"]: {stem(path) for path in spec["detect"]["paths"]}
            for spec in frameworks if spec.get("script") == NEXT_SCRIPT}


def where_to_add(markdown):
    """The second cell of a document's Next.js row: where the page script goes."""
    return table_rows(markdown)[NEXT_ROW].split("|")[2]


def sentences_about(markdown, words):
    """Each sentence of a document's paragraphs, list items and table cells that contains words, without Markdown
    emphasis; code blocks left out."""
    texts = []
    for block in BLANK_LINE.split(FENCE.sub("", markdown.replace("**", ""))):
        lines = block.strip().splitlines()
        texts += [cell for line in lines for cell in line.split("|")] if lines and lines[0].startswith("|") else [block]
    return [sentence for found in texts for sentence in SENTENCE_END.split(" ".join(found.split())) if words in sentence]


class NextJsRows(unittest.TestCase):
    def test_a_file_is_named_without_its_folder_under_src_and_its_extension(self):
        self.assertEqual(stem("src/pages/_app.tsx"), "pages/_app")
        self.assertEqual(stem("app/layout"), "app/layout")
        self.assertEqual(FILE_PATH.findall("Add it to `app/layout` or `pages/_app`. The [`cakeNext`](x) middleware"),
                         ["app/layout", "pages/_app"])

    def test_setup_recognizes_both_routers(self):
        self.assertEqual(len(next_routers()), 2)

    def test_each_documents_nextjs_row_names_the_files_setup_edits(self):
        """pages/_document runs only on the server, so setup adds the page script to pages/_app, as Next.js's own
        guide does for a script that every page loads."""
        routers = next_routers()
        files = set().union(*routers.values())
        for name, path in DOCUMENTS.items():
            named = {stem(found) for found in FILE_PATH.findall(where_to_add(read(path)))}
            with self.subTest(name):
                self.assertTrue(named)
                self.assertLessEqual(named, files)
                for router, stems in routers.items():
                    self.assertTrue(named & stems, f"{name} names no file of {router}")


class CloudflareProxy(unittest.TestCase):
    def test_a_proxied_record_works_with_the_shipped_caddyfile_and_doctor_only_warns(self):
        """What makes DNS only a recommendation: behind Cloudflare, Caddy reads the visitor's address."""
        self.assertRegex(caddyfile()["global"], r"client_ip_headers[^\n]*\bCF-Connecting-IP\b")
        net = FakeNet(None, {PROXIED_HOST: cdn_addresses(1)}, {})
        line, _ = doctor_public.dns_check(net, PROXIED_HOST, HTTPS_PORT, {"host": PROXIED_HOST, "prefix": PREFIX})
        self.assertEqual(line[1], doctor_lines.WARN)

    def test_a_requirement_is_found_however_it_is_worded(self):
        for sentence in ("the record must be DNS only (gray cloud).", "DNS only is required.",
                         "It requires DNS only."):
            self.assertRegex(sentence, REQUIRED)
        self.assertNotRegex("DNS only is the recommended setting.", REQUIRED)

    def test_a_sentence_is_read_from_its_own_paragraph_or_table_cell(self):
        markdown = "| DNS record | Required |\n| Proxy | DNS only |\n\n- Use **DNS only**,\n  as a rule.\n\n```\nDNS only\n```\n"
        self.assertEqual(sentences_about(markdown, "DNS only"), ["DNS only", "- Use DNS only, as a rule."])

    def test_no_document_requires_dns_only(self):
        for name, path in DOCUMENTS.items():
            for sentence in sentences_about(read(path), "DNS only"):
                with self.subTest(name, sentence=sentence):
                    self.assertNotRegex(sentence, REQUIRED)

    def test_install_md_recommends_dns_only_as_server_md_does(self):
        for path in (INSTALL_MD, SERVER_MD):
            with self.subTest(os.path.basename(path)):
                self.assertTrue(any("recommend" in sentence for sentence in sentences_about(read(path), "DNS only")))


class PathOptionFirewall(unittest.TestCase):
    """The path option's server: nothing comes in but from the load balancer and through IAP, and it still goes out."""

    @classmethod
    def setUpClass(cls):
        cls.firewall = " ".join(section(read(SERVER_MD), "Firewall for the path option", level=3).split())

    def test_it_doesnt_say_the_server_needs_no_external_address(self):
        self.assertNotRegex(self.firewall, r"needs no external (?:IP )?address")

    def test_it_says_the_server_needs_outbound_access_through_an_address_or_nat(self):
        self.assertRegex(self.firewall, r"\boutbound\b")
        self.assertRegex(self.firewall, r"\bNAT\b")

    def test_it_names_the_base_image_that_the_build_pulls(self):
        self.assertIn("FROM", [instruction for instruction, _ in dockerfile_instructions()])
        self.assertRegex(self.firewall, r"\bbase image")

    def test_it_names_the_monthly_update_that_is_on_by_default(self):
        self.assertIs(config.DEFAULTS["lists_auto_update"], True)
        self.assertRegex(self.firewall, r"once a month|monthly")


if __name__ == "__main__":
    unittest.main()
