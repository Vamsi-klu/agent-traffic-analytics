"""Run the command line: ``python3 -m agentcake <command>`` or ``python3 -I <folder>/agentcake/__main__.py <command>``.

The first form needs agentcake importable (an installed wheel). bin/agentcake uses the second form for a release
folder or a checkout: isolated mode (-I) puts neither the current folder nor this file's folder on sys.path, so the
folder that holds the package is added here, the way pip's own __main__.py does it. cake.py, the 0.3.x
entry point, runs this file too.

Before anything else is imported, a Python older than the one data/product.json names ("python") is told so in one
sentence (data/copy.en.json, "python_too_old") instead of failing somewhere later with a traceback. An older Python
reads this file, so it keeps to syntax every Python 3 parses and uses only json, os, sys and zipfile (agentcake.pyz
runs --version and help with the package still inside the zip). pyproject.toml's requires-python names the same
version (tests/test_cli.py checks that they agree).
"""
import json
import os
import sys
import zipfile

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))


def python_too_old():
    """The sentence for a Python older than AgentCake needs, or None when this one will do."""
    def data(name):
        archive = os.path.dirname(PACKAGE_DIR)
        if os.path.isfile(archive):  # imported from agentcake.pyz itself
            with zipfile.ZipFile(archive) as zipped:
                member = "/".join((os.path.basename(PACKAGE_DIR), "data", name))
                return json.loads(zipped.read(member).decode("utf-8"))
        with open(os.path.join(PACKAGE_DIR, "data", name), encoding="utf-8") as f:
            return json.load(f)

    product = data("product.json")
    needed = tuple(int(part) for part in product["python"].split("."))
    if tuple(sys.version_info[:len(needed)]) >= needed:
        return None
    running = "{0}.{1}.{2}".format(*sys.version_info)  # major.minor.micro
    return data("copy.en.json")["python_too_old"].format(version=running, executable=sys.executable, **product)


if __name__ == "__main__":
    upgrade = python_too_old()
    if upgrade:
        sys.exit(upgrade)  # printed to stderr, exit status 1

if not __package__:  # run as a file: let `import agentcake` find the package this file belongs to
    sys.path.insert(0, os.path.dirname(PACKAGE_DIR))

from agentcake.cli import main  # noqa: E402  (needs the check and the path above)

if __name__ == "__main__":
    sys.exit(main())
