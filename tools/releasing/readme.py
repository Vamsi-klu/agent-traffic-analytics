"""README's pictures in a release: named at the release's tag, where the repository names them on its main branch.

Between releases README.md and its Chinese translation (release.json "readme" "files") show the repository's pictures
from main, so the repository's page on GitHub shows the pictures main has. The files a release ships keep that
release's own pictures instead: PyPI shows the wheel's README (the metadata's description) as the package's page for
good, and the release folder carries both READMEs. pin_tree() rewrites the exported commit's READMEs before the wheel
and the release folder are written: every address of a file of the repository on main, its raw address
(raw.githubusercontent.com/<owner>/<name>/main/...) or its page (github.com/<owner>/<name>/blob/main/...), becomes the
same address at the release's tag. What README already names at the tag (the files it links to, which
tests/test_install_docs.py keeps at the version's tag) stays as it is. An address at any other tag stops the build: a
README the release has not caught up with.
"""
import os
import re

from tools.releasing.settings import ReleaseError

GITHUB_REPOSITORY = re.compile(r"https://github\.com/([\w.-]+/[\w.-]+?)/?")  # protocol: a repository's page on GitHub
# protocol: GitHub's addresses of a file of a repository at a ref (a branch or a tag): its page and its raw file
FILE_ADDRESS = r"(https://(?:github\.com/{0}/blob|raw\.githubusercontent\.com/{0})/)([^/\s]+)/([^\s\"'<>`)]*)"


def repository(project, settings):
    """owner/name of the repository: the address pyproject.toml's [project.urls] gives under release.json "readme"
    "source_label"."""
    label = settings["readme"]["source_label"]
    address = dict(project.project_urls()).get(label, "")
    match = GITHUB_REPOSITORY.fullmatch(address)
    if not match:
        raise ReleaseError(f"pyproject.toml [project.urls] {label} must be the repository's page on GitHub "
                           f"(https://github.com/<owner>/<name>), for README's pictures; it is {address!r}")
    return match.group(1)


def file_addresses(owner_and_name):
    """The addresses of the repository's files: groups (the address up to the ref, the ref, the file's path)."""
    return re.compile(FILE_ADDRESS.format(re.escape(owner_and_name)))


def pin(text, owner_and_name, branch, tag):
    """text with every address of a file of the repository on branch named at tag instead. An address at any other
    ref stops the release, naming each such address."""
    stale = []

    def at_tag(match):
        start, ref, path = match.groups()
        if ref == branch:
            return f"{start}{tag}/{path}"
        if ref != tag:
            stale.append(match.group(0))
        return match.group(0)

    pinned = file_addresses(owner_and_name).sub(at_tag, text)
    if stale:
        raise ReleaseError(f"README names the repository's files at a ref other than {branch} and {tag}, the release's "
                           "tag: " + ", ".join(stale) + ". Name pictures on the branch and links at the tag.")
    return pinned


def pin_tree(tree, settings, project):
    """The READMEs of an exported commit (release.json "readme" "files") rewritten in place by pin(), for the tag of
    the version being released; returns {README: how many of its addresses changed}."""
    rule = settings["readme"]
    owner_and_name = repository(project, settings)
    tag = settings["tag_prefix"] + project.version
    on_branch = file_addresses(owner_and_name)
    changed = {}
    for rel in rule["files"]:
        path = os.path.join(tree, *rel.split("/"))
        if not os.path.isfile(path):
            raise ReleaseError(f"tools/releasing/release.json \"readme\" names {rel}, which is not in the commit")
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
        pinned = pin(text, owner_and_name, rule["branch"], tag)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(pinned)
        changed[rel] = sum(1 for match in on_branch.finditer(text) if match.group(2) == rule["branch"])
    return changed
