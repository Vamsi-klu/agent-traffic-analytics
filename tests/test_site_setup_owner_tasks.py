"""setup --print --site: who does each step that it leaves, as INSTALL.md's table of tasks gives them.

    python3 -I -m unittest discover -s tests -p test_site_setup_owner_tasks.py -v      (from the AgentCake folder)

Step 5 has the coding agent finish the steps left with the site owner's approval, the site owner signing in to their
accounts and paying. The site owner can ask their coding agent to create the server and add the A record at their DNS
provider, and doctor checks the setup; it deploys the website with the branch and method of its plan and hands the
middleware's shared secret straight to the platform's command-line tool. A trial on this computer deploys its change
only once AgentCake runs on a server: until then the script tag sends public visitors' browsers to 127.0.0.1, their own
computer. For a WordPress theme or plugin, the coding agent uploads AgentCake's plugin to the WordPress site itself when
it has a browser tool and the site owner approves, the site owner signing in; otherwise the site owner does it. What the
steps hold besides is test_site_setup.py's.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), HERE]
from test_site_setup import SITE_KEY, SetupSite  # noqa: E402

ADDRESS = "https://cake.brewbean.example"
ADDS_RECORD = r"\badd (?:the|this) (?:A )?record\b"
CREATES_SERVER = r"\bcreate the server\b"
DEPLOY = r"\b[Dd]eploy(?:s|ing)?\b(?!/)"  # not the release's deploy/ folder in an address


def agent_can(text, action):
    """Whether one sentence of text has the site owner ask their coding agent to do action, or says it can do it with
    their approval."""
    return any(re.search(action, sentence) and (re.search(r"\bask your coding agent to\b", sentence)
                                                or re.search(r"\bcoding agent can\b.*\bapprov(?:e|es|al)\b", sentence))
               for sentence in re.split(r"(?<=\.)\s+", text))


def bullets(out):
    """Step 5's items, each on one line."""
    return [" ".join(item.split()) for item in re.split(r"\n  - ", out[out.index("Step 5."):])[1:]]


def opening(out):
    """Step 5's first lines, up to its first item."""
    start = out.index("Step 5.")
    return " ".join(out[start:out.index("\n  - ", start)].split())


def item(out, pattern):
    """Step 5's one item that matches pattern."""
    found, = [line for line in bullets(out) if re.search(pattern, line)]
    return found


class OnThisComputer(SetupSite):

    def test_step_5_has_the_agent_finish_with_the_owners_approval_and_the_owner_sign_in_and_pay(self):
        start = opening(self.printed("static"))
        for fact in (r"\bsite owner's approval\b", r"\bsign(?:-| )in\b", r"\bpayment\b", r"\bask the site owner\b"):
            self.assertRegex(start, fact)

    def test_with_approval_the_agent_creates_the_server_and_adds_the_record(self):
        server = item(self.printed("static"), r"server for public visitors")
        self.assertTrue(agent_can(server, CREATES_SERVER), server)
        self.assertTrue(agent_can(server, ADDS_RECORD), server)

    def test_the_website_is_deployed_once_agentcake_runs_on_a_server(self):
        self.assertRegex(item(self.printed("static"), DEPLOY), r"\bafter \S+ runs on a server\b")


class ServerDeployment:
    """Both server routes print the deployment and secret handoff for the site owner."""

    def test_the_agent_sets_the_middleware_secret_on_the_hosting_platform_before_deployment(self):
        output = self.printed("express")
        deploy = item(output, DEPLOY)
        self.assertIn("branch and method in your plan", deploy)
        steps = " ".join(bullets(output))
        before_deploy = steps[:re.search(DEPLOY, steps).start()]
        for fact in ("coding agent", "hosting platform", "server middleware", "CAKE_SERVER_TIMING_SECRET", "shared secret"):
            self.assertIn(fact, before_deploy)
        sign_in = before_deploy[:before_deploy.index("CAKE_SERVER_TIMING_SECRET")]
        self.assertRegex(sign_in, r"\b(?:credentials|password|verification code)\b")
        self.assertRegex(sign_in, r"\b(?:your(?: own)?|the site owner's) (?:terminal|browser)\b")
        self.assertIn("browser", sign_in)
        self.assertIn("terminal", sign_in)
        credential_step = item(output, r"\b(?:credentials|password|verification code)\b")
        self.assertRegex(credential_step, r"\b(?:asks? for|requests? (?:a|your)|prompt(?:s|ed)?|when needed|if required)\b")

    def test_the_owner_sets_the_secret_when_the_tool_cannot_read_it_privately_from_standard_input(self):
        steps = " ".join(bullets(self.printed("express")))
        secret = steps[:re.search(DEPLOY, steps).start()]
        self.assertIn("command-line tool", secret)
        self.assertIn("standard input", secret)
        self.assertRegex(secret, r"\bwithout (?:displaying|showing|printing) (?:it|the secret)\b")
        handoff = secret[secret.index("standard input"):]
        self.assertRegex(handoff, r"\bonly\b.*\bcommand-line arguments?\b|\bcommand-line arguments?\b.*\bonly\b")
        self.assertRegex(handoff, r"\b(?:your(?: own)?|the site owner's) terminal\b")
        terminal = handoff[handoff.index("terminal"):]
        command = "`agentcake secret print`"
        self.assertIn(command, terminal)
        self.assertIn("the server", handoff)
        after_command = terminal.split(command, 1)[1]
        self.assertRegex(after_command, r"\b(?:[Pp]aste|[Ee]nter)\b")
        self.assertRegex(after_command, r"\bplatform(?:'s)? (?:secret )?settings?\b")

    def test_for_a_static_site_the_middleware_secret_comes_with_its_condition(self):
        """Step 3 tells a static site to skip the server middleware (it needs server code), so step 5 names the
        middleware's secret only for a site that uses the middleware: unconditionally, it had a coding agent set a
        variable on a static site's platform that nothing reads."""
        output = self.printed("static")
        self.assertIn("not for a static site", output)
        steps = " ".join(bullets(output))
        first = re.search(r"[^.]*CAKE_SERVER_TIMING_SECRET[^.]*\.", steps).group(0).strip()
        self.assertRegex(first, r"^If your site uses the server middleware, it needs\b")


class SubdomainRoute(ServerDeployment, SetupSite):

    def setUp(self):
        super().setUp()
        self.settings(site_key=SITE_KEY, public_listen="127.0.0.1:8080", path_prefix="/cake",
                      site_domain="brewbean.example", public_url=ADDRESS)

    def test_the_agent_can_add_the_dns_record_and_doctor_checks_the_setup(self):
        """Step 5's opening has the agent do the remaining steps with the site owner's approval (OnThisComputer); its
        doctor item checks the record with the rest of the setup."""
        out = self.printed("static")
        self.assertRegex(item(out, r"^Add an A record"), r"\bcoding agent can add this record\b")
        self.assertRegex(item(out, r"^To check the setup"), r"\bdoctor\b")


class SameSitePath(ServerDeployment, SetupSite):

    def setUp(self):
        super().setUp()
        self.settings(site_key=SITE_KEY, public_listen="0.0.0.0:8080", path_prefix="/cake",
                      site_domain="brewbean.example")


class WordPressThemeOrPlugin(SetupSite):

    def test_with_a_browser_tool_and_approval_the_agent_uploads_the_plugin_itself(self):
        flat = " ".join(self.printed("wordpress-theme").split())
        for fact in (r"\bbrowser tool\b", r"\bapprov", r"Upload Plugin", r"\bsite owner\b[^.]*\bsigns? in\b",
                     r"\b(?:[Oo]therwise|[Ww]ithout (?:a|one))\b[^.]*\bask the site owner\b"):
            self.assertRegex(flat, fact)
        self.assertNotIn("Ask the site owner to upload the .zip file", flat)


if __name__ == "__main__":
    unittest.main()
