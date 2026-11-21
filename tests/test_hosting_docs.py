"""docs/hosting.md, the hosting reference, against the documents it links to and the code it names.

    python3 -I -m unittest discover -s tests -v      (from the AgentCake folder)

Every link to a file of the repository exists, and every link to a section names a heading of that file, the way
GitHub makes a heading's anchor; every `agentcake` command it shows is one the command line lists; each framework that
`agentcake setup --print --site` recognizes has its row, which names the middleware setup adds for it and links to its
README; the server it asks for is the one SERVER.md's first step asks for.

What it says about money: the page opens with what AgentCake costs, one row per case, free and paid, the domains in
the order an owner should choose them (one they already have, an sslip.io name, a new .com); the server range there is
the range of the server costs table, so the two can't drift apart; the hosting platforms table gives only what each
platform adds, never the server's price again, and says so when a platform adds nothing; every price comes with a link
to where it was read, and every section with prices says on which day they were read.
"""
import json
import os
import re
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from cake_server import ROOT, SERVER_MD, read  # noqa: E402  (needs the path above)
from test_install_docs import LINK, command_words, documented_commands, listed_forms  # noqa: E402

HOSTING_MD = os.path.join(ROOT, "docs", "hosting.md")
FRAMEWORKS = os.path.join(ROOT, "agentcake", "data", "frameworks.json")
# The row of each framework that setup recognizes by its name in data/frameworks.json; WordPress has rows of its own.
ROW_OF = {"next-app": "Next.js", "next-pages": "Next.js", "express": "Express", "hono": "Hono", "flask": "Flask",
          "fastapi": "FastAPI", "django": "Django", "php": "PHP", "wordpress": "Self-hosted WordPress"}
HEADING = re.compile(r"^#{1,6} (.+?)\s*#*$", re.M)
FENCE = re.compile(r"^[ \t]*```.*?^[ \t]*```", re.M | re.S)
SERVER_FIGURES = re.compile(r"\d+ vCPU|\d+ GB of memory|\d+ to \d+ GB|public IPv4 address")
DOLLARS = re.compile(r"^\$(\d+(?:\.\d+)?)$")
COSTS = "What AgentCake costs"  # the page's first section, which INSTALL.md links to by its anchor
PLATFORMS, PLANS, SERVERS = "Hosting platforms", "Platform plans", "Server costs"
# A price: a currency sign and a number ("$11.17", "€5.49"); one that is not zero needs the provider's own page.
PRICE = re.compile(r"[$€](\d[\d,]*(?:\.\d+)?)")
SERVER_RANGE = re.compile(r"\$(\d+(?:\.\d+)?) to \$(\d+(?:\.\d+)?)")
WEB_LINK = re.compile(r"\]\(https://[^)\s]+\)")
READ_DATE = re.compile(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
                       r" \d{1,2}, \d{4}\b")
# The cases the costs table names, by a word of their first cell: the free ones, then the paid ones.
FREE_CASES = ("computer", "Oracle", "existing domain", "sslip.io", "certificate", "City database", "middleware",
              "Traffic")
PAID_CASES = ("another provider", ".com", "CloudFront", "load balancer", "platform plan")
DOMAIN_ORDER = ("existing domain", "sslip.io", ".com")  # the owner's own domain, then an sslip.io name, then a new one
# A platform row that adds nothing says so ("None.", "The page script adds no cost, ...", "There's no extra cost on
# ...", or "—" for a platform AgentCake can't use); otherwise it gives a price.
NO_EXTRA_COST = re.compile(r"^(?:None\b|—$)|\bno (?:extra )?cost\b|\bis free\b")
# A cost per page views is an estimate from measured page views: the section that gives one says how long a view lasts.
PER_VIEWS = re.compile(r"per 10,000 page views")
VIEW_LENGTH = re.compile(r"one minute on each page")


def anchor(heading):
    """GitHub's anchor for a heading: lower case, punctuation dropped (the hyphen and underscore stay), spaces to
    hyphens. Inline code and links count by their text."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading).replace("`", "")
    return re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")


def anchors(markdown):
    """Every anchor of a Markdown text, with -1, -2 … after a repeated one, as GitHub numbers them."""
    found, seen = set(), {}
    for heading in HEADING.findall(FENCE.sub("", markdown)):
        slug = anchor(heading)
        found.add(f"{slug}-{seen[slug]}" if slug in seen else slug)
        seen[slug] = seen.get(slug, 0) + 1
    return found


def link_problems(path, markdown):
    """A relative link whose file is missing, or whose #section names no heading of that file."""
    problems = []
    for target in LINK.findall(markdown):
        if re.match(r"^(https?:|mailto:)", target):
            continue
        file_part, _, section = target.partition("#")
        linked = os.path.normpath(os.path.join(os.path.dirname(path), file_part)) if file_part else path
        if not os.path.isfile(linked):
            problems.append(f"{target}: no such file")
        elif section and section not in anchors(read(linked)):
            problems.append(f"{target}: no such section")
    return problems


def table_rows(markdown):
    """{first cell: the whole row} for each row of the document's tables."""
    rows = {}
    for line in markdown.splitlines():
        if line.startswith("| ") and not set(line) <= set("|-: "):
            rows.setdefault(line.split("|")[1].strip(), line)
    return rows


def sections(markdown):
    """[(heading, text)] of each level-2 section, in order; code blocks left out."""
    parts = re.split(r"^## (.+)$", FENCE.sub("", markdown), flags=re.M)
    return list(zip(parts[1::2], parts[2::2]))


def section_text(markdown, heading):
    return dict(sections(markdown))[heading]


def cells(row):
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def table(text):
    """(header cells, [row cells]) of the first table in a section; group rows (a bold first cell, which may have a
    note beside it) left out."""
    first = re.search(r"^\|.*(?:\n\|.*)*", text, re.M).group(0)  # the first run of table lines
    lines = first.splitlines()
    rows = [cells(line) for line in lines[2:]]
    return cells(lines[0]), [row for row in rows if not re.fullmatch(r"\*\*.+\*\*", row[0])]


def units(text):
    """Each table row, list item and paragraph of a section: what a price and its link have to share."""
    found = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.strip().splitlines()
        if lines and lines[0].startswith("|"):
            found += [line for line in lines if not set(line) <= set("|-: ")]
        else:
            found += re.split(r"\n(?=- )", block.strip())
    return [unit for unit in found if unit.strip()]


def prices(text):
    return [float(found.replace(",", "")) for found in PRICE.findall(text)]


def names(row, word):
    """Whether a row's first cell names a case, in any case of letters ("Load balancer path rules")."""
    return word.lower() in row[0].lower()


class Anchors(unittest.TestCase):
    def test_an_anchor_is_made_the_way_github_makes_it(self):
        self.assertEqual(anchor("The dashboard: 127.0.0.1 only, through a tunnel"),
                         "the-dashboard-127001-only-through-a-tunnel")
        self.assertEqual(anchor("Sites behind Cloudflare's proxy"), "sites-behind-cloudflares-proxy")
        self.assertEqual(anchor("Express, Connect or node:http"), "express-connect-or-nodehttp")
        self.assertEqual(anchors("## Settings\n\n## Settings\n"), {"settings", "settings-1"})

    def test_a_link_to_a_missing_section_or_file_is_found(self):
        text = "[a](../SERVER.md#no-such-heading) [b](../NO_SUCH_FILE.md) [c](#server-costs)"
        self.assertEqual(link_problems(HOSTING_MD, text),
                         ["../SERVER.md#no-such-heading: no such section", "../NO_SUCH_FILE.md: no such file"])


class Reading(unittest.TestCase):
    """How the money tests read the page: sections, tables, units and prices."""

    TEXT = ("# Title\n\nIntro.\n\n## First\n\n| Case | Cost |\n|---|---|\n| **Group** | A note. |\n| A | $0 |\n"
            "| B | [$11.17](https://example.com/) a year |\n\nPrices are from November 20, 2026.\n\n"
            "| Part | Price |\n|---|---|\n| C | $2.40 |\n\n"
            "## Second\n\n- One: €5.49 in Helsinki.\n- Two: $1,200.\n\n```\n## Not a heading\n```\n")

    def test_level_two_sections_come_in_order_without_code_blocks(self):
        self.assertEqual([heading for heading, _ in sections(self.TEXT)], ["First", "Second"])

    def test_a_sections_table_is_its_first_one_without_its_group_rows(self):
        header, rows = table(section_text(self.TEXT, "First"))
        self.assertEqual(header, ["Case", "Cost"])
        self.assertEqual([row[0] for row in rows], ["A", "B"])

    def test_a_unit_is_a_table_row_a_list_item_or_a_paragraph(self):
        self.assertEqual(units(section_text(self.TEXT, "Second")), ["- One: €5.49 in Helsinki.", "- Two: $1,200."])
        self.assertIn("Prices are from November 20, 2026.", units(section_text(self.TEXT, "First")))

    def test_prices_are_read_in_dollars_and_euros(self):
        self.assertEqual(prices(self.TEXT), [0.0, 11.17, 2.4, 5.49, 1200.0])
        self.assertRegex("Prices are from November 20, 2026.", READ_DATE)
        self.assertNotRegex("Prices are from 2026-11-20.", READ_DATE)


class HostingReference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hosting = read(HOSTING_MD)
        cls.rows = table_rows(cls.hosting)

    def test_links_to_files_and_sections_exist(self):
        self.assertEqual(link_problems(HOSTING_MD, self.hosting), [])

    def test_server_md_links_to_this_page(self):
        self.assertIn("(docs/hosting.md)", read(SERVER_MD))
        self.assertEqual(link_problems(SERVER_MD, "[Hosting reference](docs/hosting.md)"), [])

    def test_every_agentcake_command_shown_is_one_the_command_line_lists(self):
        forms = listed_forms()
        commands = documented_commands(self.hosting)
        self.assertTrue(commands)
        for command in commands:
            words = command_words(command)
            self.assertTrue(any(tuple(words[:len(form)]) == form for form in forms), command)

    def test_each_framework_setup_recognizes_has_a_row_with_its_middleware(self):
        with open(FRAMEWORKS, encoding="utf-8") as f:
            frameworks = [spec for spec in json.load(f)["frameworks"] if spec.get("middleware")]
        self.assertEqual({spec["name"] for spec in frameworks}, set(ROW_OF))
        for spec in frameworks:
            row = self.rows[ROW_OF[spec["name"]]]
            middleware = spec["middleware"]
            with self.subTest(spec["name"]):
                if "plugin" not in middleware:
                    self.assertTrue(any(f"`{name}`" in row for name in [middleware["name"], *middleware.get("files", [])]))
                self.assertIn(f"(../edge/{middleware['readme']}", row)

    def test_the_server_it_asks_for_is_the_one_server_md_asks_for(self):
        step = re.search(r"^### 1\. Get a server\n(.*?)^### ", read(SERVER_MD), re.M | re.S).group(1)
        needs = re.search(r"^## Requirements for a public website\n(.*?)^## ", self.hosting, re.M | re.S).group(1)
        self.assertEqual(SERVER_FIGURES.findall(" ".join(needs.split())), SERVER_FIGURES.findall(" ".join(step.split())))


class WhatItCosts(unittest.TestCase):
    """The money on the page: one place for each price, with where and when it was read."""

    @classmethod
    def setUpClass(cls):
        cls.hosting = read(HOSTING_MD)
        cls.sections = sections(cls.hosting)
        # without the section every test below fails on its own, each saying what is missing
        cls.cases = table(section_text(cls.hosting, COSTS))[1] if COSTS in dict(cls.sections) else []

    def server_prices(self):
        """The dollar prices of the server costs table, provider by provider."""
        _, rows = table(section_text(self.hosting, SERVERS))
        found = [DOLLARS.match(row[-1]) for row in rows]
        return [float(match.group(1)) for match in found if match]

    def case(self, word):
        return next(row for row in self.cases if names(row, word))

    def test_the_page_opens_with_what_agentcake_costs(self):
        self.assertEqual(self.sections[0][0], COSTS)
        self.assertLessEqual({"what-agentcake-costs", "server-costs", "platform-plans"}, anchors(self.hosting))

    def test_the_costs_table_has_a_row_for_each_free_and_each_paid_case(self):
        for word in FREE_CASES + PAID_CASES:
            with self.subTest(word):
                self.assertTrue(any(names(row, word) for row in self.cases))

    def test_the_free_cases_cost_nothing(self):
        for word in FREE_CASES:
            with self.subTest(word):
                self.assertEqual(prices(self.case(word)[1])[:1], [0.0])

    def test_the_domains_come_in_the_order_an_owner_chooses_them(self):
        places = [next(n for n, row in enumerate(self.cases) if names(row, word)) for word in DOMAIN_ORDER]
        self.assertEqual(places, sorted(places))

    def test_the_server_range_is_the_range_of_the_server_costs_table(self):
        found = SERVER_RANGE.search(self.case("another provider")[1])
        self.assertIsNotNone(found)
        self.assertIn("(#server-costs)", self.case("another provider")[1])
        paid = [price for price in self.server_prices() if price > 0]
        self.assertEqual((float(found.group(1)), float(found.group(2))), (min(paid), max(paid)))
        self.assertIn(0.0, self.server_prices())  # the free tier, which has its own row
        self.assertEqual(prices(self.case("Oracle")[1]), [0.0])

    def test_the_platforms_table_gives_only_what_a_platform_adds(self):
        header, rows = table(section_text(self.hosting, PLATFORMS))
        self.assertIn("Extra cost", header[-1])
        server_prices = {price for price in self.server_prices() if price > 0}
        for row in rows:
            with self.subTest(row[0]):
                cost = row[-1]
                self.assertTrue(cost)
                self.assertNotIn("#server-costs", cost)
                self.assertFalse(server_prices & set(prices(cost)), cost)
                # no range between two server prices ("$0 to $12.18"); a range per 10,000 page views is the platform's
                ranges = [{float(low), float(high)} for low, high in SERVER_RANGE.findall(cost)]
                self.assertFalse([found for found in ranges if found <= set(self.server_prices())], cost)

    def test_a_range_of_two_server_prices_is_caught_and_a_traffic_range_is_not(self):
        server = set(self.server_prices())
        self.assertLessEqual({float(v) for v in SERVER_RANGE.search("costs $0 to $12.18.").groups()}, server)
        self.assertFalse({float(v) for v in SERVER_RANGE.search("about $0.13 to $0.41 per").groups()} <= server)

    def test_a_platform_that_adds_nothing_says_so(self):
        _, rows = table(section_text(self.hosting, PLATFORMS))
        for row in rows:
            with self.subTest(row[0]):
                self.assertTrue(prices(row[-1]) or NO_EXTRA_COST.search(row[-1]), row[-1])

    def test_every_price_links_to_where_it_was_read(self):
        """A price that isn't zero links to the provider's page; a free one links to its source or AgentCake's own
        document."""
        for heading, text in self.sections:
            for unit in units(text):
                found = prices(unit)
                if not found:
                    continue
                with self.subTest(heading, unit=unit[:80]):
                    self.assertTrue(LINK.search(unit), unit)
                    if any(found):
                        self.assertRegex(unit, WEB_LINK)

    def test_every_section_with_page_view_estimates_says_how_long_a_view_lasts(self):
        for heading, text in self.sections:
            if PER_VIEWS.search(text):
                with self.subTest(heading):
                    self.assertRegex(text, VIEW_LENGTH)

    def test_every_section_with_prices_says_when_they_were_read(self):
        for heading, text in self.sections:
            if prices(text):
                with self.subTest(heading):
                    self.assertRegex(text, READ_DATE)


if __name__ == "__main__":
    unittest.main()
