#!/usr/bin/env python3
"""Find values written into AgentCake's code instead of its settings, data files or design tokens.

    python3 tools/check_hardcode.py [repository folder]      (default: the folder above tools/)

Reads agentcake/**/*.py with ast, and agentcake/static/src/*.js with a small tokenizer. Finds:
  - numbers other than 0, 1 and -1 (True and False are not numbers here);
  - colours in strings: #rgb, #rgba, #rrggbb, #rrggbbaa, rgb(), rgba(), hsl(), hsla();
  - addresses in strings: an IPv4 address, localhost, a URL with its host, or host:port.
Docstrings and comments are not read. A line ending in `# protocol: <why>` (JavaScript: `// protocol: <why>`) may
hold values fixed by a protocol or a definition (a unit, a file format, the loopback address). Files listed under
"check_hardcode" in tools/limits.json are skipped, each with its reason. Prints one line per finding and a count; the
exit code is 0 when the count is 0.
"""
import ast
import io
import os
import re
import sys
import tokenize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)  # run as a script under python3 -I, the repository root is not on sys.path

from tools.code_checks import folder_argument, limits  # noqa: E402
ALLOWED_NUMBERS = (0, 1)  # -1 is the number 1 with a minus sign in front
PROTOCOL = re.compile(r"(#|//)\s*protocol:\s*\S")
COLOUR = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b|\b(?:rgba?|hsla?)\(")
ADDRESS = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])"            # IPv4
                     r"|\blocalhost\b"
                     r"|\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/{}\"'<>]+"           # scheme://host
                     r"|(?:\[[0-9a-fA-F:]+\]|\b[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+):\d{2,5}\b")  # host:port
JS_NUMBER = re.compile(r"(?<![\w$.])(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|(?:\d[\d_]*(?:\.[\d_]*)?|\.\d[\d_]*)"
                       r"(?:[eE][+-]?\d+)?)n?(?![\w$])")


def exempt_paths():
    return limits("check_hardcode")["exempt"]


def string_findings(value):
    """What in a string looks like a colour or an address."""
    return [f"colour {m.group(0)!r}" for m in COLOUR.finditer(value)] + \
           [f"address {m.group(0)!r}" for m in ADDRESS.finditer(value)]


# ---------------------------------------------------------------- Python
def docstring_nodes(tree):
    nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                nodes.add(first.value)
    return nodes


def protocol_lines(source):
    return {tok.start[0] for tok in tokenize.generate_tokens(io.StringIO(source).readline)
            if tok.type == tokenize.COMMENT and PROTOCOL.search(tok.string)}


def python_findings(source):
    """(line, what) for each value written into Python code."""
    tree, skip = ast.parse(source), protocol_lines(source)
    docstrings, found = docstring_nodes(tree), []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or node.lineno in skip or node in docstrings:
            continue
        value = node.value
        if isinstance(value, (int, float, complex)) and not isinstance(value, bool) and value not in ALLOWED_NUMBERS:
            found.append((node.lineno, f"number {value!r}"))
        elif isinstance(value, str):
            found += [(node.lineno, what) for what in string_findings(value)]
    return sorted(found)


# ---------------------------------------------------------------- JavaScript
def js_split(source):
    """Per line: (the code with strings and comments blanked out, the text of its strings, the text of its comments).
    Expressions inside template literals count as string text; regular expression literals count as code."""
    code, strings, comments = [], [], []
    i, quote, comment = 0, None, None  # comment: None, "line" or "block"

    def put(c, s, m):
        code.append(c); strings.append(s); comments.append(m)

    while i < len(source):
        ch, two = source[i], source[i:i + 2]
        if ch == "\n":
            put(ch, ch, ch)
            comment = None if comment == "line" else comment
        elif comment == "block" and two == "*/":
            put("  ", "  ", two); comment = None; i += 1
        elif comment:
            put(" ", " ", ch)
        elif quote and ch == "\\":
            nxt = source[i + 1:i + 2]
            put(" " + ("\n" if nxt == "\n" else " "), "\\" + nxt, " " + ("\n" if nxt == "\n" else " ")); i += 1
        elif quote:
            quote = None if ch == quote else quote
            put(" ", ch if quote else " ", " ")
        elif two in ("//", "/*"):
            comment = "line" if two == "//" else "block"
            put("  ", "  ", two); i += 1
        elif ch in "'\"`":
            quote = ch
            put(" ", " ", " ")
        else:
            put(ch, " ", " ")
        i += 1
    return tuple("".join(chars).split("\n") for chars in (code, strings, comments))


def js_findings(source):
    """(line, what) for each value written into JavaScript code."""
    found = []
    for number, (code, strings, comment) in enumerate(zip(*js_split(source)), start=1):
        if PROTOCOL.search(comment):
            continue
        for m in JS_NUMBER.finditer(code):
            digits = m.group(0).replace("_", "").rstrip("n")
            value = int(digits, 0) if digits[:len("0x")].lower() in ("0x", "0b", "0o") else float(digits)
            if value not in ALLOWED_NUMBERS:
                found.append((number, f"number {m.group(0)}"))
        found += [(number, what) for what in string_findings(strings)]
    return found


# ---------------------------------------------------------------- files
def files_to_check(root):
    package = os.path.join(root, "agentcake")
    for folder, dirs, files in os.walk(package):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in sorted(files):
            if name.endswith(".py"):
                yield os.path.join(folder, name), python_findings
    js_folder = os.path.join(package, "static", "src")
    if os.path.isdir(js_folder):
        for name in sorted(os.listdir(js_folder)):
            if name.endswith(".js"):
                yield os.path.join(js_folder, name), js_findings


def hardcoded(root, exempt=None):
    """(path relative to root, line, what) for every finding outside the exempt files."""
    exempt = exempt_paths() if exempt is None else exempt
    found = []
    for path, reader in files_to_check(root):
        rel = os.path.relpath(path, root)
        if rel in exempt:
            continue
        with open(path, encoding="utf-8") as f:
            found += [(rel, line, what) for line, what in reader(f.read())]
    return found


def main(argv):
    root = folder_argument(argv, __doc__)
    found = hardcoded(root)
    for rel, line, what in found:
        print(f"{rel}:{line}: {what}: move it to defaults.json, a data file or a token (or mark a protocol constant)")
    print(f"check_hardcode: {len(found)} value(s) written into the code")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
