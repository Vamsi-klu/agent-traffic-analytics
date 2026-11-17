"""Scratch project trees for the release tests: a pyproject.toml, a made-up agentcake package and
whatever files a test adds, in a temporary folder. Nothing in them is real data.
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.releasing import settings as release_settings  # noqa: E402  (the repository is put on sys.path first)

VERSION = "1.2.3"
PYPROJECT = """[project]
name = "agentcake"
dynamic = ["version", "description"]
readme = "README.md"
requires-python = ">=3.11"
dependencies = []

[project.scripts]
agentcake = "agentcake.cli:main"

[tool.flit.sdist]
include = ["bin/", "SERVER.md"]
exclude = ["bin/left-out"]
"""
FILES = {
    "pyproject.toml": PYPROJECT,
    "README.md": "# A made-up AgentCake\n\nFor the release tests.\n",
    "SERVER.md": "# Server\n",
    "bin/agentcake": "#!/bin/sh\necho made-up\n",
    "bin/left-out": "left out by the exclude pattern\n",
    "agentcake/__init__.py": f'"""A made-up AgentCake for the release tests.\n\nNot the real one."""\n\n__version__ = "{VERSION}"\n',
    "agentcake/cli.py": "def main():\n    print('made-up cli')\n    return 0\n",
    "agentcake/data/product.json": '{"name": "AgentCake"}\n',
}


def settings():
    return release_settings.load()


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def edit_pyproject(tree, old, new):
    """Replace old with new in the tree's pyproject.toml (old must be there)."""
    path = os.path.join(tree, "pyproject.toml")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if old not in text:
        raise AssertionError(f"{old!r} is not in the test's pyproject.toml")
    write(tree, "pyproject.toml", text.replace(old, new))


def make_tree(test, files=None, executable=("bin/agentcake",)):
    """A scratch tree with FILES and files (rel path -> text; None leaves a FILES entry out), removed after the test."""
    root = tempfile.mkdtemp(prefix="agentcake-release-test-")
    test.addCleanup(shutil.rmtree, root, True)
    chosen = {**FILES, **(files or {})}
    for rel, text in chosen.items():
        if text is not None:
            write(root, rel, text)
    for rel in executable:
        if chosen.get(rel) is not None:
            os.chmod(os.path.join(root, rel), 0o755)  # protocol: rwxr-xr-x
    return root


def scratch(test, prefix="agentcake-release-out-"):
    folder = tempfile.mkdtemp(prefix=prefix)
    test.addCleanup(shutil.rmtree, folder, True)
    return folder
