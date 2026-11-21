"""The sites' middleware in the release: edge/ copied into the package, so every way of installing has it.

edge/ holds the server half for a website (Node, Python, PHP, WordPress). It is not published anywhere
else: `agentcake setup --print --site` points at the copy inside the installed package, in the folder the data file
named by release.json "edge" says (agentcake.site_setup.edge_dir() looks there first). Its tests and
development scripts stay in the repository (release.json "edge" -> "skip"), and so do node_modules and the other
names never shipped.

The WordPress plugin is installed as it is, so its header names its version, which WordPress shows under Plugins: the
version being released, written in the same commit as agentcake/__init__.py's. check_plugin_version() refuses a commit
whose plugin names another one (release.json "edge" -> "plugin"), the way readme.py refuses a README at another tag.
"""
import os
import re
import shutil

from tools.releasing.settings import ReleaseError, package_folder

HEADER_BYTES = 8192  # protocol: WordPress's get_file_data() reads a plugin's header fields from its first 8 KB


def header_field(text, field):
    """A plugin header field as WordPress's get_file_data() reads it (wp-includes/functions.php): the first line that
    has the field's name and a colon after the comment's opening marks, ignoring case, cut before a closing */ or ?>
    (_cleanup_header_comment). None when the file has no such line or it is empty."""
    head = text.replace("\r", "\n")
    match = re.search(r"^(?:[ \t]*<\?php)?[ \t/*#@]*" + re.escape(field) + r":(.*)$", head, re.M | re.I)
    value = re.sub(r"\s*(?:\*/|\?>).*", "", match.group(1)).strip() if match else ""
    return value or None


def plugin_version(tree, settings):
    """The version the WordPress plugin's header names, read from the first HEADER_BYTES of its main file."""
    rule = settings["edge"]
    rel = f"{rule['folder']}/{rule['plugin']['file']}"
    try:
        with open(os.path.join(tree, *rel.split("/")), "rb") as f:
            head = f.read(HEADER_BYTES).decode("utf-8", errors="ignore")
    except OSError as error:
        raise ReleaseError(f"cannot read the WordPress plugin, {rel}: {error}") from None
    return header_field(head, rule["plugin"]["version_field"])


def check_plugin_version(tree, settings, version):
    """Refuse a tree whose WordPress plugin names another version than the one being released."""
    rule = settings["edge"]
    field = rule["plugin"]["version_field"]
    named = plugin_version(tree, settings)
    if named != version:
        found = f"names version {named}" if named else f"has no {field} field"
        raise ReleaseError(f"{rule['folder']}/{rule['plugin']['file']} {found} in its header, and the release is "
                           f"{version} (agentcake/__init__.py): write {field}: {version} there with the version, "
                           "commit, then build again")


def build(tree, settings):
    """Copy the commit's edge/ into the package; returns the folder it was copied to."""
    rule = settings["edge"]
    source = os.path.join(tree, rule["folder"])
    target = package_folder(tree, settings, rule)
    if os.path.exists(target):
        raise ReleaseError(f"{os.path.relpath(target, tree)} is already in the commit: the middleware goes there")
    left_out = {os.path.normpath(os.path.join(source, path)) for path in rule["skip"]}
    missing = sorted(path for path in left_out if not os.path.exists(path))
    if missing:
        raise ReleaseError(f"release.json edge skip names what the commit does not have: {missing}")
    never = settings["package_files"]

    def ignore(folder, names):
        return [name for name in names
                if os.path.normpath(os.path.join(folder, name)) in left_out or name in never["skip_dirs"]
                or name in never["skip_names"] or name.endswith(tuple(never["skip_suffixes"]))]

    shutil.copytree(source, target, ignore=ignore)
    return target
