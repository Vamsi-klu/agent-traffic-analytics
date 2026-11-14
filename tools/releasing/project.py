"""What is released: the version, the core metadata from pyproject.toml, and which files are the package.

The version is written only in agentcake/__init__.py (__version__) and read here with ast, without importing the
package. Everything else that describes the package (name, Python, command, readme, license) is pyproject.toml's,
the table flit_core reads when a wheel is built from a checkout (`pip wheel .`), so a release and a source build
describe the package alike; the summary is the first line of the package's docstring (dynamic "description"), as
flit_core takes it. A key of [project] that this module does not write into the metadata stops the release instead
of being left out silently.

Core metadata: https://packaging.python.org/specifications/core-metadata/ (2.2; 2.4 when there is license
information, PEP 639). File names: the wheel and source distribution formats (PEP 427, PEP 625).
"""
import ast
import glob
import os
import re
import tomllib

from tools.releasing.settings import ReleaseError

METADATA_VERSION = "2.2"  # protocol: core metadata 2.2, the oldest a source distribution's PKG-INFO may have
LICENSE_METADATA_VERSION = "2.4"  # protocol: License-Expression and License-File need core metadata 2.4 (PEP 639)
WHEEL_TAG = "py3-none-any"  # protocol: pure Python 3, any ABI, any platform
README_TYPES = {".md": "text/markdown", ".rst": "text/x-rst", ".txt": "text/plain"}  # protocol: core metadata
HANDLED_KEYS = {"name", "version", "description", "dynamic", "readme", "requires-python", "dependencies", "scripts",
                "license", "license-files"}
FROM_PACKAGE = {"version", "description"}  # the dynamic fields this module reads from the package


class Project:
    """pyproject.toml and the package of one tree (the repository, or an exported commit)."""

    def __init__(self, root, settings):
        with open(os.path.join(root, "pyproject.toml"), "rb") as f:
            self.pyproject = tomllib.load(f)
        self.table = self.pyproject["project"]
        unknown = sorted(set(self.table) - HANDLED_KEYS)
        if unknown:
            raise ReleaseError(f"pyproject.toml [project] has {', '.join(unknown)}, which tools/releasing/project.py "
                               "does not put into the metadata yet: add it there first")
        if self.table.get("dependencies"):
            raise ReleaseError("pyproject.toml lists dependencies: Agent Cake ships as a wheel without any")
        unread = sorted(set(self.table.get("dynamic", [])) - FROM_PACKAGE)
        if unread or "version" in self.table:
            raise ReleaseError("pyproject.toml must leave the version to agentcake/__init__.py (dynamic) and have no "
                               f"other dynamic field; found {unread or 'a version'}")
        self.root, self.settings = root, settings
        self.name = self.table["name"]
        self.package = settings["package"]
        self.version, docstring = read_version_and_docstring(os.path.join(root, settings["version_file"]))
        self.summary = self.table.get("description") or docstring.strip().splitlines()[0]

    # ---------------------------------------------------------------- names (PEP 427, PEP 625)
    def escaped_name(self):
        """The name as it is spelled in file names: lower case, runs of - _ . written as one _."""
        return re.sub(r"[-_.]+", "_", self.name).lower()

    def wheel_name(self):
        return f"{self.escaped_name()}-{self.version}-{WHEEL_TAG}.whl"

    def dist_info(self):
        return f"{self.escaped_name()}-{self.version}.dist-info"

    def sdist_base(self):
        """The source distribution's name without .tar.gz, which is also its top folder."""
        return f"{self.escaped_name()}-{self.version}"

    # ---------------------------------------------------------------- files
    def readme(self):
        return self.table.get("readme")

    def sdist_rules(self):
        """pyproject.toml's [tool.flit.sdist]: the include and exclude patterns of the source distribution."""
        return self.pyproject.get("tool", {}).get("flit", {}).get("sdist", {})

    def license_files(self):
        """The license files at the project's root (PEP 639): pyproject.toml's license-files patterns, each of which
        must match, or release.json's default patterns, which may match nothing (no LICENSE yet)."""
        patterns = self.table.get("license-files")
        found = set()
        for pattern in patterns or self.settings["license_globs"]:
            matched = [p for p in glob.glob(pattern, root_dir=self.root) if os.path.isfile(os.path.join(self.root, p))]
            if patterns is not None and not matched:
                raise ReleaseError(f"pyproject.toml license-files: {pattern!r} matches no file")
            found.update(p.replace(os.sep, "/") for p in matched)
        return sorted(found)

    def package_files(self):
        """(path in the release, path on disk, executable) of every file of the package, in sorted order, without
        what release.json "package_files" says is never shipped."""
        skip = self.settings["package_files"]
        top = os.path.join(self.root, self.package)
        files = []
        for folder, dirs, names in os.walk(top):
            dirs[:] = [d for d in dirs if d not in skip["skip_dirs"]]
            for name in names:
                if name in skip["skip_names"] or name.endswith(tuple(skip["skip_suffixes"])):
                    continue
                path = os.path.join(folder, name)
                rel = os.path.relpath(path, self.root).replace(os.sep, "/")
                files.append((rel, path, is_executable(path)))
        return sorted(files)

    # ---------------------------------------------------------------- metadata
    def metadata(self):
        """The core metadata, as a wheel's METADATA and a source distribution's PKG-INFO carry it."""
        license_expression = self.table.get("license")
        if license_expression is not None and not isinstance(license_expression, str):
            raise ReleaseError("pyproject.toml license: write it as an SPDX expression, e.g. license = \"MIT\" (PEP 639)")
        license_files = self.license_files()
        with_license = license_expression is not None or bool(license_files)
        fields = [("Metadata-Version", LICENSE_METADATA_VERSION if with_license else METADATA_VERSION),
                  ("Name", self.name), ("Version", self.version), ("Summary", self.summary)]
        if "requires-python" in self.table:
            fields.append(("Requires-Python", self.table["requires-python"]))
        if license_expression is not None:
            fields.append(("License-Expression", license_expression))
        fields += [("License-File", name) for name in license_files]
        body = ""
        readme = self.readme()
        if readme:
            if not isinstance(readme, str):
                raise ReleaseError("pyproject.toml readme: give the file's name (readme = \"README.md\")")
            content_type = README_TYPES.get(os.path.splitext(readme)[1].lower())
            if content_type is None:
                raise ReleaseError(f"pyproject.toml readme: {readme} is not .md, .rst or .txt")
            fields.append(("Description-Content-Type", content_type))
            with open(os.path.join(self.root, readme), encoding="utf-8") as f:
                body = f.read()
        head = "".join(f"{key}: {value}\n" for key, value in fields)
        return head + "\n" + body if body else head

    def entry_points(self):
        """entry_points.txt: the commands pyproject.toml's [project.scripts] names."""
        scripts = self.table.get("scripts", {})
        lines = ["[console_scripts]"] + [f"{name} = {target}" for name, target in sorted(scripts.items())]
        return "\n".join(lines) + "\n"


def read_version_and_docstring(path):
    """__version__ and the docstring of a module, read without running it."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), path)
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "__version__" and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            return node.value.value, ast.get_docstring(tree) or ""
    raise ReleaseError(f"{path} has no __version__ = \"<version>\"")


def is_executable(path):
    return bool(os.stat(path).st_mode & 0o111)  # protocol: the three execute bits of a POSIX file mode
