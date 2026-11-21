"""SERVER.md, deploy/cake.service, Dockerfile, .dockerignore, docker-compose.yml and deploy/Caddyfile against the code.

    python3 -I -m unittest discover -s tests -v      (from the AgentCake folder)

Every `agentcake` command in SERVER.md's code blocks runs in a scratch CAKE_HOME (but those that never return or go
online), every setting it names exists, and the public paths, trusted headers, data folder files and Python version it
states are the code's. The unit file and the image run `agentcake serve` the same way, isolated (-I), on the same data
folder, as a user that is not root; the image is python:3.14-slim, exposes only the public port, checks its health with
`agentcake status` and is built from the wheel alone. On the subdomain route, docker-compose.yml runs that image and a
Caddy of a pinned version that reads deploy/Caddyfile, both on the host's network, with volumes whose names outlive a
release folder; the Caddyfile serves the subdomain SERVER.md names, forwards only the path rules' paths to the public
listener SERVER.md sets, and sets or removes every header AgentCake trusts. Neither Docker, Caddy nor systemd is
needed: the files are read the way they read them.
"""
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
import unittest
from urllib.parse import urlsplit

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from agentcake import config, geoip, netfacts, paths, routes, updates, wording  # noqa: E402  (needs the path above)
from agentcake.detect import lists  # noqa: E402
from cake_server import PREFIX, ROOT, SERVER_MD, documented_public_routes, free_port, read, run_cli  # noqa: E402
from deploy_files import (CADDYFILE, COMPOSE_FILE, DOCKERIGNORE, caddyfile, compose_file,  # noqa: E402
                          dockerfile_instructions, final_stage, instruction_values, mounts, unit_data_folder,
                          unit_file)

PYPROJECT = os.path.join(ROOT, "pyproject.toml")
STORAGE_FILE = os.path.join(paths.PACKAGE_DIR, "data", "storage.json")
# SERVER.md commands the scratch run leaves out: `serve` does not return (test_server_mode.py runs it), doctor checks
# the server's subdomain over the internet, and `lists update` downloads; a test never goes online.
NOT_RUN = (("serve",), ("doctor",), ("lists", "update"))
# Settings SERVER.md documents together with the code of the same release that adds them: the subdomain route's
# address and the proxies in front of a path of your own site. Until a checkout has them, the commands that set them
# are not run and test_settings_documented_ahead_of_the_code is skipped; once they exist, this changes nothing.
AHEAD_OF_CODE = frozenset({"public_url", "proxy_hops"})
SHELL_OPERATORS = ("|", "||", "&&", ";")
RUN_OPERATORS = re.compile(r"&&|\|\||;|\|")  # SHELL_OPERATORS as a RUN line writes them, longest first
# What a build may run besides pip: the commands that make the image's user and its data folder, none of which goes
# online. pip itself only with --no-index (the wheel in the build context).
OFFLINE_BUILD_COMMANDS = ("groupadd", "useradd", "install")
PACKAGE_NAME = "agentcake"
MINIMUM_PYTHON = re.compile(r"`?\b[Pp]ython3?`?\s+(\d+\.\d+) or (?:newer|later)")
MINIMUM_CADDY = re.compile(r"\bCaddy (\d+)\.(\d+) or newer")
CADDY_IMAGE = re.compile(r"^caddy:(\d+)\.(\d+)\.(\d+)(?:-[\w.]+)?$")  # an exact release, never caddy:2 or latest
COMPOSE_SERVICE = re.compile(r"docker compose (?:exec|restart|stop|start|up|logs|run)((?: -{1,2}[\w-]+)*) ([a-z][\w-]*)")
# The volume a `docker volume inspect` names, after any options and their quoted values (-f '{{ .Mountpoint }}').
VOLUME_INSPECT = re.compile(r"docker volume inspect(?: -{1,2}[\w-]+(?: '[^']*'| \"[^\"]*\")?)* ([\w.][\w.-]*)")
# SERVER.md's placeholders for what is the reader's own (the home page's "On a server" commands use the same), and the
# made-up value each is run with here.
PLACEHOLDERS = {"<your-domain>": "example.com"}
API_WORDS = os.path.join(ROOT, "agentcake", "data", "api.en.json")


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
    """The arguments of every AgentCake command in the code blocks: `agentcake …`, `python3 -I -m agentcake …` or
    `…/agentcake/__main__.py …`, up to a pipe, `&&`, `;`, a comment, or the quote that ends a command for ssh; each
    placeholder of PLACEHOLDERS in them filled with its made-up value."""
    commands = []
    for line in code_block_lines(markdown):
        if line.startswith("alias "):
            continue
        for placeholder, value in PLACEHOLDERS.items():
            line = line.replace(placeholder, value)
        match = re.search(r"(?:^agentcake|-m agentcake|agentcake/__main__\.py)\s+([^'\"]+)", line)
        if match:
            words = shlex.split(match.group(1), comments=True)
            operators = [i for i, word in enumerate(words) if word in SHELL_OPERATORS]
            commands.append(words[:operators[0]] if operators else words)
    return commands


def section(markdown, heading, level=2):
    """The text under one heading of that level (`## heading`), up to the next heading of that level or above."""
    match = re.search(rf"^{'#' * level} {re.escape(heading)}\n(.*?)(?=^#{{1,{level}}} |\Z)", markdown, re.M | re.S)
    if not match:
        raise AssertionError(f"SERVER.md has no section '{'#' * level} {heading}'")
    return match.group(1)


def first_column_names(text):
    """The `backticked` names in the first cell of each table row."""
    names = []
    for line in text.splitlines():
        cells = line.split("|")
        if line.startswith("|") and len(cells) > 2 and not set(cells[1].strip()) <= set("-: "):
            names += re.findall(r"`([^`]+)`", cells[1])
    return names


def pending_settings():
    """The settings of AHEAD_OF_CODE this checkout does not have yet."""
    return AHEAD_OF_CODE - config.SETTABLE


def build_commands():
    """Each command the Dockerfile's RUN instructions start, in every stage: a RUN split at its shell operators."""
    return [command.strip() for instruction, rest in dockerfile_instructions() if instruction == "RUN"
            for command in RUN_OPERATORS.split(rest) if command.strip()]


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

    # ---------------------------------------------------------------------------------------- SERVER.md
    def test_every_agentcake_command_in_server_md_runs(self):
        commands = agentcake_commands(self.server_md)
        self.assertTrue(commands)
        home = tempfile.mkdtemp(prefix="agentcake-server-md-")
        self.addCleanup(shutil.rmtree, home, True)
        env = dict(os.environ, CAKE_HOME=home, CAKE_PORT=str(free_port()))  # status finds nothing, never another cake
        for words in commands:
            if any(tuple(words[:len(left_out)]) == left_out for left_out in NOT_RUN):
                continue
            if words[:2] == ["config", "set"] and words[2] in pending_settings():
                continue
            done = run_cli(env, *words)
            allowed = (0, 1) if words[0] == "status" else (0,)  # status says 1 when nothing runs here
            self.assertIn(done.returncode, allowed, f"agentcake {' '.join(words)}: {done.stdout}{done.stderr}")

    def test_every_setting_server_md_names_exists(self):
        named = set(first_column_names(section(self.server_md, "Settings")))
        named |= {c[2] for c in agentcake_commands(self.server_md) if c[:2] == ["config", "set"]}
        self.assertTrue(named)
        self.assertEqual(named - config.SETTABLE - pending_settings(), set())

    def test_settings_documented_ahead_of_the_code(self):
        if pending_settings():
            self.skipTest(f"SERVER.md documents {', '.join(sorted(pending_settings()))}, which the code of the same "
                          "release adds; this checkout does not have them yet")
        self.assertLessEqual(AHEAD_OF_CODE, set(first_column_names(section(self.server_md, "Settings"))))

    def test_public_paths_in_server_md_are_the_public_routes(self):
        self.assertEqual(documented_public_routes(self.server_md), {(r.method, PREFIX + r.path) for r in routes.PUBLIC})

    def test_headers_server_md_trusts_are_ones_agentcake_reads(self):
        trusted = set(first_column_names(section(self.server_md, "Which headers AgentCake trusts", level=3)))
        self.assertIn(netfacts.lb_headers()["ip"], trusted)
        self.assertLessEqual(trusted, set(netfacts.lb_headers().values()))

    def test_every_header_agentcake_reads_is_in_server_md(self):
        self.assertLessEqual(set(netfacts.lb_headers().values()), set(re.findall(r"X-Cake-[A-Za-z0-9-]+", self.server_md)))

    def test_data_files_in_server_md_are_the_ones_written(self):
        """Everything the data folder can hold is listed, and nothing else: the paths.*_file functions, the replay and
        backup folders of data/storage.json, the folders an update writes (the lists, and on a server the city
        database), and the record and lock of the updates (updates.py)."""
        written = {os.path.basename(f()) for name, f in vars(paths).items()
                   if callable(f) and name.endswith(("_file", "_dir"))}
        storage = json.loads(read(STORAGE_FILE))
        written |= {storage["replay_dir"], storage["backup_dir"], os.path.basename(lists.user_root()),
                    os.path.basename(geoip.user_folder()), updates.settings()["state_file"],
                    updates.settings()["lock_file"]}
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
        the server's 127.0.0.1, which a tunnel reaches. SERVER.md runs the image with Compose (checked below); any
        `docker run` it still shows has to say the same."""
        for line in code_block_lines(self.server_md):
            if line.startswith("docker run"):
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
        self.assertEqual(service["ReadWritePaths"], unit_data_folder())
        self.assertEqual(service["ProtectSystem"], "strict")
        self.assertNotIn(service["User"], ("root", "0"))
        self.assertIn(f"`{unit_data_folder()}`", self.server_md)

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
        home = unit_data_folder()
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

    def test_the_build_runs_no_agentcake_code(self):
        """Building the image installs the wheel and makes its user, nothing more: AgentCake downloads the city
        database itself, into the data volume, at its first check after it starts (updates.py). On a 1 GB server the
        build's own download took 7 of its 9 minutes."""
        for command in build_commands():
            words = shlex.split(command)
            self.assertNotIn(PACKAGE_NAME, words[:1], command)
            self.assertFalse(words[:1] == ["python3"] and any(word.startswith(PACKAGE_NAME) for word in words), command)

    def test_the_build_downloads_nothing_but_the_base_image(self):
        """Besides pulling the base image, a build goes nowhere: pip installs the wheel from the build context with
        --no-index, and the other commands make the image's user and its data folder. No ADD, which can fetch a URL."""
        instructions = dockerfile_instructions()
        self.assertNotIn("ADD", [instruction for instruction, _ in instructions])
        self.assertEqual({rest.split()[0] for instruction, rest in instructions if instruction == "FROM"},
                         {"${PYTHON_IMAGE}"})
        for command in build_commands():
            words = shlex.split(command)
            if words[0] == "python3":
                self.assertEqual(words[1:4], ["-m", "pip", "install"], command)
                self.assertIn("--no-index", words, command)
            else:
                self.assertIn(words[0], OFFLINE_BUILD_COMMANDS, command)


class SubdomainRouteMatchesServerMd(unittest.TestCase):
    """docker-compose.yml and deploy/Caddyfile, the subdomain route's two files, do what SERVER.md says they do."""

    @classmethod
    def setUpClass(cls):
        missing = [os.path.relpath(path, ROOT) for path in (COMPOSE_FILE, CADDYFILE) if not os.path.isfile(path)]
        if missing:
            raise unittest.SkipTest(f"{' and '.join(missing)} not in this checkout: they come with the subdomain "
                                    "route's code; SERVER.md already describes them")
        cls.server_md, cls.caddy, compose = read(SERVER_MD), caddyfile(), compose_file()
        cls.services, cls.volumes = compose["services"], compose.get("volumes") or {}

    def test_compose_runs_agentcake_and_caddy_on_the_host_network(self):
        """The local page's 127.0.0.1 has to be the server's, for the tunnel; Caddy reaches 127.0.0.1:8080."""
        self.assertLessEqual({"agentcake", "caddy"}, set(self.services))
        for name in ("agentcake", "caddy"):
            self.assertEqual(self.services[name].get("network_mode"), "host", name)

    def test_agentcake_is_this_folders_image_on_the_unit_files_data_folder(self):
        build = self.services["agentcake"]["build"]
        self.assertEqual(build if isinstance(build, str) else build.get("context"), ".")
        volume = mounts(self.services["agentcake"])[unit_data_folder()]
        inspected = VOLUME_INSPECT.findall(self.server_md)
        self.assertTrue(inspected)
        self.assertEqual({(self.volumes[volume] or {}).get("name")}, set(inspected))

    def test_a_volume_is_read_after_the_options_of_docker_volume_inspect(self):
        for command, volume in (("docker volume inspect agentcake-data", "agentcake-data"),
                                ("docker volume inspect -f '{{ .Mountpoint }}' agentcake-data", "agentcake-data"),
                                ('docker volume inspect --format "{{ .Mountpoint }}" my.data', "my.data")):
            self.assertEqual(VOLUME_INSPECT.findall(command), [volume], command)

    def test_volumes_keep_their_names_in_a_new_release_folder(self):
        """Compose names volumes after the folder by default, and each release unpacks into a folder of its own: only
        a volume with a name of its own keeps the data and Caddy's certificates across an upgrade."""
        self.assertTrue(self.volumes)
        for volume, settings in self.volumes.items():
            self.assertTrue((settings or {}).get("name"), f"volume {volume} has no name of its own")

    def test_caddy_is_a_pinned_version_that_reads_the_caddyfile(self):
        """SERVER.md names the least Caddy the Caddyfile needs (trusted_proxies_strict came with 2.8)."""
        image = CADDY_IMAGE.match(self.services["caddy"]["image"])
        self.assertTrue(image, self.services["caddy"]["image"])
        least = {tuple(map(int, found)) for found in MINIMUM_CADDY.findall(self.server_md)}
        self.assertEqual(len(least), 1, least)
        self.assertGreaterEqual(tuple(map(int, image.groups()[:2])), least.pop())

    def test_caddy_reads_this_caddyfile_and_keeps_its_certificates(self):
        mounts_of_caddy = mounts(self.services["caddy"])
        source = os.path.normpath(os.path.join(os.path.dirname(COMPOSE_FILE), mounts_of_caddy["/etc/caddy/Caddyfile"]))
        self.assertEqual(source, CADDYFILE)
        self.assertIn(f"`{os.path.relpath(CADDYFILE, ROOT)}`", self.server_md)
        self.assertIn(mounts_of_caddy["/data"], self.volumes)

    def test_server_md_names_only_services_of_the_compose_file(self):
        named = {service for _, service in COMPOSE_SERVICE.findall(self.server_md)}
        self.assertTrue(named)
        self.assertLessEqual(named, set(self.services))

    def test_caddyfile_serves_the_subdomain_server_md_sets(self):
        """Step 5's public_url; the name for a site without its own domain is test_server_nodomain.py's."""
        steps = section(self.server_md, "Install with Docker Compose")
        public_urls = [c[3] for c in agentcake_commands(steps) if c[:3] == ["config", "set", "public_url"]]
        self.assertTrue(public_urls)
        self.assertEqual({urlsplit(url).hostname for url in public_urls}, {self.caddy["site"]})
        self.assertIn(f"s/{re.escape(self.caddy['site'])}/", self.server_md)  # step 3's sed writes yours there

    def test_the_home_pages_server_commands_are_server_mds_word_for_word(self):
        """The local page's "On a server" tab shows the commands of steps 3 to 5 (api.en.json setup_server)."""
        with open(API_WORDS, encoding="utf-8") as f:
            blocks = json.load(f)["setup_server"]
        commands = [line.format(**wording.product()) for part in ("install", "settings") for line in blocks[part]]
        self.assertTrue(commands)
        for command in commands:
            self.assertIn(command, self.server_md)

    def test_caddy_forwards_the_path_rules_to_the_public_listener(self):
        rules = [line for line in code_block_lines(section(self.server_md, "Path rules", level=3))
                 if line.startswith(PREFIX + "/")]
        self.assertEqual(sorted(self.caddy["forwarded"]), sorted(rules))
        public = {PREFIX + route.path for route in routes.PUBLIC}
        self.assertLessEqual(set(self.caddy["forwarded"]), public)
        listens = [c[3] for c in agentcake_commands(self.server_md) if c[:3] == ["config", "set", "public_listen"]]
        self.assertEqual(self.caddy["upstream"], listens[0])
        self.assertTrue(self.caddy["answers_404"], "SERVER.md: Caddy answers 404 to everything else")

    def test_caddy_sets_or_removes_every_header_agentcake_trusts(self):
        """A header the front door neither sets nor removes passes through from the visitor (Which headers AgentCake
        trusts); the visitor's address is the one Caddy took the connection from, or Cloudflare's header for it. No
        other header: one AgentCake does not read needs no line."""
        self.assertEqual(set(self.caddy["headers"]), set(netfacts.lb_headers().values()))
        self.assertEqual(self.caddy["headers"][netfacts.lb_headers()["ip"]], "{client_ip}")

    def test_caddy_reads_the_visitors_address_behind_cloudflare(self):
        """Two special cases: with Cloudflare's proxy on, the Caddyfile trusts its ranges and reads CF-Connecting-IP."""
        self.assertIn("CF-Connecting-IP", self.server_md)
        self.assertRegex(self.caddy["global"], r"trusted_proxies\s")
        self.assertRegex(self.caddy["global"], r"client_ip_headers[^\n]*\bCF-Connecting-IP\b")


if __name__ == "__main__":
    unittest.main()
