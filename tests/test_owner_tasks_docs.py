"""Who does what when a coding agent sets AgentCake up, said alike in every document that a site owner or their coding
agent reads.

    python3 -I -m unittest discover -s tests -p test_owner_tasks_docs.py -v      (from the AgentCake folder)

INSTALL.md's table of tasks is where an installing agent reads it: once the site owner has seen its plan with each
monthly cost and approved it, the agent creates the server, adds the subdomain's DNS record, deploys the website and
pastes the script tag in a site builder, with each provider's command-line tool or its own browser tool. The site owner
signs in to their accounts, pays, accepts terms and registers on the local page. README.md and its Chinese
translation, SERVER.md's first two steps, the note under the prompt on the Connect your website page
(web/src/lib/words.ts) and the release notes of 0.6.0 (CHANGELOG.md), which brought it, say the same; `agentcake setup --print --site`
says it in its own steps (test_site_setup.py). No document still says that only the site owner creates the server or
adds the DNS record while the agent explains the steps.
"""
import os
import re
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from cake_server import ROOT, SERVER_MD, read  # noqa: E402  (needs the path above)
from test_install_docs import AGENTS_MD, INSTALL_MD, README_MD, README_ZH, section  # noqa: E402

CHANGELOG_MD = os.path.join(ROOT, "CHANGELOG.md")
CHANGES_CAME_IN = "0.6.0"  # the release whose notes Changelog reads: the one that brought the division
COPY_JSON = os.path.join(ROOT, "agentcake", "data", "copy.en.json")
WORDS_TS = os.path.join(ROOT, "web", "src", "lib", "words.ts")
DOCS = os.path.join(ROOT, "docs")
LLMS_TXT = os.path.join(ROOT, "llms.txt")
WITH_AGENT_WHAT = re.compile(r"withAgentWhat: \(product: string\) => `([^`]*)`")
TASK_TABLE = re.compile(r"^\| Task \| Who does it \|.*\n\|[-| ]+\|\n((?:\|.*\|\n)+)", re.M)
AGENT = re.compile(r"^You\b")  # INSTALL.md speaks to the installing agent as "you"
OWNER = re.compile(r"^The site owner\b")
# The tasks of INSTALL.md's table, found by the words of their Task cell, and who does each.
AGENT_TASKS = {"create the server": r"\b(?:Create|Set up) the server\b", "add the DNS record": r"\bDNS record\b",
               "paste the script tag in a site builder": r"\bsite builder\b", "deploy the website": r"\bDeploy\b"}
OWNER_TASKS = {"sign in": r"\bSign in\b", "pay": r"\b[Pp]ay(?:ment)?\b", "accept terms": r"\bterms\b",
               "register on the local page": r"\bRegister\b",
               "approve its plan and costs": r"\bApprove\b.*\bplan\b"}
# What the English documents say, each fact as words a paragraph holds (case-insensitive).
APPROVAL = r"\bapprov(?:e|es|al|ed)\b"
CREATES_SERVER = r"\bcreates? (?:a|the|your) server\b"
ADDS_RECORD = r"\badds? (?:a|the|this|its) DNS record\b"
SIGNS_IN = r"\bsign[- ]in\b"
NEW_ACCOUNTS = r"\bnew accounts?\b"
PAYS = r"\b(?:pay|payments?)\b"
TERMS = r"\bterms\b"
MONTHLY_COST = r"\bmonthly costs?\b"
TOTAL = r"\btotal\b"
COMMAND_LINE = r"\bcommand-line tools?\b"
# The Chinese README's words for the same facts.
ZH_APPROVAL = r"批准|同意"
ZH_CREATES_SERVER = r"(?:创建|建)服务器"
ZH_ADDS_RECORD = r"(?:添加|加) DNS 记录"
ZH_SIGNS_IN = r"登录"
ZH_NEW_ACCOUNTS = r"开账号|开设帐户|开户|创建帐户|注册"
ZH_PAYS = r"付款"
ZH_TERMS = r"条款"
ZH_MONTHLY = r"每月|月度|月费"
ZH_TOTAL = r"合计|总费用|总额|总计"
# Sayings of the division before the site owner's approval let the agent act: only the owner creates the server or
# adds the record, the agent explains, provides the details or guides them through it, the agent's plan only links a
# price page, and the agent never commits or pushes.
OLD_DIVISION = [
    r"[Oo]nly (?:you|the site owner|the user) (?:can )?(?:creates?|adds?) (?:the|a) (?:server|record|DNS record)",
    r"The user creates servers and changes DNS records",
    r"[Oo]nly you can add the record",
    r"A coding agent can provide the record details",
    r"require accounts with your cloud and DNS providers",
    r"follow the agent's instructions for your DNS provider",
    r"can guide you through this step",
    r"guides you through steps such as adding a DNS record",
    r"For a Shopify store or another hosted platform, the agent shows you where to paste the script tag",
    r"请按照它提供的说明完成这些步骤",
    r"逐步指导你添加 DNS 记录",
    r"如果网站托管在 Shopify 等平台上，它会说明在何处添加此代码",
    r"Link to the provider's pricing page",
    r"say that there's no charge for AgentCake",
    r"Never commit or push the user's repositories",
]


def paragraphs(markdown):
    """The text's paragraphs and list items, each on one line."""
    blocks = re.split(r"\n\s*\n|\n(?=\s*[-*] |\s*\d+\. )", markdown)
    return [" ".join(block.split()) for block in blocks if block.strip()]


def says(blocks, *facts):
    """Whether one paragraph of blocks holds every fact (regular expressions, case-insensitive)."""
    return any(all(re.search(fact, block, re.I) for fact in facts) for block in blocks)


def step(markdown, number):
    """SERVER.md's `### <number>. …` step, up to the next heading."""
    match = re.search(rf"^### {number}\. .*?\n(.*?)(?=^#{{2,3}} )", markdown, re.M | re.S)
    if not match:
        raise AssertionError(f"SERVER.md has no step {number}")
    return match.group(1)


def newest_release(changelog):
    """CHANGELOG.md's newest `## <version>` section."""
    return re.search(r"^## \S+\n(.*?)(?=^## \S+$|\Z)", changelog, re.M | re.S).group(1)


def release_entry(changelog, version):
    """CHANGELOG.md's `## <version>` section."""
    return re.search(rf"^## {re.escape(version)}\n(.*?)(?=^## \S+|\Z)", changelog, re.M | re.S).group(1)


def task_rows(markdown):
    """INSTALL.md's table of tasks as [(task, who does it)]."""
    table = TASK_TABLE.search(markdown)
    if not table:
        raise AssertionError("INSTALL.md has no table '| Task | Who does it | …'")
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in table.group(1).splitlines()]
    return [(row[0], row[1]) for row in rows]


def published_texts():
    """{path: text} of what a site owner or a coding agent reads about installing: the root documents, docs/, llms.txt,
    the command line's words and the local pages' words. CHANGELOG.md counts by its newest release: older releases
    describe how those releases worked."""
    paths = [README_MD, README_ZH, INSTALL_MD, AGENTS_MD, SERVER_MD, LLMS_TXT, COPY_JSON, WORDS_TS]
    paths += [os.path.join(DOCS, name) for name in sorted(os.listdir(DOCS)) if name.endswith(".md")]
    texts = {path: read(path) for path in paths}
    texts[CHANGELOG_MD] = newest_release(read(CHANGELOG_MD))
    return texts


class InstallMd(unittest.TestCase):
    """INSTALL.md's table of tasks gives each task to whom the other documents say."""

    def test_the_agent_creates_the_server_adds_the_record_deploys_and_pastes_the_script_tag(self):
        rows = task_rows(read(INSTALL_MD))
        for task, words in AGENT_TASKS.items():
            found = [(name, who) for name, who in rows if re.search(words, name)]
            self.assertTrue(found, f"INSTALL.md's table has no row to {task}")
            for name, who in found:
                self.assertRegex(who, AGENT, f"INSTALL.md: {name}")

    def test_the_site_owner_signs_in_pays_accepts_terms_and_registers(self):
        rows = task_rows(read(INSTALL_MD))
        for task, words in OWNER_TASKS.items():
            found = [(name, who) for name, who in rows if re.search(words, name)]
            self.assertTrue(found, f"INSTALL.md's table has no row to {task}")
            for name, who in found:
                self.assertRegex(who, OWNER, f"INSTALL.md: {name}")


class Readme(unittest.TestCase):
    """The installation responsibilities described in both READMEs."""

    @classmethod
    def setUpClass(cls):
        readme, readme_zh = read(README_MD), read(README_ZH)
        cls.english = paragraphs(section(readme, "Install"))
        cls.chinese = paragraphs(section(readme_zh, "安装"))

    def test_with_approval_the_agent_creates_the_server_and_adds_the_record(self):
        self.assertTrue(says(self.english, APPROVAL, CREATES_SERVER, ADDS_RECORD), self.english)
        self.assertTrue(says(self.chinese, ZH_APPROVAL, ZH_CREATES_SERVER, ZH_ADDS_RECORD), self.chinese)

    def test_with_approval_the_agent_connects_the_website_and_checks_it(self):
        self.assertTrue(says(self.english, APPROVAL, r"\bconnects? your (?:web)?site\b", r"agentcake doctor"), self.english)
        self.assertTrue(says(self.chinese, ZH_APPROVAL, r"(?:连接|接入)(?:你的)?网站", r"agentcake doctor"), self.chinese)

    def test_the_site_owner_signs_in_pays_and_accepts_terms(self):
        self.assertTrue(says(self.english, SIGNS_IN, NEW_ACCOUNTS, PAYS, TERMS), self.english)
        self.assertTrue(says(self.chinese, ZH_SIGNS_IN, ZH_NEW_ACCOUNTS, ZH_PAYS, ZH_TERMS), self.chinese)

    def test_a_public_website_needs_a_server_and_a_computer_records_only_its_own_visits(self):
        """Public visitors' browsers can't reach AgentCake on the owner's computer: a public website needs a server, and
        AgentCake on a computer records only visits from that computer (not "around the clock" or "while it's on")."""
        self.assertTrue(says(self.english, r"\bpublic website\b", r"\bneeds? a server\b"), self.english)
        self.assertTrue(says(self.english, r"\bon your computer\b", r"\bonly visits from (?:that|this|your) computer\b"),
                        self.english)
        self.assertTrue(says(self.chinese, r"公开网站", r"服务器"), self.chinese)
        self.assertTrue(says(self.chinese, r"只记录(?:本机|这台电脑)上的访问"), self.chinese)
        for blocks in (self.english, self.chinese):
            self.assertFalse(says(blocks, r"around the clock|while your computer is off|持续记录|关机期间"), blocks)

    def test_the_agents_plan_lists_each_monthly_cost_and_the_total(self):
        self.assertTrue(says(self.english, MONTHLY_COST, r"\b(?:each|every|itemized|per[- ]item)\b", TOTAL), self.english)
        self.assertTrue(says(self.chinese, ZH_MONTHLY, r"每一?项|逐项|各项", ZH_TOTAL), self.chinese)


class ServerMd(unittest.TestCase):
    """SERVER.md's first two steps open with what the site owner can ask a coding agent to do there."""

    def test_steps_1_and_2_open_with_the_agent_and_install_md(self):
        server = read(SERVER_MD)
        for number in (1, 2):
            opening = paragraphs(step(server, number))[0]
            for fact in (APPROVAL + r"|\byou can ask a coding agent\b", r"\bcoding agent\b", COMMAND_LINE,
                         r"\]\(INSTALL\.md[#)]"):
                self.assertRegex(opening, re.compile(fact, re.I), f"SERVER.md step {number}")


class WordsTs(unittest.TestCase):
    """The note under the prompt on the Connect your website page."""

    def test_the_note_says_the_agent_creates_the_server_and_adds_the_record_and_who_signs_in(self):
        note = WITH_AGENT_WHAT.search(read(WORDS_TS)).group(1)
        for fact in (APPROVAL, CREATES_SERVER, ADDS_RECORD, SIGNS_IN):
            self.assertRegex(note, re.compile(fact, re.I))


class Changelog(unittest.TestCase):
    """The release notes of 0.6.0, where these changes came in, say what changed for the site owner."""

    @classmethod
    def setUpClass(cls):
        cls.release = release_entry(read(CHANGELOG_MD), CHANGES_CAME_IN)
        cls.blocks = paragraphs(cls.release)

    def test_with_approval_the_agent_creates_the_server_and_adds_the_record(self):
        """The install part says the agent's plan waits for approval, then lists the agent's tasks."""
        part = paragraphs(re.search(r"^### Install with a coding agent\n(.*?)(?=^### )", self.release, re.M | re.S).group(1))
        for fact in (APPROVAL, CREATES_SERVER, ADDS_RECORD):
            self.assertTrue(says(part, fact), (fact, part))
        self.assertTrue(says(part, SIGNS_IN, PAYS, TERMS), part)

    def test_the_agents_plan_lists_each_monthly_cost_and_the_total(self):
        self.assertTrue(says(self.blocks, MONTHLY_COST, TOTAL), self.release)

    def test_it_names_the_hosting_reference_sslip_io_names_and_docker_backups(self):
        self.assertIn("](docs/hosting.md", self.release)
        self.assertTrue(says(self.blocks, r"\bsslip\.io\b"), self.release)
        self.assertTrue(says(self.blocks, r"\bDocker Compose\b", r"\bback(?:s)? up\b|\bbackups?\b"), self.release)

    def test_it_says_updates_run_at_the_lowest_priority_while_docker_reports_healthy(self):
        """On a server with 1 vCPU, the first automatic update (the city database) once made Docker report AgentCake
        unhealthy: updates run at the lowest CPU priority and Docker's health check waits longer."""
        self.assertTrue(says(self.blocks, r"\blowest CPU priority\b", r"\bsystemd\b"), self.release)
        self.assertTrue(says(self.blocks, r"\bhealth check\b", r"\bDocker\b"), self.release)

    def test_it_says_systemd_keeps_agentcake_running_when_the_memory_limit_stops_an_update(self):
        """deploy/cake.service's OOMPolicy=continue: the update fails and is recorded, AgentCake keeps running; an
        installed service takes the new unit as SERVER.md's Upgrading says."""
        self.assertTrue(says(self.blocks, r"\bsystemd\b", r"\bmemory limit\b", r"\bkeeps running\b",
                             r"deploy/cake\.service"), self.release)

    def test_it_says_doctor_names_a_certificate_problem_instead_of_blaming_a_sandbox(self):
        """doctor_live.why_not_opened: a certificate Python's check refuses is named by its kind (data/doctor.json
        certificate_errors), never taken for a sandbox that blocks the connection."""
        self.assertTrue(says(self.blocks, r"agentcake doctor --url", r"\bHTTPS certificate\b", r"\bexpired\b",
                             r"\bself-signed\b", r"\bhost name\b"), self.release)
        self.assertTrue(says(self.blocks, r"\bproxy that replaces certificates\b", r"\bno longer blames a sandbox\b"),
                        self.release)


class OldDivision(unittest.TestCase):
    def test_no_document_still_says_only_the_site_owner_creates_the_server_or_adds_the_record(self):
        for path, text in published_texts().items():
            flat = " ".join(text.split())
            for saying in OLD_DIVISION:
                self.assertIsNone(re.search(saying, flat), f"{os.path.relpath(path, ROOT)}: {saying}")


if __name__ == "__main__":
    unittest.main()
