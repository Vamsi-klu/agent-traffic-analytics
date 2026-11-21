"""The repository's community files against README, the release and the command line.

    python3 -I -m unittest discover -s tests -v      (from the AgentCake folder)

What GitHub shows beside README (SECURITY.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, the issue forms and the pull request
template in .github/), the release notes (CHANGELOG.md), the file a coding agent reads first (llms.txt, in
llmstxt.org's format) and the questions page (docs/FAQ.md) are checked so that they stay true as AgentCake changes:
one address for private reports, README's; every `agentcake` command they show is one the command line lists; every
link to a file of the repository exists, llms.txt's at this release's tag; CHANGELOG's newest entry is this version
(or the next one's, marked unreleased, on top of it);
every question on the FAQ page is a heading that ends with "?"; each issue form has GitHub's required keys and warns
against pasting visitors' data; the social preview is the size GitHub asks for. No published document (README and its
translation included) offers as an agent AgentCake recognizes a product it only watches the marks of: no list entry
names those, so their sessions are Unnamed.
"""
import json
import glob
import os
import re
import struct
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from agentcake.wording import product  # noqa: E402  (needs the path above)
from cake_server import ROOT, read  # noqa: E402
from test_install_docs import (INSTALL_MD, LINK, README_MD, README_ZH, command_words, documented_commands,
                               listed_forms, release_tag, repositories, section)

SECURITY_MD = os.path.join(ROOT, "SECURITY.md")
CONTRIBUTING_MD = os.path.join(ROOT, "CONTRIBUTING.md")
CODE_OF_CONDUCT_MD = os.path.join(ROOT, "CODE_OF_CONDUCT.md")
CHANGELOG_MD = os.path.join(ROOT, "CHANGELOG.md")
LLMS_TXT = os.path.join(ROOT, "llms.txt")
FAQ_MD = os.path.join(ROOT, "docs", "FAQ.md")
EVAL_README = os.path.join(ROOT, "eval", "README.md")
PULL_REQUEST_TEMPLATE = os.path.join(ROOT, ".github", "pull_request_template.md")
ISSUE_TEMPLATES = os.path.join(ROOT, ".github", "ISSUE_TEMPLATE")
ISSUE_CONFIG = os.path.join(ISSUE_TEMPLATES, "config.yml")
SOCIAL_PREVIEW = os.path.join(ROOT, "docs", "assets", "readme", "social-preview.png")
MARKDOWN = (SECURITY_MD, CONTRIBUTING_MD, CODE_OF_CONDUCT_MD, CHANGELOG_MD, FAQ_MD, PULL_REQUEST_TEMPLATE)
MARKS_FILE = os.path.join(ROOT, "agentcake", "data", "agent_markers.json")
NAMES_FILE = os.path.join(ROOT, "agentcake", "data", "lists", "names.json")
# What people read about what AgentCake recognizes; eval/README.md is left out: it records what was tested.
NAMING_DOCS = (README_MD, README_ZH, FAQ_MD, LLMS_TXT, CHANGELOG_MD, CONTRIBUTING_MD, INSTALL_MD,
               *(os.path.join(ROOT, *name.split("/")) for name in (
                   "docs/collect-format.md", "DESIGN.md", "SERVER.md", "PRIVACY.md", "AGENTS.md", "edge/node/README.md",
                   "edge/php/README.md", "edge/python/README.md", "edge/wordpress/agentcake/README.md")))

MAILTO = re.compile(r"mailto:([^)\s>]+)")
LLMS_LINK = re.compile(r"^- \[[^\]]+\]\((\S+)\)(?:: .+)?$")  # llmstxt.org: "- [name](url)" and optional ": notes"
FORM_KEYS = ("name", "description", "body")  # protocol: GitHub's issue form schema, its required top-level keys
CONFIG_KEYS = ("blank_issues_enabled", "contact_links")  # protocol: GitHub's issue template chooser, config.yml
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"  # protocol: the PNG file signature
SOCIAL_PREVIEW_SIZE = (1280, 640)  # protocol: GitHub's size "for best display" of a social preview
SOCIAL_PREVIEW_MAX_BYTES = 1_000_000  # protocol: GitHub takes a social preview under 1 MB
PRIVACY_WARNING = "Do not paste"  # each issue form says it before the reporter writes anything
# The FAQ's accuracy figures, "X of Y" (or "X of its Y"), each one eval/README.md's "README's figures" gives; a median
# may have decimals. README gives only the totals of the test data that the figures count over.
FIGURE = re.compile(r"\b(\d+(?:,\d{3})*) of (?:its )?(\d+(?:,\d{3})*)\b")
MEDIAN = re.compile(r"a median of \d+(?:\.\d+)? seconds")
README_TOTAL = re.compile(r"\b(\d+(?:,\d{3})*) (?:agent|human) sessions")


def issue_forms():
    """The issue forms of .github/ISSUE_TEMPLATE/: every YAML file but the chooser's config.yml."""
    return sorted(path for path in glob.glob(os.path.join(ISSUE_TEMPLATES, "*.yml")) if path != ISSUE_CONFIG)


def top_level_keys(yaml_text):
    """The keys of a YAML file's top level (lines that start a key with no indent)."""
    return re.findall(r"^([A-Za-z_][\w-]*):", yaml_text, re.M)


def png_size(path):
    """(width, height) from a PNG's IHDR chunk, which follows the signature."""
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != PNG_SIGNATURE or head[12:16] != b"IHDR":
        raise AssertionError(f"{path} is not a PNG")
    return struct.unpack(">II", head[16:24])


def version_parts(version):
    """A version's numbers, to compare two versions: "0.5.10" is later than "0.5.9"."""
    return tuple(int(part) for part in version.split("."))


class CommunityDocuments(unittest.TestCase):
    """The files a visitor of the repository's page reads after README say the same as README and the release."""

    @classmethod
    def setUpClass(cls):
        cls.version, cls.tag = release_tag()
        cls.repository, = repositories(read(INSTALL_MD))
        cls.readme_address, = MAILTO.findall(section(read(README_MD), "Help and contributing"))

    def test_one_address_for_private_reports(self):
        """README's security line, SECURITY.md and the code of conduct give the same private address."""
        for path in (SECURITY_MD, CODE_OF_CONDUCT_MD):
            self.assertEqual(set(MAILTO.findall(read(path))), {self.readme_address}, os.path.basename(path))

    def test_the_security_policy_keeps_reports_out_of_public_issues(self):
        policy = read(SECURITY_MD)
        for words in ("public issue", self.readme_address, "latest release"):
            self.assertIn(words, policy)

    def test_every_agentcake_command_shown_is_one_the_command_line_lists(self):
        forms = listed_forms()
        shown = MARKDOWN + (LLMS_TXT,) + tuple(issue_forms())
        for path in shown:
            for command in documented_commands(read(path)):
                words = command_words(command)
                self.assertTrue(any(tuple(words[:len(form)]) == form for form in forms),
                                f"{os.path.relpath(path, ROOT)}: `{command}` is not in `agentcake help`")

    def test_links_to_files_of_the_repository_exist(self):
        for path in MARKDOWN:
            for target in LINK.findall(read(path)):
                if re.match(r"^(https?:|mailto:|#)", target):
                    continue
                local = os.path.join(os.path.dirname(path), target.split("#")[0])
                self.assertTrue(os.path.exists(local), f"{os.path.relpath(path, ROOT)} links to {target}, missing")

    def test_llms_txt_follows_llmstxt_org_and_points_at_this_release(self):
        """An H1 with the name, a one-line summary in a blockquote, paragraphs, then H2 sections that only list links;
        each link is a Markdown file of the repository at this release's tag, so it answers what was released."""
        lines = read(LLMS_TXT).splitlines()
        self.assertEqual(lines[0], f"# {product()['name']}")
        self.assertTrue(next(line for line in lines[1:] if line.strip()).startswith("> "))
        first_section = next(number for number, line in enumerate(lines) if line.startswith("## "))
        self.assertFalse([line for line in lines[1:first_section] if line.startswith("#")])
        raw = f"https://raw.githubusercontent.com/{self.repository}/{self.tag}/"
        links = []
        for line in (line for line in lines[first_section:] if line.strip() and not line.startswith("## ")):
            match = LLMS_LINK.match(line)
            self.assertTrue(match, f"llms.txt: not a link item: {line}")
            links.append(match.group(1))
        self.assertTrue(links)
        for url in links:
            self.assertTrue(url.startswith(raw), url)
            self.assertTrue(url.endswith(".md"), url)
            self.assertTrue(os.path.isfile(os.path.join(ROOT, url[len(raw):])), url)

    def test_contributing_and_the_pr_template_ask_for_eval_results_as_readme_does(self):
        """README's rule for a change to the rules or the model, before and after `agentcake eval` and no more humans
        classified as agents, is the contribution guide's and the pull request template's too."""
        for path in (README_MD, CONTRIBUTING_MD, PULL_REQUEST_TEMPLATE):
            with self.subTest(path=os.path.relpath(path, ROOT)):
                flat = " ".join(read(path).split())
                self.assertRegex(flat, r"`agentcake eval` results from before and after")
                self.assertRegex(flat, r"\bmust not (?:mis)?classify more humans as agents\b")

    def test_changelog_starts_with_this_version(self):
        """The newest entry is this version's; the next version's may come first while it isn't released, marked
        "(unreleased)", which it loses when the version changes to it."""
        (newest, unreleased), *older = re.findall(r"^## (\S+)( \(unreleased\))?$", read(CHANGELOG_MD), re.M)
        if unreleased:
            self.assertGreater(version_parts(newest), version_parts(self.version), f"{newest} is released already")
            newest = older[0][0]
        self.assertEqual(newest, self.version)

    def test_every_question_on_the_faq_page_is_a_heading(self):
        questions = re.findall(r"^## (.+)$", read(FAQ_MD), re.M)
        self.assertTrue(questions)
        for question in questions:
            self.assertTrue(question.endswith("?"), question)

    def test_the_faq_page_quotes_the_evaluations_figures(self):
        """The FAQ answers how accurate AgentCake is with numbers (the ones search and AI assistants quote): each is one
        eval/README.md's "README's figures" gives, over the totals README gives for the test data, so a new release's
        figures fail this test until the FAQ says the same."""
        faq = " ".join(read(FAQ_MD).split())
        evaluation = " ".join(section(read(EVAL_README), "README's figures").split())
        figures = FIGURE.findall(faq)
        self.assertTrue(figures)
        self.assertLessEqual(set(figures), set(FIGURE.findall(evaluation)))
        self.assertLessEqual(set(MEDIAN.findall(faq)), set(MEDIAN.findall(evaluation)))
        totals = set(README_TOTAL.findall(" ".join(read(README_MD).split())))
        self.assertTrue(totals)
        self.assertLessEqual(totals, {total for _, total in figures})

    def test_issue_forms_have_githubs_keys_and_warn_against_visitors_data(self):
        forms = issue_forms()
        self.assertTrue(forms)
        for path in forms:
            form = read(path)
            self.assertLessEqual(set(FORM_KEYS), set(top_level_keys(form)), os.path.basename(path))
            ids = re.findall(r"^\s+id: (\S+)$", form, re.M)
            self.assertEqual(len(ids), len(set(ids)), os.path.basename(path))
            self.assertIn(PRIVACY_WARNING, form, os.path.basename(path))

    def test_the_issue_chooser_links_to_files_of_this_repository(self):
        chooser = read(ISSUE_CONFIG)
        self.assertLessEqual(set(CONFIG_KEYS), set(top_level_keys(chooser)))
        blob = f"https://github.com/{self.repository}/blob/main/"
        targets = re.findall(r"url: (\S+)", chooser)
        self.assertTrue(targets)
        for url in targets:
            self.assertTrue(url.startswith(blob), url)
            self.assertTrue(os.path.isfile(os.path.join(ROOT, url[len(blob):].split("#")[0])), url)

    def test_the_social_preview_is_the_size_github_asks_for(self):
        self.assertEqual(png_size(SOCIAL_PREVIEW), SOCIAL_PREVIEW_SIZE)
        self.assertLess(os.path.getsize(SOCIAL_PREVIEW), SOCIAL_PREVIEW_MAX_BYTES)

    def test_no_document_offers_an_agent_agentcake_cannot_name(self):
        """The products of the mark table that no list entry names (their marks reach a reason at most, and the
        session is Unnamed) appear in no document about what AgentCake recognizes, in any spelling of their id."""
        with open(MARKS_FILE, encoding="utf-8") as f:
            products = {mark["product"] for mark in json.load(f)["markers"].values()}
        with open(NAMES_FILE, encoding="utf-8") as f:
            products -= {entry["id"] for entry in json.load(f)["names"]}
        self.assertTrue(products, "the mark table has products the lists don't name")
        for product in sorted(products):
            spelled = re.compile(r"(?<![\w-])" + r"[ _-]?".join(map(re.escape, product.split("-"))) + r"(?![\w-])", re.I)
            for path in NAMING_DOCS + tuple(issue_forms()):
                with self.subTest(os.path.relpath(path, ROOT), product=product):
                    self.assertIsNone(spelled.search(read(path)))


if __name__ == "__main__":
    unittest.main()
