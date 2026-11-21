"""The coding agents the repository's own scripts start carry none of the person's MCP servers: tools/agent_home.py
gives Codex a home of its own and the flags that turn off the ChatGPT account's apps and plugins, and names Claude
Code's flag; tools/check_agent_mcp.py finds a script that starts either agent without them; the repository itself
passes it.

    python3 -I -m unittest discover -s tests -p test_agent_mcp.py      (from the AgentCake folder)

On 11/19 every Codex the judges, fact checks and benches started read the person's ~/.codex/config.toml, whose posthog
server sent a request to mcp.posthog.com on each start and whose node_repl runs code outside Codex's sandbox.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import tomllib
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
THREADS = 16  # as many threads as a judge run could ask for a home at once, and more
REAL_CONFIG = """model = "gpt-x"
model_reasoning_effort = "high"
personality = "friendly"
notify = ["say", "done"]

[mcp_servers.posthog]
url = "https://mcp.posthog.example/mcp"

[projects."/somewhere"]
trust_level = "trusted"
"""


def load_tool(name):
    spec = importlib.util.spec_from_file_location(f"tool_{name}", os.path.join(TOOLS, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(text))
    return path


class Scratch(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="agentcake-agent-mcp-")
        self.addCleanup(shutil.rmtree, self.root, True)


class CodexHome(Scratch):
    def setUp(self):
        super().setUp()
        self.real = os.path.join(self.root, "real-codex")
        write(self.root, "real-codex/auth.json", "{}")
        write(self.root, "real-codex/config.toml", REAL_CONFIG)
        self.home = load_tool("agent_home")

    def test_it_links_the_sign_in_and_holds_only_the_model_settings(self):
        folder = self.home.codex_home(os.path.join(self.root, "own"), real=self.real)
        self.assertEqual(sorted(os.listdir(folder)), ["auth.json", "config.toml"])
        link = os.path.join(folder, "auth.json")
        self.assertTrue(os.path.islink(link))
        self.assertEqual(os.path.realpath(link), os.path.realpath(os.path.join(self.real, "auth.json")))
        with open(os.path.join(folder, "config.toml"), "rb") as f:
            config = tomllib.load(f)
        self.assertEqual(config, {"model": "gpt-x", "model_reasoning_effort": "high", "personality": "friendly",
                                  "features": {name: False for name in self.home.FEATURES_OFF}})

    def test_the_features_that_reach_the_persons_accounts_or_devices_are_off(self):
        """Codex starts the ChatGPT account's apps (an MCP server at chatgpt.com, which a judge run of 11/19 still
        tried) and its plugins, and can drive the person's browser or computer, unless config.toml turns them off."""
        self.assertTrue({"apps", "plugins", "remote_plugin", "browser_use_external", "computer_use"}
                        <= set(self.home.FEATURES_OFF))

    def test_the_environment_sends_codex_there(self):
        own = os.path.join(self.root, "own")
        env = self.home.codex_env({"PATH": "/bin"}, own, real=self.real)
        self.assertEqual(env, {"PATH": "/bin", "CODEX_HOME": own})

    def test_without_a_folder_one_temporary_home_serves_the_process(self):
        first, second = self.home.codex_home(real=self.real), self.home.codex_home(real=self.real)
        self.assertEqual(first, second)
        self.assertTrue(os.path.realpath(first).startswith(os.path.realpath(tempfile.gettempdir()) + os.sep))

    def test_a_home_made_again_keeps_its_link(self):
        own = os.path.join(self.root, "own")
        self.home.codex_home(own, real=self.real)
        self.home.codex_home(own, real=self.real)
        self.assertTrue(os.path.islink(os.path.join(own, "auth.json")))

    def test_a_link_another_thread_made_first_is_kept(self):
        """The shared judge asks for its Codex home from several threads at once (--parallel). On 11/19 one thread saw
        no auth.json link, another made it, and the first one's FileExistsError cost a whole judge run."""
        own, symlink = os.path.join(self.root, "own"), os.symlink

        def another_thread_first(source, link):
            symlink(source, link)  # the other thread, between this one's look and its own link
            symlink(source, link)

        with mock.patch.object(os, "symlink", another_thread_first):
            self.home.codex_home(own, real=self.real)
        self.assertEqual(os.path.realpath(os.path.join(own, "auth.json")),
                         os.path.realpath(os.path.join(self.real, "auth.json")))

    def test_threads_asking_at_once_share_one_temporary_home(self):
        start, homes = threading.Barrier(THREADS), []

        def ask():
            start.wait()
            homes.append(self.home.codex_home(real=self.real))

        threads = [threading.Thread(target=ask) for _ in range(THREADS)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(homes), THREADS)
        self.assertEqual(len(set(homes)), 1)

    def test_a_home_made_again_with_the_same_settings_leaves_config_toml_as_it_is(self):
        """A Codex already started from this home may be reading config.toml: writing it again would empty it first."""
        own = os.path.join(self.root, "own")
        self.home.codex_home(own, real=self.real)
        config = os.path.join(own, "config.toml")
        os.chmod(config, 0o444)  # a write would now fail
        self.home.codex_home(own, real=self.real)
        os.chmod(config, 0o644)
        write(self.root, "real-codex/config.toml", REAL_CONFIG.replace("gpt-x", "gpt-y"))
        self.home.codex_home(own, real=self.real)
        with open(config, "rb") as f:
            self.assertEqual(tomllib.load(f)["model"], "gpt-y")

    def test_claude_code_gets_no_mcp_server_it_is_not_given(self):
        self.assertEqual(self.home.CLAUDE_NO_MCP, "--strict-mcp-config")

    def test_codex_is_told_on_its_command_line_to_leave_the_accounts_apps_and_plugins_off(self):
        """The ChatGPT account brings its apps (an MCP server at chatgpt.com) and plugins to any CODEX_HOME; both
        `codex exec` and `codex exec resume` get these flags."""
        self.assertEqual(self.home.CODEX_NO_APPS, ["-c", "features.apps=false", "-c", "features.plugins=false"])


def run_check(folder):
    done = subprocess.run([sys.executable, "-I", os.path.join(TOOLS, "check_agent_mcp.py"), folder],
                          capture_output=True, text=True)
    return done.returncode, done.stdout


class Check(Scratch):
    def test_a_codex_command_without_a_home_of_its_own_is_found(self):
        write(self.root, "scripts/scorer.py", 'CODEX = ["codex", "exec", "--ephemeral"] + agent_home.CODEX_NO_APPS\n'
                                             'subprocess.run(CODEX)\n')
        code, out = run_check(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("scripts/scorer.py", out)

    def test_a_codex_command_that_leaves_the_accounts_apps_on_is_found(self):
        write(self.root, "scorer.py", 'CODEX = ["codex", "exec"]\nsubprocess.run(CODEX, env=agent_home.codex_env())\n')
        write(self.root, "half.py", 'argv = ["codex", "exec", "-c", "features.apps=false"]\nenv = {"CODEX_HOME": h}\n')
        code, out = run_check(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("scorer.py", out)
        self.assertIn("half.py", out)

    def test_codex_with_a_home_of_its_own_or_without_the_users_config_passes(self):
        write(self.root, "a.py", 'CODEX = ["codex", "exec"] + agent_home.CODEX_NO_APPS\n'
                                 'subprocess.run(CODEX, env=agent_home.codex_env())\n')
        write(self.root, "b.py", 'cmd = [brain["binary"], "exec", "--ignore-user-config",\n'
                                 '       "-c", "features.apps=false", "-c", "features.plugins=false", "--json"]\n')
        write(self.root, "c.py", 'env = dict(os.environ, CODEX_HOME=home)\n'
                                 'argv = ["codex", "exec", "-c", "features.apps=false",\n'
                                 '        "-c", "features.plugins=false"]\n')
        write(self.root, "d.py", 'env = dict(os.environ, CODEX_HOME=home)\n'
                                 'argv = ["codex", "exec", *[part for name in off\n'
                                 '                           for part in ("-c", f"features.{name}=false")]]\n')
        self.assertEqual(run_check(self.root), (0, "check_agent_mcp: 0 script(s) start an agent with the "
                                                   "person's MCP servers\n"))

    def test_a_binary_named_by_a_subscript_is_a_command_too(self):
        write(self.root, "brain.py", 'cmd = [brain["binary"], "exec", "--ignore-user-config", "--json"]\n')
        write(self.root, "tools.py", 'cmd = [paths["claude"], "-p", prompt, "--model", model]\n')
        code, out = run_check(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("brain.py: Codex without features.apps=false", out)
        self.assertIn("tools.py: claude -p without --strict-mcp-config", out)

    def test_claude_print_mode_without_strict_mcp_config_is_found(self):
        write(self.root, "t22.py", 'subprocess.run(["claude", "-p", task, "--permission-mode", "acceptEdits"])\n')
        write(self.root, "ok.py", 'subprocess.run([shutil.which("claude"), "-p", task, "--strict-mcp-config"])\n')
        code, out = run_check(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("t22.py", out)
        self.assertNotIn("ok.py", out)

    def test_a_mark_in_a_comment_or_docstring_gives_no_home(self):
        write(self.root, "bench.py", '"""Codex reads CODEX_HOME; claude gets --strict-mcp-config."""\n'
                                     'BASE = ["codex", "exec", "--json"] + CODEX_NO_APPS  # under CODEX_HOME\n'
                                     'CLAUDE = ["claude", "-p"]  # --strict-mcp-config later\n')
        code, out = run_check(self.root)
        self.assertEqual(code, 1, out)
        self.assertEqual(out.count("bench.py"), 2, out)

    def test_a_shell_script_counts_too(self):
        write(self.root, "run.sh", 'codex exec "hello"\nclaude -p "hello"\n')
        code, out = run_check(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("run.sh", out)

    def test_mentions_and_tests_are_no_commands(self):
        write(self.root, "doc.py", '"""A fresh `codex exec --ephemeral` session, or `claude -p`."""\n')
        write(self.root, "tests/test_x.py", 'self.assertEqual(argv[:2], ["codex", "exec"])\n')
        write(self.root, "tests/fake_claude.py", 'ARGV = ["claude", "-p"]\n')
        write(self.root, "web/node_modules/x/run.js", 'spawn(["codex", "exec"])\n')
        self.assertEqual(run_check(self.root)[0], 0)

    def test_a_script_marked_exempt_with_its_reason_is_skipped_and_one_without_a_reason_is_not(self):
        write(self.root, "old/scorer.py", '# check_agent_mcp: exempt, not run since its job ended\n'
                                         'CODEX = ["codex", "exec"]\n')
        self.assertEqual(run_check(self.root)[0], 0)
        write(self.root, "older/scorer.py", '# check_agent_mcp: exempt\nCODEX = ["codex", "exec"]\n')
        code, out = run_check(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("older/scorer.py", out)

    def test_an_agy_command_without_isolated_home_or_settings_is_found(self):
        write(self.root, "bare.py", 'subprocess.run(["agy", "-p", prompt])\n')
        write(self.root, "no_settings.py",
              'subprocess.run(["agy", "--input-format", "stream-json"], env=agent_home.agy_env())\n')
        write(self.root, "no_home.py",
              'subprocess.run(["agy", "-p", prompt, "--settings", settings_path])\n')
        write(self.root, "run.sh", 'agy -p "hello"\n')
        code, out = run_check(self.root)
        self.assertEqual(code, 1, out)
        for name in ("bare.py", "no_settings.py", "no_home.py", "run.sh"):
            self.assertIn(name, out)

    def test_agy_with_isolated_home_and_settings_passes(self):
        write(self.root, "a.py",
              'subprocess.run(["agy", "--input-format", "stream-json", "--settings", cfg], env=agent_home.agy_env())\n')
        write(self.root, "b.py",
              'subprocess.run(agent_home.agy_command(cfg), env=agent_home.agy_env())\n')
        write(self.root, "c.sh", 'HOME="$TMP_HOME" agy -p "hello" --settings "$CFG"\n')
        self.assertEqual(run_check(self.root), (0, "check_agent_mcp: 0 script(s) start an agent with the "
                                                   "person's MCP servers\n"))


class Repository(unittest.TestCase):
    def test_every_script_starts_its_agents_without_the_persons_mcp_servers(self):
        code, out = run_check(ROOT)
        self.assertEqual(code, 0, out)

    def test_every_exemption_is_still_a_script_that_starts_an_agent(self):
        """A script marked exempt that no longer starts an agent should lose its mark."""
        load_tool("check_agent_mcp")
        check = load_tool("check_agent_mcp")
        rules = check.limits("check_agent_mcp")
        for rel in check.scripts(ROOT, rules):
            with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as f:
                text = f.read()
            if check.EXEMPT.search(text):
                with self.subTest(script=rel):
                    self.assertTrue(check.starts_an_agent(rel, text))


if __name__ == "__main__":
    unittest.main()
