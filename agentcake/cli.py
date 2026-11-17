"""The command line: main(argv) runs one command and returns its exit code.

Used by bin/agentcake (and the 0.3.x entry points bin/cake and cake.py), by `python3 -m agentcake`, and by the
`agentcake` command an installed wheel provides (pyproject.toml). Everything it prints is in data/copy.en.json;
`config get` lists every setting with its value and where it comes from.

Every command is a Python process of its own, so each imports its module when it runs: importing them
all up front made every command, --version too, load the server, the judging and the storage first.
"""
import importlib.util
import json
import os
import sys

from agentcake import __version__, paths
from agentcake.config import DEFAULTS, JSON_INDENT, SETTABLE, coerce, ensure_cfg, load_cfg, save_user, sources
from agentcake.units import PERCENT
from agentcake.wording import raw, text

EXIT_USAGE = 2  # protocol: exit status of a command-line usage error (POSIX utilities, argparse)
HELP_FLAGS = ("-h", "--help")
# The options of the commands whose words main() reads itself, as the help lists them: any other word, or an option
# without its value, stops the command before it starts, stops, migrates or pings anything. WITH_VALUE options take the
# word after them.
OPTIONS = {"serve": (), "_serve": (), "start": (), "stop": (), "status": (), "snippet": (), "sentence": (), "ping": (),
           "migrate": ("--dry-run",), "setup": ("--print", "--site", "--dir"), "doctor": ("--dir", "--url")}
WITH_VALUE = ("--dir", "--url")
# The commands that read their own words, each with its usage line in data/copy.en.json (eval has its own parser).
USAGES = {"secret": "secret_usage", "config": "config_usage", "lists": "lists_usage", "logs": "logs_usage",
          "delete": "delete_usage"}


def help_text():
    from agentcake.netfacts import lb_headers

    return text("help", version=__version__, port=DEFAULTS["port"], budget_mb=DEFAULTS["budget_mb"],
                disk_min_free_mb=DEFAULTS["disk_min_free_mb"],
                warn_pct=round(DEFAULTS["budget_warn_ratio"] * PERCENT),
                free_left_pct=round((1 - DEFAULTS["auto_free_target_ratio"]) * PERCENT),
                lb_headers=", ".join(lb_headers().values()))


def secret_command(args):
    from agentcake.edge_secret import create_secret, srv_secret

    sub = (args or [""])[0]
    if sub == "init":
        if srv_secret():
            print(text("secret_exists", path=paths.tilde(paths.secret_file()))); return 0
        create_secret()
        print(text("secret_created", path=paths.tilde(paths.secret_file()))); return 0
    if sub == "print":
        v = srv_secret()
        if not v:
            print(text("secret_missing"), file=sys.stderr); return 1
        sys.stdout.write(v.decode()); return 0
    print(text("secret_usage")); return EXIT_USAGE


def print_settings():
    """Every setting, its value and its source, one per line in aligned columns."""
    c, where, labels = load_cfg(), sources(), raw("config_source")
    values = {key: json.dumps(c.get(key)) for key in where}
    key_width, value_width = max(map(len, values)), max(map(len, values.values()))
    for key, value in values.items():
        print(f"{key.ljust(key_width)}  {value.ljust(value_width)}  {labels[where[key]]}")


def config_command(args):
    ensure_cfg()
    action, *rest = args or [""]
    if action == "get":
        if rest:
            print(json.dumps(load_cfg().get(rest[0])))
        else:
            print_settings()
        return 0
    if action == "set" and rest[1:]:  # a key and at least one word of value
        key, *words = rest
        if key not in SETTABLE:
            print(text("config_unknown_key", keys=", ".join(sorted(SETTABLE)))); return EXIT_USAGE
        try:
            value = coerce(key, " ".join(words))
        except ValueError as e:
            print(e); return EXIT_USAGE
        save_user(**{key: value}); print(text("config_set", key=key, value=json.dumps(value))); return 0
    print(text("config_usage")); return EXIT_USAGE


def lists_command(args):
    """`lists`: the age and sources of the name and range lists in use. `lists update`: the only command that
    fetches them, into $CAKE_HOME/lists/<date>/; when anything fails it says what and the lists stay as they were."""
    from agentcake.detect import lists

    sub = (args or [""])[0]
    if sub == "update":
        # Only this command loads the code that fetches; a running cake never imports it.
        from agentcake.detect import lists_build

        try:
            folder = lists_build.update()
        except lists_build.BuildError as error:
            print(text("lists_not_updated", error=error), file=sys.stderr); return 1
        print(json.dumps({"updated": paths.tilde(folder), **lists.current().status()}, indent=JSON_INDENT)); return 0
    if not sub:
        print(json.dumps(lists.current().status(), indent=JSON_INDENT)); return 0
    print(text("lists_usage")); return EXIT_USAGE


def stray_option(words, allowed):
    """The first word that is not an option in allowed, as (word, False), or a WITH_VALUE option with nothing after
    it, as (option, True); None when words hold only allowed options, each WITH_VALUE one with its value."""
    rest = list(words)
    while rest:
        word = rest.pop(0)
        if word not in allowed:
            return word, False
        if word in WITH_VALUE:
            if not rest:
                return word, True
            rest.pop(0)
    return None


def option_value(words, flag):
    """The word after flag (`--dir DIR`, `--url URL`), or None when flag is not there or nothing follows it."""
    at = words.index(flag) + 1 if flag in words else len(words)
    return words[at] if at < len(words) else None


def main(argv=None):
    a = sys.argv[1:] if argv is None else list(argv)
    if not a or a[0] in ("-h", "--help", "help"):
        print(help_text()); return 0
    cmd, args = a[0], a[1:]
    if cmd == "--version":
        print(text("version", version=__version__)); return 0
    if (cmd in OPTIONS or cmd in USAGES) and any(word in HELP_FLAGS for word in args):
        print(text(USAGES[cmd]) if cmd in USAGES else help_text()); return 0
    stray = stray_option(args, OPTIONS[cmd]) if cmd in OPTIONS else None
    if stray:
        word, needs_value = stray
        print(text("option_needs_value" if needs_value else "option_unknown", subcommand=cmd, word=word))
        return EXIT_USAGE
    if cmd in ("_serve", "serve"):
        from agentcake.server import serve
        serve(); return 0
    if cmd == "secret":
        return secret_command(args)
    if cmd in ("start", "stop", "status"):
        from agentcake import daemon
        if cmd == "start": return daemon.start()
        if cmd == "stop": return daemon.stop()
        h = daemon.running()
        print(json.dumps(h, indent=JSON_INDENT) if h else text("not_running")); return 0 if h else 1
    if cmd in ("snippet", "sentence"):
        from agentcake import site_setup
        print(site_setup.snippet() if cmd == "snippet" else site_setup.sentence_b()); return 0
    if cmd == "ping":
        from agentcake.ping import ping
        return ping()
    if cmd == "migrate":
        from agentcake.migrate import migrate
        return migrate(dry_run="--dry-run" in a)
    if cmd == "delete":
        from agentcake import delete_command
        try:
            ids, dry_run = delete_command.parse(args)
        except ValueError as e:
            print(e); return EXIT_USAGE
        return delete_command.run(ids, dry_run)
    folder = option_value(a, "--dir")
    d = os.path.abspath(folder) if folder else None
    if cmd == "doctor":
        from agentcake.doctor import doctor
        return doctor(d, option_value(a, "--url"))
    if cmd == "setup":
        from agentcake import site_setup
        if "--site" in a:
            site_setup.setup_print_site(d or os.getcwd())
        else:
            site_setup.setup_print_local()
        return 0
    if cmd == "config":
        return config_command(args)
    if cmd == "lists":
        return lists_command(args)
    if cmd == "eval":  # the evaluation code is the biggest of all, and only a checkout has it (a release leaves it out)
        if importlib.util.find_spec("agentcake.eval") is None:
            print(text("eval_from_checkout"), file=sys.stderr); return EXIT_USAGE
        from agentcake import eval as eval_command
        return eval_command.main(args)
    if cmd == "logs":
        from agentcake.logs import logs_command
        return logs_command(args)
    print(text("unknown_command")); return EXIT_USAGE
