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

    def test_the_formal_rounds_corrections_stand_where_the_agent_reads_them(self):
        """0.6.0's formal round (11/20): agents that stopped after the part on this computer pointed back to an
        earlier message for the remaining steps, asked about one default on its own (CloudFront's invalidation, the
        region), and, told to do only the part on this computer, started AgentCake there although their approved plan
        said not to. Step 4's defaults say not to ask about one on its own; step 5 opens, after its rule for changing
        an approved plan, with what part of a plan means and with the last message of a setup that stops early."""
        defaults = " ".join(section(self.install, "Step 4. Propose a plan").split())
        self.assertIn("The site owner can change a default when they review your plan. Don't ask a separate question "
                      "about a default, before your plan or in it, such as whether the region suits them, whether to "
                      "keep the CloudFront invalidation, or whether to add the server middleware, unless this guide "
                      "tells you to ask, as it does before you use `sudo` for Docker on an existing server.", defaults)
        never = " ".join(section(self.install, "Never").split())
        self.assertIn("On an existing server, ask the site owner before using `sudo` for Docker.", never)
        opening = " ".join(section(self.install, "Step 5. Install").split("\n### ", 1)[0].split())
        self.assertTrue(opening.startswith(
            f"**{APPROVED_PLAN_RULE}** If the site owner asks for only part of your plan, such as the part on this "
            "computer, do only your plan's steps for that part; for anything else, such as starting AgentCake on this "
            "computer when your plan doesn't, send the new plan and wait for their approval first. If you stop before "
            "your plan is done, such as after that part, your last message lists each remaining step and who does "
            "it, as step 7 says, without pointing back to an earlier message. Write your updates in the site owner's "
            "language."), opening[:400])

    def test_the_local_pages_english_prompt_does_not_set_the_language(self):
        """0.6.1's round of the new entry (11/23): connecting a website starts with the local page's prompt, which is
        English (the interface is English only), and the owner then wrote in Chinese; the agent answered in English to
        the end, the updates too. How to work says which language a copied prompt leaves the agent with."""
        how = " ".join(section(self.install, "How to work").split())
        self.assertIn("This includes the updates that you write between commands. If their first message is the English "
                      "prompt from AgentCake's local page, answer in the language of the words they write themselves, "
                      "in your updates too.", how)

    def test_the_last_message_says_the_local_page_shows_how_to_connect_the_website(self):
        """The last message says that after registering, the local page teaches how to connect the website, as
        AGENTS.md has it. In 0.6.1's round (11/23) an install on this computer never said it: step 7 didn't ask for it.
        The local page shows how to connect the website once registered, on this computer and on a server alike, until
        the website's first visit (web/tests: home.test.mjs, register.test.mjs)."""
        step7 = " ".join(section(self.install, "Step 7. Finish the setup").split())
        self.assertIn("The page script, collecting visits and the command line work without registering. After they "
                      "register, the local page shows how to connect their website until the website sends its first "
                      "visit. 8. A list of the files that you changed", step7)

    def test_the_install_question_goes_into_the_plan_as_an_item_of_its_own(self):
        """0.6.1's round (11/23, a WordPress site): once the owner named Google Cloud, the agent asked whether to
        install gcloud in a round of its own before its plan, reading How to work's "Ask about each install on its own"
        as a message of its own; three other runs asked it inside their plans. Step 4 says where it goes, in the same
        words."""
        plan = " ".join(section(self.install, "Step 4. Propose a plan").split())
        self.assertIn("The site owner confirms the account and the project. If your plan installs a command-line tool "
                      "on this computer, ask about each install in your plan as an item of its own, and wait for an "
                      "explicit yes to it: approving your plan doesn't approve an install.", plan)
        how = " ".join(section(self.install, "How to work").split())
        self.assertIn("Ask about each install on its own, such as `hcloud` with `brew` or `npm`, and wait for an explicit "
                      "yes.", how)

    def test_the_last_message_the_free_name_and_the_privacy_notice_say_what_was_read_two_ways(self):
        """0.6.1's round of the new entry (11/23), installs on a server: the site owner wrote again after a complete
        hand-over, and the agent's answer, the last message, left out the costs and how to delete what it made; for a
        site without its own domain the agent asked the owner, before its plan, to choose between the free name and a
        new domain; drafting the privacy notice, the agent wrote the owner's account e-mail address into it."""
        step7 = " ".join(section(self.install, "Step 7. Finish the setup").split())
        self.assertIn("Include each of these points in your last message. If the site owner writes again after that "
                      "message, your answer is then the last message: write each of these points in it again, though a "
                      "point that didn't change may be shorter.", step7)
        plan = " ".join(section(self.install, "Step 4. Propose a plan").split())
        self.assertIn("| Name without a domain | A free sslip.io name. Your plan names the other choice too, a new .com "
                      "domain for about $11 a year; don't ask the site owner to choose before your plan. |", plan)
        self.assertIn("| sslip.io risks | Its risks go in your plan, before the site owner approves it |", plan)
        how = " ".join(section(self.install, "How to work").split())
        self.assertIn("| Update the privacy notice | You | Your draft, after the site owner approves the wording. Leave "
                      "the contact address for them to fill in. | — |", how)


if __name__ == "__main__":
    unittest.main()
