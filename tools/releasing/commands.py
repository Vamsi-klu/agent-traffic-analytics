"""Running the build's commands (npm, esbuild, AgentCake's own build_js.py) for a release.

run() shows a command's output as it comes and turns a missing program or a failure into a ReleaseError that says
what is needed. output() is for a command whose output is the result (esbuild reading cake.js on stdin).
"""
import os
import subprocess

from tools.releasing.settings import ReleaseError

NODE_NEEDED = "the release builds the local pages and cake.js with Node.js and npm (release.json \"toolchain\")"


def shown(command, tree):
    """The command as the log shows it: the program by its name, paths inside tree relative to it."""
    words = [os.path.basename(command[0])]
    for word in command[1:]:
        inside = os.path.isabs(word) and os.path.commonpath([tree, word]) == tree
        words.append(os.path.relpath(word, tree) if inside else word)
    return " ".join(words)


def run(command, folder, tree):
    """Run command in folder (both shown relative to tree); a failure stops the release."""
    where = os.path.relpath(folder, tree)
    print(f"release: {shown(command, tree)} (in {where})", flush=True)
    try:
        code = subprocess.run(command, cwd=folder).returncode
    except FileNotFoundError:
        raise ReleaseError(f"{command[0]} is not installed: {NODE_NEEDED}") from None
    if code != 0:
        raise ReleaseError(f"{shown(command, tree)} failed in {where} (exit {code})")


def output(command, text, folder):
    """Run command with text on stdin; returns its stdout. Anything it writes to stderr is shown."""
    try:
        done = subprocess.run(command, cwd=folder, input=text, capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError:
        raise ReleaseError(f"{command[0]} is not there: {NODE_NEEDED}") from None
    if done.stderr.strip():
        print(done.stderr.rstrip(), flush=True)
    if done.returncode != 0:
        raise ReleaseError(f"{os.path.basename(command[0])} failed (exit {done.returncode})")
    return done.stdout
