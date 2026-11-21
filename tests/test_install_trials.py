"""INSTALL.md against what trial runs of the new entry showed coding agents doing: each correction
stands in the part of the guide where the agent reads it. The guide's other checks (commands, links, the release, the
command line) are in test_install_docs.py.

    python3 -I -m unittest discover -s tests -v      (from the AgentCake folder)
"""
import re
import unittest

from cake_server import read
from test_install_docs import INSTALL_MD, part, section

# Step 5's rule for changing an approved plan, and step 3's for asking about visitors.
APPROVED_PLAN_RULE = ("To change your approved plan, send the site owner the new plan. Wait for their explicit "
                      "approval before you make any changes.")
VISITORS_RULE = ("For a live website, ask the site owner whether to start with a trial on this computer or with public "
                 "visitors. If the site owner already answered a question, skip it.")
# The language of the updates between commands, which opens each part of step 5 (step 5 itself opens with "Write your
# updates in the site owner's language."), and step 4's default for a site with a consent banner, as (choice, default).
UPDATES_RULE = "Use the site owner's language in your updates."
CONSENT_DEFAULT = ("Consent banner", "`data-consent=\"required\"` on the script tag, with `window.cake.start()` when the "
                   "visitor agrees and `window.cake.stop()` when they refuse")
STEP5_PARTS = 7  # this computer's five parts, the server's and the website's


class InstallTrials(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.install = read(INSTALL_MD)

    def test_the_entry_benchs_corrections_stand_where_the_agent_reads_them(self):
        """Trial runs of the new entry: agents asked about defaults and details step 3 doesn't list, answered a Chinese
        owner in English, changed an approved plan or set out to create the owner's server, skipped the visitors
        question for a live website and never said when to deploy a trial's changes. INSTALL.md says each where the
        agent reads it (the server and anything else that costs money only once the owner approves its costs); step 5
        and each of its branches open with the rule for changing an approved plan, in bold."""
        for name, words in (
                ("How to work", "This includes the updates that you write between commands."),
                ("Step 1. Review the website and this computer",
                 "An empty folder means that there's no website code on this computer to change."),
                ("Step 3. Ask your questions", f"{VISITORS_RULE} Ask only about the details in this table. | Detail |"),
                ("Step 4. Propose a plan", "List these defaults in your plan instead of asking about them."),
                ("Step 4. Propose a plan", "| CloudFront cache | Invalidation after deployment |"),
                ("Step 4. Propose a plan", "| Docker installation | With `sudo` |"),
                ("Step 4. Propose a plan", "Write your plan in the site owner's language."),
                ("Step 4. Propose a plan",
                 "Create paid resources after the site owner approves their costs."),
                ("Step 5. Install", "Write your updates in the site owner's language."),
                ("Step 5. Install", "| New resources | Listed in your approved plan |"),
                ("Step 7. Finish the setup",
                 "For a trial on this computer, deploy the website's changes only after AgentCake runs on a server.")):
            self.assertIn(words, " ".join(section(self.install, name).split()))
        for branch in (section(self.install, "Step 5. Install").split("\n### ", 1)[0],
                       part(self.install, "Set up the server"), part(self.install, "Connect the website")):
            with self.subTest(branch=branch.strip()[:40]):
                self.assertTrue(" ".join(branch.split()).startswith(f"**{APPROVED_PLAN_RULE}**"))

    def test_the_second_candidates_corrections_stand_where_the_agent_reads_them(self):
        """The server install trial on 0.6.0's second candidate: Codex copied the owner's rows of the tasks table
        without the column that said how (Guidance then, How now), so its plan never said that it would guide the
        owner; Claude's plan said that it would change no other file, and then it added a component that loads the
        page script after consent; Claude wrote its updates on the
        server in English to an owner who wrote in Chinese. Step 4 copies the rows that apply with their How and Check
        columns, its defaults say where the page script goes on a site with a consent banner, and each part of step 5
        opens with the language of the updates, after the rule for changing an approved plan where it has one."""
        plan = " ".join(section(self.install, "Step 4. Propose a plan").split())
        self.assertIn("Copy the rows of the tasks table that apply to this setup into your plan. Include the How and "
                      "Check columns.", plan)
        self.assertIn(f"| {CONSENT_DEFAULT[0]} | {CONSENT_DEFAULT[1]} |", plan)
        parts = re.findall(r"^### (.+)$", section(self.install, "Step 5. Install"), re.M)
        self.assertEqual(len(parts), STEP5_PARTS)
        for heading in parts:
            with self.subTest(part=heading):
                opening = " ".join(part(self.install, heading).split()).removeprefix(f"**{APPROVED_PLAN_RULE}** ")
                self.assertTrue(opening.startswith(UPDATES_RULE), opening[:80])


if __name__ == "__main__":
    unittest.main()
