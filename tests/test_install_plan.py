"""Check the questions, accounts, deployment details and costs in INSTALL.md."""
import unittest
from decimal import Decimal

from cake_server import read
from test_install_docs import INSTALL_MD, part, section
from test_install_ops import STEP_4, flat, row_with, table

STEP_1, STEP_3 = "Step 1. Review the website and this computer", "Step 3. Ask your questions"
COSTS_HEADER = ("Item", "Example", "Price per month", "With the free tier", "Source")
ACCOUNT_COMMANDS = ("gcloud config list", "aws sts get-caller-identity", "az account show", "doctl account get",
                    "hcloud context active")
COST_ITEMS = ("Server", "Disk", "Public IPv4 address", "Domain", "Traffic for path rules", "Platform plan")
FREE_ITEMS = ("AgentCake", "HTTPS certificate", "City database")
FREE_TIER_REGIONS = ("us-west1", "us-central1", "us-east1")
COSTS_ANCHORS = ("docs/hosting.md#what-agentcake-costs", "docs/hosting.md#server-costs",
                 "docs/hosting.md#platform-plans")


class PlanAndCosts(unittest.TestCase):
    """The account, what the agent creates and what it costs, before any approval."""

    @classmethod
    def setUpClass(cls):
        cls.install = read(INSTALL_MD)
        cls.plan = section(cls.install, STEP_4)

    def test_step_1_reads_each_tools_account_without_changing_anything(self):
        step = flat(section(self.install, STEP_1))
        for command in ACCOUNT_COMMANDS:
            self.assertIn(f"`{command}`", step)
        self.assertIn("production", step)
        self.assertIn("`git status`", step)
        self.assertIn("`cf auth whoami`", step)
        self.assertIn("`authenticated` field. A false value means the session is signed out, even with exit code 0", step)
        self.assertIn("linked project in `.vercel/project.json`", step)
        self.assertIn("`gddy auth status`", step)
        self.assertIn("These commands show the account without changing any settings.", step)

    def test_step_3_asks_about_one_server(self):
        server = row_with(table(section(self.install, STEP_3), ("Detail", "Ask about")), "Server")
        self.assertIn("SSH name of an existing server", server[1])
        self.assertIn("cloud provider for a new", server[1])

    def test_the_plan_names_the_account_what_it_creates_and_how_it_deploys(self):
        topics = [row[0] for row in table(self.plan, ("Topic", "Example"))]
        for topic in ("Account and project", "What you create", "Region", "Deployment", "Costs"):
            self.assertIn(topic, topics)
        self.assertIn("The site owner confirms the account and the project.", flat(self.plan))
        self.assertIn("Copy the rows of the tasks table that apply to this setup into your plan. Include the How and "
                      "Check columns.", flat(self.plan))

    def test_the_builder_questions_and_plan_identify_the_same_site(self):
        questions = dict(table(section(self.install, STEP_3), ("Detail", "Ask about")))
        topics = dict(table(self.plan, ("Topic", "Example")))
        for row in (questions, topics):
            target = row["Builder account and site"].lower()
            self.assertIn("account", target)
            self.assertIn("admin address", target)
        self.assertRegex(topics["When changes go live"], r"Saving.*published Shopify theme.*live")

    def test_the_plan_names_the_rollback_and_default_network(self):
        topics = dict(table(self.plan, ("Topic", "Example")))
        self.assertRegex(topics["Rollback"], r"(?i)restore the previous working version")
        self.assertIn("Publish Deploy", topics["Rollback"])
        self.assertIn("subnet", topics["What you create"])
        self.assertRegex(topics["Enabling Compute Engine"], r"`default` network.*firewall rules")

    def test_the_defaults_name_the_server_and_put_the_sites_own_domain_first(self):
        rows = table(self.plan, ("Choice", "Default"))
        defaults = dict(rows)
        self.assertEqual(defaults["Site builder"], "Add the script tag with your browser tool")
        details = dict(table(section(self.install, STEP_3), ("Detail", "Ask about")))
        self.assertIn("signed in to the builder", details["Builder sign-in"])
        self.assertEqual(defaults["Server name"], "`agentcake`")
        self.assertIn("Deployment", defaults)
        self.assertIn("own domain, at no cost", defaults["Name for AgentCake"])
        without = defaults["Name without a domain"]
        self.assertEqual([row[0] for row in rows].index("Name without a domain"),
                         [row[0] for row in rows].index("Name for AgentCake") + 1)
        self.assertLess(without.index("sslip.io"), without.index(".com"))
        self.assertIn("$11 a year", without)
        self.assertIn("risks", defaults["sslip.io risks"])
        self.assertIn("Nearest free e2-micro region", defaults["Region on Google Cloud"])

    def test_the_cost_table_lists_each_item_its_source_and_a_total(self):
        rows = table(self.plan, COSTS_HEADER)
        for item in COST_ITEMS + FREE_ITEMS:
            row_with(rows, item)
        for item in FREE_ITEMS:
            self.assertEqual(row_with(rows, item)[2], "$0")
        total = row_with(rows, "Total")
        self.assertEqual(total, rows[-1])
        self.assertEqual(total[2:4], ("**$10.97**", "**$3.65**"))
        for column in (2, 3):
            prices = [Decimal(row[column].removeprefix("$")) for row in rows[:-1]]
            self.assertEqual(sum(prices), Decimal(total[column].strip("*$")))
        for item, regular, eligible, source in (
            ("Server", "$6.12", "$0", "pricing/general-purpose"),
            ("Disk", "$1.20", "$0", "disks-image-pricing"),
            ("Public IPv4 address", "$3.65", "$3.65", "network-pricing"),
        ):
            row = row_with(rows, item)
            self.assertEqual(row[2:4], (regular, eligible))
            self.assertIn(source, row[4])
        self.assertIn("Unless the site owner confirms that they don't, list the server and its disk at their regular "
                      "prices.", flat(self.plan))
        self.assertIn("The $3.65 total assumes the allowance covers the full month for both the server and its disk.",
                      flat(self.plan))

    def test_the_costs_say_when_a_free_tier_applies_and_come_before_anything_is_created(self):
        text = flat(self.plan)
        self.assertIn("billing account", text)
        for region in FREE_TIER_REGIONS:
            self.assertIn(f"`{region}`", text)
        for words in ("For each price, link the provider's pricing page as its source.",
                      "If a pricing page doesn't open, cite the "
                      "[hosting reference](docs/hosting.md#what-agentcake-costs) and the date of its prices.",
                      "Mark a price that you can't confirm as an estimate.",
                      "For each of them, give the free amount and the price above it.",
                      "When your plan changes, update its cost table, including what you already created.",
                      "In this example, Premium Tier traffic to North America costs $0.12 per GiB above the first GiB",
                      "Other projects in that billing account can use them up.",
                      "The example's prices are from Google's pricing pages on November 20, 2026.",
                      "Create paid resources after the site owner approves their costs."):
            self.assertIn(words, text)
        for anchor in COSTS_ANCHORS:
            self.assertIn(f"]({anchor})", self.plan)


class BenchRunCorrections(unittest.TestCase):
    """The install bench on 0.6.0: twice an agent asked about the region before its plan when two regions' prices
    differed a lot, and twice an owner stopped the setup before the server and the agent's last message left out who does
    each remaining step and that registering on the local page is the owner's."""

    @classmethod
    def setUpClass(cls):
        cls.install = read(INSTALL_MD)

    def test_a_cheaper_region_goes_into_the_plan_instead_of_a_question(self):
        costs = flat(section(self.install, STEP_4))
        for words in ("Prices can differ a lot between regions.",
                      "Plan the default region, and if another region costs much less, add its price to your cost table.",
                      "The site owner can change the region when they review your plan.",
                      "Don't ask a separate question about the region, before your plan or in it.",
                      "If you don't know where most visitors are, use the default region and name it in your plan."):
            self.assertIn(words, costs)

    def test_a_setup_stopped_early_still_ends_with_the_remaining_steps_and_who_does_them(self):
        step7 = flat(section(self.install, "Step 7. Finish the setup"))
        self.assertTrue(step7.startswith("If steps of your plan are still left when you stop, still send your last "
                                         "message. That holds when the site owner stops the setup and when they ask for "
                                         "only part of it, such as the part on this computer first. List each remaining "
                                         "step and who does it in that message, including "
                                         "registering on the local page, which is the site owner's step. Don't point "
                                         "back to an earlier message, such as with \"continue from step 1 above\"."),
                        step7[:160])

    def test_the_ssh_address_and_key_come_from_this_computer_not_from_a_question(self):
        """In all three bench runs an agent asked in its plan for the owner's public IPv4 address and whether it may
        make an SSH key: the agent's plan now carries what this computer shows, and the key is the owner's own or a listed new one."""
        server = flat(part(self.install, "Set up the server"))
        for words in ("For a new server with another provider, find the site owner's public IPv4 address before you write "
                      "your plan. Run `curl -4 -s https://checkip.amazonaws.com`, which changes nothing.",
                      "Your plan opens SSH only to that address. It says how to change that firewall rule if the address "
                      "changes, with the provider's command or settings from [Provider guides](#provider-guides).",
                      "Don't ask for the address separately.",
                      "To find the site owner's public key, run `ls ~/.ssh`.",
                      'If there\'s no public key, list a new key in your plan: `ssh-keygen -t ed25519 -f '
                      '~/.ssh/agentcake_ed25519 -C agentcake -N ""`. With `-N ""`, the new key has no passphrase.',
                      "The site owner's approval of your plan covers the new key. Don't ask about it separately."):
            self.assertIn(words, server)
        self.assertLess(server.index("For other providers"), server.index("checkip.amazonaws.com"))

    def test_installing_a_tool_waits_for_an_explicit_yes_to_that_install(self):
        """On the bench an agent read 'you decide' as leave to `brew install hcloud` on the owner's computer."""
        how = flat(section(self.install, "How to work"))
        self.assertIn("To install a command-line tool, ask the site owner first. A reply such as \"you decide\" isn't "
                      "approval to install. Ask about each install on its own, such as `hcloud` with `brew` or `npm`, and "
                      "wait for an explicit yes.", how)


if __name__ == "__main__":
    unittest.main()
