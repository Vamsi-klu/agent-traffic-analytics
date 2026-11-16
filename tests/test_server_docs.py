"""SERVER.md, deploy/cake.service, Dockerfile and .dockerignore against the code.

    python3 -I -m unittest discover -s tests -v      (from the Agent Cake folder)

Every `agentcake` command in SERVER.md's code blocks runs in a scratch CAKE_HOME, every setting it names exists, and
the public paths, load balancer headers, data folder files and Python version it states are the code's. The unit
file and the image run `agentcake serve` the same way, isolated (-I), on the same data folder, as a user that is not
root; the image is python:3.14-slim, exposes only the public port, checks its health with `agentcake status` and is
built from the wheel alone. Neither Docker nor systemd is needed: the files are read the way they read them.
"""
import configparser
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from agentcake import config, netfacts, paths, routes  # noqa: E402  (needs the path above)
from agentcake.detect import lists  # noqa: E402
from cake_server import PREFIX, ROOT, SERVER_MD, documented_public_routes, free_port, read, run_cli  # noqa: E402

UNIT_FILE = os.path.join(ROOT, "deploy", "cake.service")
DOCKERFILE = os.path.join(ROOT, "Dockerfile")
DOCKERIGNORE = os.path.join(ROOT, ".dockerignore")
PYPROJECT = os.path.join(ROOT, "pyproject.toml")
STORAGE_FILE = os.path.join(paths.PACKAGE_DIR, "data", "storage.json")
LONG_RUNNING = {"serve"}  # SERVER.md commands that do not return; test_server_mode.py runs `serve` itself
SHELL_OPERATORS = ("|", "||", "&&", ";")
MINIMUM_PYTHON = re.compile(r"`?\b[Pp]ython3?`?\s+(\d+\.\d+) or (?:newer|later)")


def minimum_pythons(markdown):
    """The Python versions a text gives as the least it needs, however it names Python: "Python 3.11 or newer",
    "Python 3.11 or later", "`python3` 3.11 or newer", "python3 3.11 or newer"."""
    return set(MINIMUM_PYTHON.findall(markdown))


def required_python():
    """The X.Y of pyproject.toml's requires-python = ">=X.Y"."""
    return re.search(r'^requires-python\s*=\s*">=\s*([\d.]+)"', read(PYPROJECT), re.M).group(1)


def code_block_lines(markdown):
    """Every line inside the fenced code blocks of a Markdown text."""
    return [line.strip() for block in re.findall(r"^```[^\n]*\n(.*?)^```", markdown, re.M | re.S)
            for line in block.splitlines() if line.strip()]


def agentcake_commands(markdown):
    """The arguments of every Agent Cake command in the code blocks: `agentcake …`, `python3 -I -m agentcake …` or
    `…/agentcake/__main__.py …`, up to a pipe, `&&`, `;`, a comment, or the quote that ends a command for ssh."""
    commands = []
    for line in code_block_lines(markdown):
        if line.startswith("alias "):
            continue
        match = re.search(r"(?:^agentcake|-m agentcake|agentcake/__main__\.py)\s+([^'\"]+)", line)
        if match:
            words = shlex.split(match.group(1), comments=True)
            operators = [i for i, word in enumerate(words) if word in SHELL_OPERATORS]
            commands.append(words[:operators[0]] if operators else words)
    return commands


def section(markdown, heading):
    """The text under one `## heading`, up to the next `## `."""
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", markdown, re.M | re.S)
    if not match:
        raise AssertionError(f"SERVER.md has no section '## {heading}'")
    return match.group(1)


def first_column_names(text):
    """The `backticked` names in the first cell of each table row."""
    names = []
    for line in text.splitlines():
        cells = line.split("|")
        if line.startswith("|") and len(cells) > 2 and not set(cells[1].strip()) <= set("-: "):
            names += re.findall(r"`([^`]+)`", cells[1])
    return names


def unit_file():
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str  # systemd keys are case-sensitive
    parser.read(UNIT_FILE, encoding="utf-8")
    return parser


def dockerfile_instructions():
    """The Dockerfile as (INSTRUCTION, arguments): comment lines dropped and continuation lines joined, the way Docker
    reads the file."""
    kept = "\n".join(line for line in read(DOCKERFILE).splitlines() if not line.lstrip().startswith("#"))
    return [(line.strip().partition(" ")[0].upper(), line.strip().partition(" ")[2].strip())
            for line in re.sub(r"\\\n", " ", kept).splitlines() if line.strip()]


def final_stage():
    """The base image and the instructions of the Dockerfile's last stage, with ${ARG} defaults filled in."""
    args, stage, base = {}, [], None
    for instruction, rest in dockerfile_instructions():
        rest = re.sub(r"\$\{(\w+)\}", lambda m: args.get(m.group(1), m.group(0)), rest)
        if instruction == "ARG" and "=" in rest:
            name, _, default = rest.partition("=")
            args[name.strip()] = default.strip()
        elif instruction == "FROM":
            stage, base = [], rest.split()[0]
        stage.append((instruction, rest))
    return base, stage


def instruction_values(stage, name):
    return [rest for instruction, rest in stage if instruction == name]


class DocumentsMatchCode(unittest.TestCase):
    """SERVER.md, deploy/cake.service, Dockerfile and .dockerignore say what the code on this branch does."""

    @classmethod
    def setUpClass(cls):
        cls.server_md = read(SERVER_MD)
        cls.unit = unit_file()
        cls.base_image, cls.final_stage = final_stage()

    def public_port_in_server_md(self):
        listens = [c[3] for c in agentcake_commands(self.server_md) if c[:3] == ["config", "set", "public_listen"]]
        self.assertTrue(listens, "SERVER.md sets public_listen")
        return int(listens[0].rpartition(":")[2])

    def unit_data_folder(self):
        return self.unit["Service"]["Environment"].partition("CAKE_HOME=")[2].split()[0]

    # ---------------------------------------------------------------------------------------- SERVER.md
    def test_every_agentcake_command_in_server_md_runs(self):
        commands = agentcake_commands(self.server_md)
        self.assertTrue(commands)
        home = tempfile.mkdtemp(prefix="agentcake-server-md-")
        self.addCleanup(shutil.rmtree, home, True)
        env = dict(os.environ, CAKE_HOME=home, CAKE_PORT=str(free_port()))  # status finds nothing, never another cake
        for words in commands:
            if words[0] in LONG_RUNNING:
                continue
            done = run_cli(env, *words)
            allowed = (0, 1) if words[0] == "status" else (0,)  # status says 1 when nothing runs here
            self.assertIn(done.returncode, allowed, f"agentcake {' '.join(words)}: {done.stdout}{done.stderr}")

    def test_every_setting_server_md_names_exists(self):
        named = set(first_column_names(section(self.server_md, "Settings")))
        named |= {c[2] for c in agentcake_commands(self.server_md) if c[:2] == ["config", "set"]}
        self.assertTrue(named)
        self.assertEqual(named - config.SETTABLE, set())

    def test_public_paths_in_server_md_are_the_public_routes(self):
        self.assertEqual(documented_public_routes(self.server_md), {(r.method, PREFIX + r.path) for r in routes.PUBLIC})

    def test_header_names_in_server_md_are_the_ones_read(self):
        self.assertEqual(set(re.findall(r"X-Cake-[A-Za-z0-9-]+", self.server_md)), set(netfacts.lb_headers().values()))

    def test_data_files_in_server_md_are_the_ones_written(self):
        """Everything the data folder can hold is listed, and nothing else: the paths.*_file functions, the replay and
        backup folders of data/storage.json, and the folder `agentcake lists update` writes."""
        written = {os.path.basename(f()) for name, f in vars(paths).items()
                   if callable(f) and name.endswith(("_file", "_dir"))}
        storage = json.loads(read(STORAGE_FILE))
        written |= {storage["replay_dir"], storage["backup_dir"], os.path.basename(lists.user_root())}
        listed = {name.rstrip("/") for name in first_column_names(section(self.server_md, "The data folder"))}
        self.assertEqual(listed, written)

    def test_python_version_in_server_md_is_pyproject_requires_python(self):
        self.assertEqual(minimum_pythons(self.server_md), {required_python()})

    def test_the_least_python_is_read_however_it_is_written(self):
        """SERVER.md once said "`python3` 3.9 or newer" after the minimum had become 3.11, and the check above,
        which only knew "Python X.Y or newer", did not see it (found while building a release)."""
        for sentence, version in (("AgentCake needs Python 3.11 or newer", "3.11"),
                                  ("You need systemd, `python3` 3.9 or newer (Debian 12 has 3.11)", "3.9"),
                                  ("it runs with python3 3.12 or newer", "3.12"),
                                  ("any python 3.13 or newer will do", "3.13")):
            self.assertEqual(minimum_pythons(sentence), {version}, sentence)

    def test_docker_run_uses_the_host_network(self):
        """The local page binds 127.0.0.1, inside a container its own loopback: only with the host's network is that
        the server's 127.0.0.1, which a tunnel reaches."""
        runs = [line for line in code_block_lines(self.server_md) if line.startswith("docker run -d")]
        self.assertTrue(runs)
        for line in runs:
            self.assertIn("--network host", line)

    # ---------------------------------------------------------------------------------------- deploy/cake.service
    def test_unit_runs_serve_isolated_from_the_package_folder(self):
        words = shlex.split(self.unit["Service"]["ExecStart"])
        self.assertIn("-I", words)
        script = next(w for w in words if w.endswith(".py"))
        self.assertTrue(script.endswith("/agentcake/__main__.py"))
        self.assertTrue(os.path.isfile(paths.MAIN_FILE))
        self.assertEqual(words[-1], "serve")

    def test_unit_writes_only_its_data_folder_as_a_user_not_root(self):
        service = self.unit["Service"]
        self.assertEqual(service["ReadWritePaths"], self.unit_data_folder())
        self.assertEqual(service["ProtectSystem"], "strict")
        self.assertNotIn(service["User"], ("root", "0"))
        self.assertIn(f"`{self.unit_data_folder()}`", self.server_md)

    def test_unit_has_a_memory_limit_and_server_md_says_how_to_change_it(self):
        self.assertTrue(self.unit["Service"]["MemoryMax"])
        self.assertIn("systemctl set-property cake MemoryMax=", self.server_md)

    # ---------------------------------------------------------------------------------------- Dockerfile
    def test_image_is_python_3_14_slim(self):
        self.assertEqual(self.base_image, "python:3.14-slim")

    def test_image_runs_as_a_user_not_root(self):
        user = instruction_values(self.final_stage, "USER")[-1].split(":")[0]
        self.assertTrue(user.isdigit() and int(user) > 0, user)

    def test_image_runs_serve_the_same_way_on_the_unit_files_data_folder(self):
        entrypoint = json.loads(instruction_values(self.final_stage, "ENTRYPOINT")[-1])
        command = json.loads(instruction_values(self.final_stage, "CMD")[-1])
        self.assertEqual(entrypoint + command, ["python3", "-I", "-m", "agentcake", "serve"])
        home = self.unit_data_folder()
        self.assertIn(f"CAKE_HOME={home}", instruction_values(self.final_stage, "ENV"))
        self.assertEqual([json.loads(v) for v in instruction_values(self.final_stage, "VOLUME")], [[home]])

    def test_image_exposes_only_the_public_port(self):
        exposed = " ".join(instruction_values(self.final_stage, "EXPOSE")).split()
        self.assertEqual(exposed, [str(self.public_port_in_server_md())])
        self.assertNotIn(str(config.DEFAULTS["port"]), exposed)

    def test_image_health_check_runs_status(self):
        check = instruction_values(self.final_stage, "HEALTHCHECK")[-1]
        self.assertEqual(json.loads(check.partition("CMD")[2]), ["python3", "-I", "-m", "agentcake", "status"])

    def test_image_stops_serve_with_sigint(self):
        """As PID 1 in a container, Python has no handler for SIGTERM and the kernel does not apply the default action
        to PID 1, so `docker stop` would wait and kill; SIGINT has Python's handler and ends `serve`."""
        self.assertEqual(instruction_values(self.final_stage, "STOPSIGNAL"), ["SIGINT"])

    def test_build_context_is_only_the_wheel(self):
        lines = [line.strip() for line in read(DOCKERIGNORE).splitlines()]
        patterns = [line for line in lines if line and not line.startswith("#")]
        self.assertEqual(patterns[0], "*")
        self.assertEqual(patterns[1:], ["!dist/agentcake-*.whl"])
        sources = [rest.split()[0] for instruction, rest in dockerfile_instructions() if instruction == "COPY"
                   and not rest.startswith("--from")]
        self.assertEqual(sources, ["dist/"])


if __name__ == "__main__":
    unittest.main()
