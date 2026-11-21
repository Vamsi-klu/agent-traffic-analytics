"""Check the decisions a coding agent makes while connecting and deploying the owner's website."""
import unittest

from cake_server import read
from test_install_docs import INSTALL_MD, part, section
from test_install_ops import flat, table


class WebsiteChanges(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        website = part(read(INSTALL_MD), "Connect the website")
        blocks = website.split("#### ")
        cls.builder = flat(next(block for block in blocks if block.startswith("On a site builder")))
        cls.code = flat(next(block for block in blocks if block.startswith("With the website's code")))
        cls.variables = flat(next(block for block in blocks if block.startswith("Set the variables")))
        cls.deploy = flat(next(block for block in blocks if block.startswith("Deploy the website")))

    def test_each_browser_change_checks_the_signed_in_account_site_and_domain(self):
        self.assertRegex(self.builder, r"Before each change, [^.]*signed-in account, site and domain[^.]*plan")
        self.assertIn("If any differs, ask the site owner", self.builder)

    def test_builder_instructions_cover_visitor_consent_and_supported_pages(self):
        for words in ('add `data-consent="required"` to the script tag', "`window.cake.start()` when the visitor agrees",
                      "`window.cake.stop()` when they refuse", "If the builder can't run code when the visitor agrees, "
                      "ask the site owner how to continue."):
            self.assertIn(words, self.builder)
        self.assertLess(self.builder.index("data-consent"), self.builder.index("Save the change"))

    def test_consent_keeps_the_script_tag_that_doctor_looks_for(self):
        """doctor's page check reads the page's HTML for the script tag: a tag added only after consent isn't there, so
        the default is PRIVACY.md's second way; the first only when the site owner asks, and your plan says so."""
        self.assertIn('add `data-consent="required"` to the script tag. Call `window.cake.start()` when the visitor agrees '
                      "and `window.cake.stop()` when they refuse. Until then the script does nothing, and `agentcake doctor "
                      "--url` still finds the script tag.", self.code)
        install = read(INSTALL_MD)
        self.assertIn("If the site owner wants the page script added only after consent, follow their choice. Say in your "
                      "plan that doctor's page check then reports the script tag as missing.",
                      flat(section(install, "Step 4. Propose a plan")))
        for old in ("load the script only after the visitor agrees", "load the page script only after they agree"):
            self.assertNotIn(old, flat(install))

    def test_publishing_other_changes_is_checked_before_a_live_save(self):
        self.assertIn("other unpublished changes", self.builder)
        self.assertLess(self.builder.index("other unpublished changes"), self.builder.index("Save the change"))
        self.assertIn("If any would go live, stop and ask the site owner", self.builder)

    def test_files_that_already_have_changes_need_an_owner_decision_before_editing(self):
        self.assertIn("If a file already has changes, ask the site owner before editing it", self.code)
        self.assertLess(self.code.index("Follow it exactly."), self.code.index("If a file already has changes"))

    def test_a_program_the_agent_starts_is_stopped_only_by_the_process_id_it_saved(self):
        """On the bench an agent started `next dev` from its tool and later found it with `pgrep -fl` to stop it."""
        for words in ("Start it with `&` and print its process ID in the same command, such as `npm run dev & echo $!`.",
                      "If you didn't save the process ID, leave the program running and tell the site owner.",
                      "Don't look for it by port or name, such as with `pgrep` or `lsof`."):
            self.assertIn(words, self.code)

    def test_each_variable_is_checked_in_the_scope_where_it_will_be_written(self):
        guard = "If a variable or secret already has that name, stop and ask the site owner"
        self.assertIn(guard, self.variables)
        self.assertLess(self.variables.index(guard), self.variables.index("secret=\""))
        self.assertIn("If you cannot check the names, stop there.", self.variables)

    def test_mixed_changes_in_one_file_need_an_owner_decision_before_commit(self):
        self.assertIn("ask the site owner how to commit the changes", self.deploy)
        self.assertLess(self.deploy.index("ask the site owner how to commit"), self.deploy.index("git commit"))

    def test_the_upload_stops_when_git_status_finds_unrelated_changes(self):
        self.assertRegex(self.deploy, r"`git status`[^.]*\. If it shows unrelated changes, stop")

    def test_the_push_stops_when_an_outgoing_commit_is_unrelated(self):
        self.assertIn("If any outgoing commit is outside this installation, ask the site owner before pushing", self.deploy)
        self.assertLess(self.deploy.index("any outgoing commit"), self.deploy.index("git push"))

    def test_a_failed_live_deployment_uses_the_approved_rollback(self):
        self.assertIn("If the live site breaks, use the rollback in your approved plan", self.deploy)
        self.assertIn("Check the restored site and report the result to the site owner", self.deploy)


class InstallationGuardrails(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = dict(table(section(read(INSTALL_MD), "Never"), ("Never", "Instead")))

    def test_godaddy_cleanup_and_google_ssh_distinguish_new_and_existing_resources(self):
        godaddy = self.rules["Use `gddy dns set` or `gddy dns delete`"]
        self.assertIn("Add with `gddy dns add`.", godaddy)
        self.assertIn("Delete records in the browser.", godaddy)
        self.assertIn("new Google VM", self.rules["Change the project's metadata"])
        self.assertIn("confirmed SSH name", self.rules["Change the project's metadata"])

    def test_gcloud_ssh_and_scp_serve_only_the_google_server_that_the_agent_created(self):
        """On a server the site owner already has, `gcloud compute ssh` or `scp` can write the project's metadata, so the
        copy, the secret's command and the tunnel use gcloud only for the server created here."""
        install = flat(read(INSTALL_MD))
        for words in ("To copy the release files to a Google Cloud server that you created:",
                      "On a Google Cloud server that you created, use the `gcloud compute ssh` form inside `$(...)`.",
                      "On an existing server, `<server>` is the SSH name that the site owner gave you.",
                      "For a Google Cloud server that you created, the command is:"):
            self.assertIn(words, install)
        self.assertNotIn("On Google Cloud, the command is:", install)

    def test_the_fact_checks_corrections_stand(self):
        """The Opus fact check of r15: each correction where the agent reads it."""
        install = read(INSTALL_MD)
        text = flat(install)
        for words in ("The OCI command checks a known profile and user OCID. If either is unavailable, use the signed-in "
                      "browser.",
                      "Whether the site owner is signed in to the builder in the browser that your tool opens. You can "
                      "also check this read-only with your browser tool.",
                      "Turning on Compute Engine also adds Google's `default` network and firewall rules to the project. "
                      "An organization policy can prevent their creation.",
                      "If the host key changed, stop and ask the site owner to verify it. For other errors, ask the site "
                      "owner to connect once from their own terminal.",
                      "On an existing server, ask the site owner before using `sudo` if the SSH user can't run `docker`.",
                      "On an existing server, ask the site owner before using `sudo` for Docker. On a new server, follow "
                      "your approved plan.",
                      "The only packages to install are the ones that setup prints.",
                      "`vercel env list --environment production --project PROJECT --scope TEAM`",
                      "For a personal project, omit `--scope TEAM` from both commands."):
            self.assertIn(words, text)
        self.assertNotIn("ask the site owner whether to use `sudo` on this server", text)
        self.assertIn("Create resources before approval", dict(table(section(install, "Never"), ("Never", "Instead"))))

    def test_the_delete_commands_say_to_use_the_values_of_the_setup(self):
        step7 = flat(section(read(INSTALL_MD), "Step 7. Finish the setup"))
        self.assertIn("Use the values from this setup, such as your subdomain in place of `cake.example.com.`", step7)
        self.assertLess(step7.index("such as your subdomain"), step7.index("gcloud dns record-sets delete"))

    def test_the_secret_fallback_goes_to_its_specific_destination(self):
        self.assertIn("the platform's secret setting", self.rules["Ask for the secret's output"])
        local = self.rules["Commit a file that holds the secret"]
        for detail in ("owner", "ignored", "outside all published folders"):
            self.assertIn(detail, local)

    def test_all_data_remains_in_the_site_owners_destinations(self):
        self.assertEqual(self.rules["Send the site key or any data elsewhere"],
                         "Use only the site owner's AgentCake, website and platform")


if __name__ == "__main__":
    unittest.main()
