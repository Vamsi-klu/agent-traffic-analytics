#!/usr/bin/env python3
"""Check that AgentCake's code imports nothing but the Python standard library and agentcake.

    python3 tools/check_imports.py [folder]      (default: agentcake/ next to tools/; e.g. tools to check the tools)

Reads every .py file under the folder with ast and lists each `import x` or `from x import y` whose top-level module
is none of: the standard library (sys.stdlib_module_names, and the newer standard library modules listed under
"check_imports" in tools/limits.json, which agentcake imports with a fallback, so the check passes on a Python older
than they are), agentcake (this project's package), the scanned folder itself (tools.eval_data inside tools/) or a
module that lives in the scanned folder; relative imports stay inside their package. Files listed under
"check_imports" "exempt" in tools/limits.json (paths from the scanned folder's parent, e.g. tools/…) are skipped,
each with its reason: a tool's half that runs only in a venv of its own. Prints one line per offending import and a
count; the exit code is 0 when it is 0.
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)  # run as a script under python3 -I, the repository root is not on sys.path

from tools.code_checks import folder_argument, limits  # noqa: E402

OWN_PACKAGE = "agentcake"
DEFAULT_FOLDER = os.path.join(ROOT, OWN_PACKAGE)


def imports(tree):
    """(line, module) for each absolute import in a parsed file."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            yield node.lineno, node.module


def python_files(folder):
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        yield from (os.path.join(root, f) for f in sorted(files) if f.endswith(".py"))


def stdlib_modules():
    """The standard library's top-level module names, with the newer ones tools/limits.json lists (compression,
    Python 3.14) that this Python may not have."""
    return set(sys.stdlib_module_names) | set(limits("check_imports")["newer_stdlib"])


def local_modules(folder):
    """The folder's own name and the top-level modules and packages inside it: this project's code, not a dependency."""
    names = {os.path.basename(os.path.normpath(folder))}
    for entry in os.listdir(folder):
        stem, suffix = os.path.splitext(entry)
        if suffix == ".py" or os.path.isfile(os.path.join(folder, entry, "__init__.py")):
            names.add(stem)
    return names


def offending_imports(folder):
    """(file relative to the folder's parent, line, module) for each import that is neither the standard library,
    agentcake nor the folder's own code."""
    allowed = stdlib_modules() | {OWN_PACKAGE} | local_modules(folder)
    exempt = set(limits("check_imports").get("exempt", {}))
    found = []
    for path in python_files(folder):
        rel = os.path.relpath(path, os.path.dirname(os.path.normpath(folder))).replace(os.sep, "/")
        if rel in exempt:
            continue
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
        for line, module in imports(tree):
            if module.split(".")[0] not in allowed:
                found.append((rel, line, module))
    return found


def main(argv):
    folder = folder_argument(argv, __doc__, DEFAULT_FOLDER, "the folder to check (default: agentcake/ next to tools/)")
    found = offending_imports(folder)
    for path, line, module in found:
        print(f"{path}:{line}: imports {module}, which is not in the standard library, {OWN_PACKAGE} or this folder")
    print(f"check_imports: {len(found)} import(s) outside the standard library in {os.path.basename(folder)}/")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
