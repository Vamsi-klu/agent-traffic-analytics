#!/usr/bin/env python3
"""Find the scripts that start a coding agent with the person's MCP servers.

    python3 tools/check_agent_mcp.py [repository folder]      (default: the folder above tools/)

A script that starts Codex (a command list whose second word is "exec" and whose first names codex or a binary:
["codex", "exec", ...], [brain["binary"], "exec", ...]; in a shell script, codex exec) must, in the same file, give it
a home of its own (CODEX_HOME, which tools/agent_home.py's codex_env sets, or --ignore-user-config) and turn off the
ChatGPT account's apps and plugins (features.apps=false and features.plugins=false, agent_home.CODEX_NO_APPS, or -c
flags made from a list of features, features.{...}=false, which the script's own tests pin). One that starts Claude
Code's print mode (["claude", "-p", ...], [shutil.which("claude"), "-p", ...]; in a shell script, claude -p) must
pass --strict-mcp-config (agent_home.CLAUDE_NO_MCP). Words in a docstring or comment are no command. A script whose
comment says "check_agent_mcp: exempt" and then why (a script no longer run) is left out. Reads every .py, .sh, .js
and .mjs file, leaving out the folder names in tools/limits.json "check_agent_mcp" "skip_dir_names" and test files
(test_*.py and fake_*.py assert commands and start no agent). Prints one line per script and a count; the exit code
is 0 when the count is 0.
"""
import io
import os
import re
import sys
import tokenize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)  # run as a script under python3 -I, the repository root is not on sys.path

from tools.code_checks import folder_argument, limits  # noqa: E402

SUFFIXES = (".py", ".sh", ".js", ".mjs")
# the first word of a command list: the name itself, a variable with it in its name, a lookup by it (shutil.which, a
# dictionary), then the second word
FIRST = (r"""\[\s*(?:["'](?:{name})["']|[\w.]*(?:{name})[\w.]*"""
         r"""|[\w.]+\s*[\[(]\s*["'][^"'\n]*(?:{name})[^"'\n]*["']\s*[\])])""")
CODEX_LIST = re.compile(FIRST.format(name="codex|binary") + r"""\s*,\s*["']exec["']""", re.I)
CLAUDE_LIST = re.compile(FIRST.format(name="claude") + r"""\s*,\s*["']-p["']""", re.I)
AGY_LIST = re.compile(
    FIRST.format(name="agy") + r"""\s*,\s*["'](?:-p|--print|--prompt|--input-format|--disable-slash-commands)["']""",
    re.I,
)
CODEX_SHELL = re.compile(r"^[^#\n]*\bcodex\s+exec\b", re.M)
CLAUDE_SHELL = re.compile(r"^[^#\n]*\bclaude\s+-p\b", re.M)
AGY_SHELL = re.compile(r"^[^#\n]*\bagy\s+(?:-p|--print|--prompt|--input-format)\b", re.M)
CODEX_OWN = re.compile(r"CODEX_HOME|--ignore-user-config|\bcodex_env\s*\(")
# an f-string tokenizes into its pieces, so code_only puts spaces around {...}
CODEX_NO_APPS = re.compile(r"\bCODEX_NO_APPS\b|features\.\s*\{[^}\n]+\}\s*=false")
CODEX_APPS_OFF = ("features.apps=false", "features.plugins=false")
EXEMPT = re.compile(r"#[ \t]*check_agent_mcp:[ \t]*exempt\b[,:;]?[ \t]*(\S.*)?$", re.M)
CLAUDE_OWN = re.compile(r"--strict-mcp-config|\bCLAUDE_NO_MCP\b")
AGY_OWN = re.compile(r"\bagy_env\s*\(|\bagy_home\s*\(|\bHOME\s*=|[\"']HOME[\"']\s*[:\]]")
AGY_SETTINGS = re.compile(r"--settings|\bagy_command\s*\(")


def scripts(root, rules):
    """Paths relative to root of the files the check reads."""
    for folder, dirs, files in os.walk(root):
        rel_folder = os.path.relpath(folder, root)
        dirs[:] = sorted(d for d in dirs if d not in rules["skip_dir_names"])
        for name in sorted(files):
            if name.endswith(SUFFIXES) and not name.startswith(("test_", "fake_")):
                yield os.path.normpath(os.path.join(rel_folder, name))


def exempt(text):
    """Whether the script says it is exempt and why (a mark without a reason exempts nothing)."""
    return any(found.group(1) for found in EXEMPT.finditer(text))


def patterns_for(rel, text):
    """(code, codex_pat, claude_pat, agy_pat) for a file, stripping comments/docstrings from Python."""
    shell = rel.endswith(".sh")
    code = code_only(text) if rel.endswith(".py") else text
    pats = (CODEX_SHELL, CLAUDE_SHELL, AGY_SHELL) if shell else (CODEX_LIST, CLAUDE_LIST, AGY_LIST)
    return (code, *pats)


def starts_an_agent(rel, text):
    code, codex, claude, agy = patterns_for(rel, text)
    return bool(codex.search(code) or claude.search(code) or agy.search(code))


def code_only(text):
    """A Python file's code without its comments and docstrings (a string that is a statement of its own), or the
    text as it is when it does not tokenize."""
    try:
        tokens = [token for token in tokenize.generate_tokens(io.StringIO(text).readline)
                  if token.type not in (tokenize.COMMENT, tokenize.NL)]
    except (tokenize.TokenError, SyntaxError):
        return text
    starts = (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT)
    kept = []
    for index, token in enumerate(tokens):
        before = tokens[index - 1].type if index else tokenize.NEWLINE
        after = tokens[index + 1].type if index + 1 < len(tokens) else tokenize.ENDMARKER
        if not (token.type == tokenize.STRING and before in starts and after == tokenize.NEWLINE):
            kept.append(token.string)
    return " ".join(kept)


def problems(rel, text):
    """What the file starts without a home of its own: [] or the agents' names."""
    code, codex, claude, agy = patterns_for(rel, text)
    found = []
    if codex.search(code):
        if not CODEX_OWN.search(code):
            found.append("Codex without a CODEX_HOME of its own (tools/agent_home.py) or --ignore-user-config")
        if not (CODEX_NO_APPS.search(code) or all(flag in code for flag in CODEX_APPS_OFF)):
            found.append("Codex without features.apps=false and features.plugins=false (agent_home.CODEX_NO_APPS)")
    if claude.search(code) and not CLAUDE_OWN.search(code):
        found.append("claude -p without --strict-mcp-config")
    if agy.search(code):
        if not AGY_OWN.search(code):
            found.append("agy without an isolated HOME of its own (tools/agent_home.py agy_env)")
        if not AGY_SETTINGS.search(code):
            found.append("agy without session --settings denying tools (tools/agent_home.py agy_command)")
    return found


def check(root, rules=None):
    rules = rules or limits("check_agent_mcp")
    found = []
    for rel in scripts(root, rules):
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
            text = f.read()
        if not exempt(text):
            found += [(rel, what) for what in problems(rel, text)]
    return found


def main(argv=None):
    root = folder_argument(sys.argv[1:] if argv is None else argv, __doc__)
    found = check(root)
    for rel, what in found:
        print(f"{rel}: {what}")
    print(f"check_agent_mcp: {len({rel for rel, _ in found})} script(s) start an agent with the person's MCP servers")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
