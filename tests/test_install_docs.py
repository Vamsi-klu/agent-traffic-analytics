"""INSTALL.md, README.md (and its Chinese translation) and AGENTS.md against the code and the release (S6.2).

    python3 -I -m unittest discover -s tests -v      (from the AgentCake folder)

INSTALL.md is what a coding agent follows to install AgentCake, one command at a time: every code block holds one
command, with no `&&`, `;`, `|`, `$` or `NAME=value`, because Claude Code's approval rules match a command by how it
starts and cannot check a variable in advance (plan note 9). Its download URLs, file names and version are the ones
tools/release.py builds from agentcake/__init__.py (S6.4). While the repository is a private preview, its release
and raw.githubusercontent.com addresses need a GitHub sign-in that curl does not have: INSTALL.md's step 2 and both
READMEs download the release with `gh release download` before the same `shasum -c` line (readme-preview); the
READMEs' own checks (install sentence, pictures, badges, the Chinese translation) are in test_readme_docs.py. Every
`agentcake` command the documents show is one the command line lists in `agentcake help`, with
settings that exist, and INSTALL.md's own `agentcake` commands run in a scratch CAKE_HOME without a usage error. Every
link to a file of the repository exists, the local page's port is the default one, and the least Python INSTALL.md
and the READMEs name is pyproject.toml's requires-python (read as test_server_docs.py reads it). INSTALL.md and
AGENTS.md say the installing agent never registers for the user (D32), and no root document or file of docs/ splits
the product's name.
Two lessons of the S6.6 runs: the download is checked by `shasum -c`'s OK line alone, and a download that fails
without network is called that.
"""
import glob
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from agentcake import config  # noqa: E402  (needs the path above)
from agentcake.cli import EXIT_USAGE, help_text  # noqa: E402
from agentcake.wording import product, text  # noqa: E402
from cake_server import AGENTCAKE, ROOT, free_port, read  # noqa: E402
from test_server_docs import minimum_pythons, required_python  # noqa: E402
from tools.releasing import settings as release_settings  # noqa: E402
from tools.releasing.project import Project  # noqa: E402

INSTALL_MD = os.path.join(ROOT, "INSTALL.md")
README_MD = os.path.join(ROOT, "README.md")
README_ZH = os.path.join(ROOT, "docs", "locales", "zh-CN", "README.md")
AGENTS_MD = os.path.join(ROOT, "AGENTS.md")
CLAUDE_MD = os.path.join(ROOT, "CLAUDE.md")
SHOWN_TO_AGENTS = (INSTALL_MD, README_MD, README_ZH, AGENTS_MD)
# Each README, the heading of its Install and Connect sections, and whether its sentences are Chinese (D21).
READMES = ((README_MD, "Install", "Connect your website", False), (README_ZH, "安装", "接入你的网站", True))

SHELL_SYNTAX = ("&", ";", "|", ">", "<", "$", "`")  # chaining, pipes, redirection, variables, command substitution
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
STARTS_A_SERVER = {"start"}  # the one INSTALL.md command that leaves a process running; the help check covers it
HELP_ITSELF = ("help",)  # `agentcake help` prints the command list, so the list does not name it (cli.main)
VERSION = re.compile(r"(?<![\w.])\d+\.\d+\.\d+(?![\w.]*\d)")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
LINK_ADDRESS = re.compile(r"\]\((https?://[^)\s]+)\)")  # a Markdown link's or picture's address, between its brackets
WRITTEN_URL = re.compile(r"https?://[^\s`<>\"]+")
INLINE_COMMAND = re.compile(r"`(agentcake (?:--)?[a-z][^`]*)`")


def code_blocks(markdown):
    """The lines of each fenced code block, fences indented inside a list item included."""
    blocks = re.findall(r"^[ \t]*```[^\n]*\n(.*?)^[ \t]*```", markdown, re.M | re.S)
    return [[line.strip() for line in block.splitlines() if line.strip()] for block in blocks]


def section(markdown, heading):
    """The text under one `## heading`, up to the next `## `."""
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", markdown, re.M | re.S)
    if not match:
        raise AssertionError(f"no section '## {heading}'")
    return match.group(1)


def command_words(command):
    """The words after the command's name: `agentcake config set port 7878` -> ['config', 'set', 'port', '7878']."""
    return shlex.split(command)[1:]


def documented_commands(markdown):
    """Every `agentcake …` command in a code block or in inline code (not `agentcake 0.4.0`, an output)."""
    name = product()["command"]
    in_blocks = [line for block in code_blocks(markdown) for line in block if line.split()[0] == name]
    return in_blocks + INLINE_COMMAND.findall(markdown)


def listed_forms():
    """The command forms `agentcake help` lists after "Commands:", one or more a line between `|`, each up to its
    first placeholder or option in brackets: "setup --print --site [--dir DIR]" -> ('setup', '--print', '--site').
    A note in parentheses may run over two lines."""
    listing = re.sub(r"\([^)]*\)", " ", help_text().partition("Commands:")[2])
    forms = {HELP_ITSELF}
    for alternative in (part for line in listing.splitlines() for part in line.split("|")):
        words = []
        for word in alternative.split():
            if not re.match(r"^(--)?[a-z][a-z-]*$", word):
                break
            words.append(word)
        if words:
            forms.add(tuple(words))
    return forms


def repositories(markdown):
    """owner/name of every GitHub repository a text links to (github.com and raw.githubusercontent.com)."""
    return set(re.findall(r"https://(?:github\.com|raw\.githubusercontent\.com)/([\w.-]+/[\w.-]+)", markdown))


def urls(markdown):
    """Every address a text gives: each Markdown link's or picture's, as written between its brackets (the bracket
    that closes it is Markdown's, not the address's), and each one written out in the text."""
    return LINK_ADDRESS.findall(markdown) + WRITTEN_URL.findall(LINK_ADDRESS.sub("]", markdown))


def gh_download(tag, repository):
    """The command that downloads every file of a release with a signed-in GitHub CLI, into the current folder."""
    return f"gh release download {tag} --repo {repository}"


def release_tag():
    """This checkout's version and its tag, as tools/release.py names them."""
    settings = release_settings.load()
    version = Project(ROOT, settings).version
    return version, settings["tag_prefix"] + version


def readme_name(readme):
    """The product's name as README's title gives it: "# AgentCake — …"."""
    return re.search(r"^# (.+?) — ", readme, re.M).group(1)


class InstallDocuments(unittest.TestCase):
    """What a coding agent reads to install AgentCake matches the release, the command line and the plan's rules."""

    @classmethod
    def setUpClass(cls):
        cls.install, cls.readme, cls.agents = read(INSTALL_MD), read(README_MD), read(AGENTS_MD)
        cls.readme_zh = read(README_ZH)
        settings = release_settings.load()
        project = Project(ROOT, settings)
        cls.version, cls.tag = release_tag()
        cls.wheel = project.wheel_name()
        cls.pyz, cls.checksums = (release_settings.file_name(settings, kind, project.name, project.version)
                                  for kind in ("pyz", "checksums"))
        cls.release_folder = project.sdist_base()
        cls.release_files = {cls.wheel, cls.pyz, cls.checksums, cls.release_folder + ".tar.gz"}
        cls.readme_name = readme_name(cls.readme)

    def repository(self):
        """The one repository INSTALL.md downloads from (test_one_repository_everywhere: the only one named)."""
        repository, = repositories(self.install)
        return repository

    # ---------------------------------------------------------------------------------------- one command per step
    def test_every_code_block_in_install_md_holds_one_command(self):
        blocks = code_blocks(self.install)
        self.assertTrue(blocks)
        for block in blocks:
            self.assertEqual(len(block), 1, f"one command per block: {block}")
            command = block[0]
            for syntax in SHELL_SYNTAX:
                self.assertNotIn(syntax, command, f"{command!r} chains, pipes, redirects or reads a variable")
            self.assertFalse(ASSIGNMENT.match(command), f"{command!r} sets a variable")

    # ---------------------------------------------------------------------------------------- the release
    def test_urls_end_where_an_agent_copying_them_would_stop(self):
        """No URL runs straight into a full stop, comma or bracket, which an agent could take as part of it."""
        for path in (INSTALL_MD, README_MD, README_ZH):
            found = urls(read(path))
            self.assertTrue(found, path)
            for url in found:
                self.assertNotIn(url[-1], ".,;:)", f"{os.path.basename(path)}: {url}")

    def test_a_markdown_links_closing_bracket_is_not_part_of_its_url(self):
        """README's badges and links are Markdown; a URL written into a sentence still may not end in a bracket."""
        self.assertEqual(urls("[![Issues](https://img.shields.io/badge/a-b-c)](https://github.com/o/r/issues)"),
                         ["https://img.shields.io/badge/a-b-c", "https://github.com/o/r/issues"])
        self.assertEqual(urls("(see https://example.com/a)"), ["https://example.com/a)"])
        self.assertEqual(urls('<img src="https://example.com/a.png">'), ["https://example.com/a.png"])

    def test_download_urls_are_the_files_of_this_release(self):
        downloads = re.findall(r"https://github\.com/[\w.-]+/[\w.-]+/releases/download/([^/\s`]+)/([^\s`]+)",
                               self.install)
        self.assertEqual({tag for tag, _ in downloads}, {self.tag})
        self.assertLessEqual({name for _, name in downloads}, self.release_files)
        self.assertLessEqual({self.wheel, self.pyz, self.checksums}, {name for _, name in downloads})
        pages = re.findall(r"https://github\.com/[\w.-]+/[\w.-]+/releases/tag/([^\s`/]+)", self.install)
        self.assertEqual(set(pages), {self.tag})

    def test_file_names_and_versions_in_install_md_are_this_releases(self):
        names = {name.rstrip(".") for name in re.findall(r"\bagentcake[-.][\w.+-]*", self.install)}
        self.assertTrue(names)
        self.assertLessEqual(names, self.release_files | {self.release_folder})
        self.assertEqual(set(VERSION.findall(self.install)), {self.version})

    def test_a_private_preview_is_downloaded_with_gh_and_checked_the_same_way(self):
        """While the repository is private, curl gets a 404 for its release; INSTALL.md's step 2 checks that the GitHub
        CLI is signed in and downloads the release into this folder with it, and the one shasum line comes after both
        ways of downloading. Both READMEs' Install give the same command, as their "Private preview" item."""
        download = gh_download(self.tag, self.repository())
        step = section(self.install, "Step 2. Download the release and check it")
        commands = [block[0] for block in code_blocks(step)]
        self.assertIn("gh auth status", commands)
        self.assertIn(download, commands)
        checksum = commands.index("shasum -a 256 -c SHA256SUMS --ignore-missing")
        self.assertLess(commands.index(download), checksum)
        self.assertLess(max(i for i, command in enumerate(commands) if command.startswith("curl ")), checksum)
        for path, install_heading, _, _ in READMES:
            install = section(read(path), install_heading)
            self.assertIn(f"`{download}`", install, path)

    def test_one_repository_everywhere(self):
        found = repositories(self.install) | repositories(self.readme)
        self.assertEqual(len(found), 1, found)

    # ---------------------------------------------------------------------------------------- the command line
    def test_every_agentcake_command_shown_is_one_the_command_line_lists(self):
        forms = listed_forms()
        for path in SHOWN_TO_AGENTS:
            commands = documented_commands(read(path))
            self.assertTrue(commands, path)
            for command in commands:
                words = command_words(command)
                self.assertTrue(any(tuple(words[:len(form)]) == form for form in forms),
                                f"{os.path.basename(path)}: `{command}` is not in `agentcake help`")
                if words[:2] == ["config", "set"]:
                    self.assertIn(words[2], config.SETTABLE, command)

    def test_install_md_commands_run_without_a_usage_error(self):
        """Each in a scratch CAKE_HOME on a free port, where no AgentCake runs: doctor may say so, but no command may
        be one the command line does not understand, or end in a traceback. The data folder exists, as
        `agentcake start` (step 4) leaves it before every later step."""
        for block in code_blocks(self.install):
            words = shlex.split(block[0])
            if words[0] != product()["command"] or words[1] in STARTS_A_SERVER:
                continue
            home = tempfile.mkdtemp(prefix="agentcake-install-md-")
            self.addCleanup(shutil.rmtree, home, True)
            env = dict(os.environ, CAKE_HOME=home, CAKE_PORT=str(free_port()))
            done = subprocess.run(AGENTCAKE + words[1:], env=env, cwd=home, capture_output=True, text=True)
            self.assertNotEqual(done.returncode, EXIT_USAGE, f"{block[0]}: {done.stdout}{done.stderr}")
            self.assertNotIn("Traceback", done.stderr, block[0])

    # ---------------------------------------------------------------------------------------- links and addresses
    def test_links_to_files_of_the_repository_exist(self):
        for path in SHOWN_TO_AGENTS:
            for target in LINK.findall(read(path)):
                if re.match(r"^(https?:|mailto:|#)", target):
                    continue
                local = os.path.join(os.path.dirname(path), target.split("#")[0])
                self.assertTrue(os.path.exists(local), f"{os.path.basename(path)} links to {target}, which is missing")

    def test_the_least_python_is_pyproject_requires_python(self):
        for path in (INSTALL_MD, README_MD):
            self.assertEqual(minimum_pythons(read(path)), {required_python()}, path)
        self.assertEqual(re.findall(r"Python (\d+\.\d+) 或更新", self.readme_zh), [required_python()])

    def test_the_local_page_is_on_the_default_port(self):
        for path in SHOWN_TO_AGENTS:
            ports = set(re.findall(r"127\.0\.0\.1:(\d+)", read(path)))
            self.assertEqual(ports, {str(config.DEFAULTS["port"])}, path)

    # ---------------------------------------------------------------------------------------- what the agent says
    def test_the_installing_agent_never_registers_for_the_user(self):
        """D32: the local page asks the user to register; the agent gives the address and nothing more."""
        for words in ("never fill in their e-mail address", 'press "Register & Continue" for them'):
            self.assertIn(words, " ".join(self.install.split()))
            self.assertIn(words, " ".join(self.agents.split()))

    def test_whether_agentcake_is_on_path_is_left_to_doctors_line(self):
        """S6.6: told that uv's folder "may not be on PATH", Claude Code told the user it was not, while doctor's own
        line said it was. INSTALL.md says nothing an agent can repeat as a fact and sends it to doctor's line."""
        flat = " ".join(self.install.split())
        self.assertNotRegex(flat, r"(?i)(?:may|might|is) not (?:be )?on PATH")
        self.assertIn(text("doctor_path", command=product()["command"]), flat)

    def test_the_download_is_checked_by_the_checksum_command_alone(self):
        """S6.6 (GOAL T1): in a trial run Claude Code printed SHA256SUMS and the file's hash and compared them itself,
        with no OK line. Step 2 says the command's OK line alone decides."""
        step = section(self.install, "Step 2. Download the release and check it")
        self.assertIn(["shasum -a 256 -c SHA256SUMS --ignore-missing"], code_blocks(step))
        flat = " ".join(step.split())
        for words in ("this command alone decides", "Do not print hashes and compare them yourself"):
            self.assertIn(words, flat)

    def test_a_download_without_network_is_called_no_network(self):
        """S6.6 (GOAL T2, no network): curl failed with "Couldn't connect to server" and Codex asked the user to start
        that server. The sandbox section names curl's errors without network and says to ask for network access."""
        sandbox = " ".join(section(self.install, "If you run in a sandbox").split())
        for words in ("Could not resolve host", "Couldn't connect to server", "there is no network access here",
                      "Do not say a server is down or has to be started"):
            self.assertIn(words, sandbox)

    def test_the_documents_spell_the_product_as_readme_does(self):
        """D19: one word since 11/12. The root documents and docs/ never split README's name ("Agent Cake"); README's
        pictures in docs/assets/ are not text."""
        split = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", self.readme_name)
        documents = glob.glob(os.path.join(ROOT, "*.md")) + [path for path in glob.glob(os.path.join(ROOT, "docs", "*"))
                                                              if os.path.isfile(path)]
        self.assertTrue(documents)
        for path in sorted(documents):
            self.assertNotIn(split, read(path), os.path.relpath(path, ROOT))

    def test_agents_md_keeps_the_interface_rules_and_claude_md_includes_it(self):
        for rule in ("INSTALL.md", "DESIGN.md", "npm run check:ui", "npm run visual"):
            self.assertIn(rule, self.agents)
        self.assertEqual(read(CLAUDE_MD).splitlines()[0], "@AGENTS.md")


if __name__ == "__main__":
    unittest.main()
