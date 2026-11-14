"""The three code checks (S1.2): tools/check_hardcode.py, check_size.py and check_imports.py each find what they are
for and skip what they must skip, and the repository itself passes all three.

    python3 -I -m unittest discover -s tests -v      (from the Agent Cake folder)

Each check runs as people run it, as a script, on a scratch folder holding the case.
"""
import json, os, shutil, subprocess, sys, tempfile, textwrap, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
with open(os.path.join(TOOLS, "limits.json"), encoding="utf-8") as _f:
    _SIZE = json.load(_f)["check_size"]
MAX_LINES = _SIZE["max_lines"]
# What limits.json exempts from the size check, as files to write: a folder gets a script of its own inside.
SIZE_EXEMPT = [rel if os.path.splitext(rel)[1] else rel + "/tool.py" for rel in _SIZE["exempt"]]


def run_tool(script, *args):
    out = subprocess.run([sys.executable, "-I", os.path.join(TOOLS, script), *args], capture_output=True, text=True)
    return out.returncode, out.stdout


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(text))


class ScratchFolder(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="agentcake-tools-")
        self.addCleanup(shutil.rmtree, self.root, True)


class Repository(unittest.TestCase):
    """The repository as it is."""

    def test_no_value_is_written_into_the_code(self):
        code, out = run_tool("check_hardcode.py")
        self.assertEqual(code, 0, out)

    def test_no_source_file_is_over_the_line_limit(self):
        code, out = run_tool("check_size.py")
        self.assertEqual(code, 0, out)

    def test_agentcake_imports_only_the_standard_library(self):
        code, out = run_tool("check_imports.py")
        self.assertEqual(code, 0, out)

    def test_tools_import_only_the_standard_library_agentcake_and_themselves(self):
        code, out = run_tool("check_imports.py", TOOLS)
        self.assertEqual(code, 0, out)


class CheckHardcode(ScratchFolder):
    def check(self):
        return run_tool("check_hardcode.py", self.root)

    def test_finds_a_magic_number(self):
        write(self.root, "agentcake/limits.py", "BATCH = 42\n")
        code, out = self.check()
        self.assertEqual(code, 1)
        self.assertIn("agentcake/limits.py:1: number 42", out)

    def test_allows_zero_one_minus_one_booleans_and_protocol_lines(self):
        write(self.root, "agentcake/ok.py", """\
            NONE, ONE, MINUS_ONE, YES = 0, 1, -1, True
            NOT_FOUND = 404  # protocol: HTTP status
            """)
        self.assertEqual(self.check()[0], 0)

    def test_does_not_read_docstrings_or_comments(self):
        write(self.root, "agentcake/doc.py", '''\
            """Listens on 127.0.0.1:7878 and draws #ff0000; 42 is the answer."""
            # localhost, http://example.com and 99 in a comment
            ''')
        self.assertEqual(self.check()[0], 0)

    def test_finds_colours_and_addresses_in_strings(self):
        write(self.root, "agentcake/strings.py", """\
            ACCENT = "#c2410c"
            SHADE = "rgba(0, 0, 0, .5)"
            LOOPBACK = "127.0.0.1"
            NAME = "localhost"
            SITE = "https://example.com/x"
            DATABASE = "db.example.com:5432"
            """)
        code, out = self.check()
        self.assertEqual(code, 1)
        self.assertIn("check_hardcode: 6 value(s)", out)

    def test_finds_numbers_in_javascript_sources_but_not_in_their_strings_or_comments(self):
        write(self.root, "agentcake/static/src/send.js", """\
            // 99 in a comment
            var batch = 50, none = 0, one = 1;
            var label = 'item 77';
            var https = 443; // protocol: default port
            """)
        code, out = self.check()
        self.assertEqual(code, 1)
        self.assertIn("agentcake/static/src/send.js:2: number 50", out)
        self.assertIn("check_hardcode: 1 value(s)", out)

    def test_skips_the_files_limits_json_exempts(self):
        write(self.root, "agentcake/static/src/botscent.js", "var css = 'body{color:#fff;max-width:1000px}'\nvar limit = 200\n")
        self.assertEqual(self.check()[0], 0)


class CheckSize(ScratchFolder):
    def check(self):
        return run_tool("check_size.py", self.root)

    def test_finds_a_file_over_the_limit(self):
        write(self.root, "agentcake/big.py", "x = 0\n" * (MAX_LINES + 1))
        code, out = self.check()
        self.assertEqual(code, 1)
        self.assertIn(f"agentcake/big.py: {MAX_LINES + 1} lines", out)

    def test_a_file_at_the_limit_passes(self):
        write(self.root, "web/src/Page.tsx", "x;\n" * MAX_LINES)
        self.assertEqual(self.check()[0], 0)

    def test_skips_installed_packages_and_what_limits_json_exempts(self):
        big = "x;\n" * (MAX_LINES + 1)
        for rel in ("web/node_modules/pkg/index.js", "notes/readme.md", *SIZE_EXEMPT):
            write(self.root, rel, big)
        self.assertEqual(self.check()[0], 0)


class CheckImports(ScratchFolder):
    def test_finds_a_third_party_import(self):
        write(self.root, "agentcake/fetch.py", "import json\nimport requests\n")
        code, out = run_tool("check_imports.py", os.path.join(self.root, "agentcake"))
        self.assertEqual(code, 1)
        self.assertIn("agentcake/fetch.py:2: imports requests", out)

    def test_allows_the_standard_library_and_relative_imports(self):
        write(self.root, "agentcake/ok.py", "import json\nfrom http import HTTPStatus\nfrom . import paths\n")
        self.assertEqual(run_tool("check_imports.py", os.path.join(self.root, "agentcake"))[0], 0)

    def test_allows_a_newer_standard_library_module_on_an_older_python(self):
        # compression is standard library from Python 3.14; agentcake imports it with a fallback (codecs.py)
        write(self.root, "agentcake/codec.py", "try:\n    from compression import zstd\nexcept ImportError:\n    zstd = None\n")
        self.assertEqual(run_tool("check_imports.py", os.path.join(self.root, "agentcake"))[0], 0)

    def test_tools_may_import_agentcake_and_their_own_package_but_nothing_else(self):
        write(self.root, "tools/made_up/rows.py", "from agentcake.detect import segment\nfrom tools.made_up import rules\n")
        self.assertEqual(run_tool("check_imports.py", os.path.join(self.root, "tools"))[0], 0)
        write(self.root, "tools/made_up/plot.py", "import numpy\n")
        code, out = run_tool("check_imports.py", os.path.join(self.root, "tools"))
        self.assertEqual(code, 1)
        self.assertIn("check_imports: 1 import(s)", out)

    def test_skips_the_files_limits_json_exempts(self):
        # tools/blockers/match.py runs only in a venv of its own, with the matcher it imports
        write(self.root, "tools/blockers/match.py", "import adblock\n")
        self.assertEqual(run_tool("check_imports.py", os.path.join(self.root, "tools"))[0], 0)
        write(self.root, "tools/blockers/check.py", "import adblock\n")
        code, out = run_tool("check_imports.py", os.path.join(self.root, "tools"))
        self.assertEqual(code, 1)
        self.assertIn("tools/blockers/check.py:1: imports adblock", out)


if __name__ == "__main__":
    unittest.main()
