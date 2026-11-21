"""A home of their own for the coding agents the repository's scripts start: judges, fact checks, the install benches
and release test drivers.

Codex reads its config.toml, MCP servers included, from CODEX_HOME (default ~/.codex). The person's own starts their
MCP servers: on 11/19 a posthog server, which sent a request to mcp.posthog.com on every start, and ChatGPT's
node_repl, which runs code outside Codex's sandbox. The ChatGPT sign-in brings its apps (an MCP server at chatgpt.com)
and plugins to any CODEX_HOME: CODEX_NO_APPS turns them off on the command line, for `codex exec` and
`codex exec resume`. Claude Code gets the account's claude.ai connectors with its sign-in alone; --strict-mcp-config
leaves it only the MCP servers it is given.

Antigravity CLI (`agy`) reads global plugins, MCP servers, hooks and skills from ~/.gemini/config/ and its settings and
conversation history from ~/.gemini/antigravity-cli/, while authenticating via the macOS login keychain under
~/Library/Keychains. Giving each headless `agy` session its own temporary HOME that symlinks only Library/Keychains
(never read or printed) and passing session-only --settings denying all file, command, URL and MCP tools runs Gemini
without any of the person's MCP servers, plugins, hooks, memories or workspace.

Claude Code as a judge (`claude -p`, when Codex has no quota) keeps its sign-in in the login keychain too, and reads
the person's settings, CLAUDE.md, memories, plugins and skills from ~/.claude and their MCP servers from ~/.claude.json.
Each session gets a temporary HOME holding only the Library/Keychains link, an empty MCP configuration taken strictly,
no tools, no setting sources and no saved session, and none of the starting Claude Code session's own variables
(CLAUDECODE and CLAUDE_*: its messaging socket and token, its effort, its config folder).

    codex_home(folder=None, real=None) -> folder with auth.json symlink and minimal config.toml
    codex_env(base=None, folder=None, real=None) -> base (default os.environ) with CODEX_HOME=codex_home(folder)
    agy_home(folder=None, real=None, model=None) -> folder with Library/Keychains symlink and agy-settings.json
    agy_env(base=None, folder=None, real=None, model=None) -> base with HOME=agy_home(...) and XDG_* stripped
    agy_command(settings_path, model=None, timeout_s=1800, binary=None) -> headless stream-json command list
    claude_home(folder=None, real=None) -> folder with only the Library/Keychains symlink
    claude_env(base=None, folder=None, real=None) -> base with HOME=claude_home(...), CLAUDE*/XDG_* stripped
    claude_command(model=None, effort=None, binary=None) -> isolated `claude -p` reading the prompt on stdin
    ask(prompt, folder, name, backend=None, model=None, timeout_s=1800) -> one isolated Codex, agy or Claude session
        (defaults: $CAKE_JUDGE_BACKEND or codex, $CAKE_JUDGE_MODEL, Claude's effort $CAKE_JUDGE_EFFORT or CLAUDE_EFFORT)
    CODEX_NO_APPS: the flags every Codex command carries, so that the account's apps and plugins stay off
    CLAUDE_NO_MCP: Claude Code's flag for no MCP server but those it is given; every claude -p carries it
"""
import atexit
import json
import os
import shutil
import subprocess
import tempfile
import threading
import tomllib
from pathlib import Path

MODEL_KEYS = ("model", "model_reasoning_effort", "personality")
FEATURES_OFF = ("apps", "plugins", "remote_plugin", "browser_use", "browser_use_external",
                "browser_use_full_cdp_access", "computer_use", "in_app_browser", "skill_mcp_dependency_install")
CODEX_CMD = ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only"]
CODEX_NO_APPS = ["-c", "features.apps=false", "-c", "features.plugins=false"]
CLAUDE_NO_MCP = "--strict-mcp-config"
AGY_DENY_ALL = ("read_file(*)", "write_file(*)", "read_url(*)", "execute_url(*)",
                "download_url(*)", "command(*)", "unsandboxed(*)", "mcp(*)")
XDG_FOLDERS = ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME")
AGY_SETTINGS_FILE = "agy-settings.json"
CLAUDE_EMPTY_MCP = json.dumps({"mcpServers": {}})
# the model and effort when none is given, the ones calibrated against Codex: Sonnet, not the Opus that writes the words
CLAUDE_MODEL = "claude-sonnet-5-5"
CLAUDE_EFFORT = "high"
CLAUDE_SIGN_INS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY")  # the person's, passed on unread
BACKENDS = ("codex", "agy", "claude")
DEFAULT_BACKEND_ENV = "CAKE_JUDGE_BACKEND"
DEFAULT_MODEL_ENV = "CAKE_JUDGE_MODEL"
DEFAULT_EFFORT_ENV = "CAKE_JUDGE_EFFORT"
DEFAULT_TIMEOUT_S = 1800
_TEMPORARY = {}
_MAKING = threading.Lock()


def model_settings(real):
    """config.toml's text: MODEL_KEYS of the person's config.toml in real, then FEATURES_OFF turned off."""
    path, values = os.path.join(real, "config.toml"), {}
    if os.path.isfile(path):
        with open(path, "rb") as f:
            values = tomllib.load(f)
    model = "".join(f"{key} = {json.dumps(values[key])}\n" for key in MODEL_KEYS if key in values)
    return model + "\n[features]\n" + "".join(f"{name} = false\n" for name in FEATURES_OFF)


def temporary_folder():
    if "folder" not in _TEMPORARY:
        _TEMPORARY["folder"] = tempfile.mkdtemp(prefix="codex-home-")
        atexit.register(shutil.rmtree, _TEMPORARY["folder"], True)
    return _TEMPORARY["folder"]


def codex_home(folder=None, real=None):
    real = real or os.path.join(os.path.expanduser("~"), ".codex")
    with _MAKING:
        folder = folder or temporary_folder()
        os.makedirs(folder, exist_ok=True)
        try:
            os.symlink(os.path.join(real, "auth.json"), os.path.join(folder, "auth.json"))
        except FileExistsError:  # made before, by this process or another one sharing the folder: kept as it is
            pass
        write_if_changed(os.path.join(folder, "config.toml"), model_settings(real))
    return folder


def write_if_changed(path, text):
    """Writes text to path unless it holds it already: opening it to write empties it first."""
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def codex_env(base=None, folder=None, real=None):
    return dict(os.environ if base is None else base, CODEX_HOME=codex_home(folder, real))


def agy_binary(real=None):
    """Resolve the agy binary before HOME is overridden to a temporary folder."""
    found = shutil.which("agy")
    if found:
        return found
    home = real or os.path.expanduser("~")
    return os.path.join(home, ".local", "bin", "agy")


def agy_model_setting(real):
    """Only the person's selected model label from ~/.gemini/antigravity-cli/settings.json, or None."""
    path = os.path.join(real, ".gemini", "antigravity-cli", "settings.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            value = json.load(f).get("model")
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, str) and value.strip() else None


def agy_settings(real=None, model=None, deny=AGY_DENY_ALL):
    """Session-only settings for headless agy: no tools allowed, no non-workspace access, sandboxed."""
    settings = {
        "agentMode": "",
        "toolPermission": "request-review",
        "allowNonWorkspaceAccess": False,
        "enableTerminalSandbox": True,
        "permissions": {"allow": [], "deny": list(deny)},
    }
    if not model and real:
        copied = agy_model_setting(real)
        if copied:
            settings["model"] = copied
    return settings


def agy_home(folder=None, real=None, model=None, require_keychains=True):
    """An isolated HOME for agy: symlink only Library/Keychains and write agy-settings.json."""
    real = real or os.path.expanduser("~")
    keychains = os.path.join(real, "Library", "Keychains")
    if require_keychains and not os.path.lexists(keychains) and not os.environ.get("GEMINI_API_KEY"):
        raise FileNotFoundError(f"agy sign-in requires {keychains} (refusing to start headless agy without login)")
    with _MAKING:
        folder = keychain_home(folder, real, "agy-home-")
        text = json.dumps(agy_settings(real=real, model=model), indent=2) + "\n"
        write_if_changed(os.path.join(folder, AGY_SETTINGS_FILE), text)
    return folder


def keychain_home(folder, real, prefix):
    """folder (a new temporary one, removed at exit, when None) holding a link to real's Library/Keychains: the
    sign-in agy and Claude Code keep in the login keychain, linked and never read. Called holding _MAKING."""
    if folder is None:
        folder = tempfile.mkdtemp(prefix=prefix)
        atexit.register(shutil.rmtree, folder, True)
    os.makedirs(folder, exist_ok=True)
    keychains = os.path.join(real, "Library", "Keychains")
    if os.path.lexists(keychains):
        os.makedirs(os.path.join(folder, "Library"), exist_ok=True)
        try:
            os.symlink(keychains, os.path.join(folder, "Library", "Keychains"))
        except FileExistsError:  # made before, by this process or another one sharing the folder: kept as it is
            pass
    return folder


def agy_env(base=None, folder=None, real=None, model=None):
    """Environment for an isolated agy session: custom HOME and no XDG overrides pointing at the user's home."""
    env = dict(os.environ if base is None else base)
    for key in XDG_FOLDERS:
        env.pop(key, None)
    env["HOME"] = agy_home(folder=folder, real=real, model=model)
    return env


def agy_command(settings_path, model=None, timeout_s=DEFAULT_TIMEOUT_S, binary=None):
    """Headless agy command reading one stream-json user message on stdin and emitting NDJSON on stdout."""
    cmd = [binary or agy_binary(), "--input-format", "stream-json", "--output-format", "stream-json",
           "--disable-slash-commands", "--settings", str(settings_path), "--print-timeout", f"{int(timeout_s)}s"]
    if model:
        cmd += ["--model", model]
    return cmd


def agy_stream_input(prompt):
    return json.dumps({"event": "user", "message": {"content": prompt}}, ensure_ascii=False) + "\n"


def parse_agy_stream(stdout):
    """(reply_text, info) from agy --output-format stream-json stdout."""
    info = {"model": None, "permission_mode": None, "mcp_tools": [], "status": None,
            "error": None, "duration_seconds": None, "num_turns": None, "usage": None, "tool_calls": 0}
    deltas = []
    response = ""
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("event")
        if kind == "init":
            init = event.get("init") or {}
            info["model"] = init.get("model")
            info["permission_mode"] = init.get("permission_mode")
            tools = init.get("tools") or []
            info["mcp_tools"] = [t for t in tools if isinstance(t, str) and t.startswith("mcp_")]
        elif kind == "step_update":
            upd = event.get("step_update") or {}
            if upd.get("step_type") == "agent_response" and upd.get("text_delta"):
                deltas.append(upd["text_delta"])
            elif upd.get("step_type") == "tool" and upd.get("state") in ("DONE", "ERROR"):
                info["tool_calls"] += 1
        elif kind == "result":
            res = event.get("result") or {}
            info["status"] = res.get("status")
            info["error"] = res.get("error")
            info["duration_seconds"] = res.get("duration_seconds")
            info["num_turns"] = res.get("num_turns")
            info["usage"] = res.get("usage")
            if res.get("status") == "SUCCESS":
                response = res.get("response") or "".join(deltas)
            else:
                response = ""
    return response, info


def claude_binary(real=None):
    """Claude Code's command, found before HOME points at a temporary folder."""
    return shutil.which("claude") or os.path.join(real or os.path.expanduser("~"), ".local", "bin", "claude")


def claude_home(folder=None, real=None):
    """A HOME for one claude -p: only the link to the person's Library/Keychains, their sign-in."""
    real = real or os.path.expanduser("~")
    keychains = os.path.join(real, "Library", "Keychains")
    if not os.path.lexists(keychains) and not any(os.environ.get(name) for name in CLAUDE_SIGN_INS):
        raise FileNotFoundError(f"Claude Code's sign-in needs {keychains} (no claude -p without one)")
    with _MAKING:
        return keychain_home(folder, real, "claude-home-")


def claude_env(base=None, folder=None, real=None):
    """base without the starting Claude Code session's variables (CLAUDECODE, CLAUDE_*) and XDG folders, but with the
    person's sign-in variables, and HOME=claude_home(folder)."""
    env = {name: value for name, value in (os.environ if base is None else base).items()
           if name in CLAUDE_SIGN_INS or not (name.startswith("CLAUDE") or name in XDG_FOLDERS)}
    env["HOME"] = claude_home(folder=folder, real=real)
    return env


def claude_command(model=None, effort=None, binary=None):
    """claude -p with the prompt on stdin: an empty MCP configuration taken strictly, no tool, no setting source, no
    slash command or skill, no saved session; stream-json says which tools and MCP servers the session had."""
    claude_exe = binary or claude_binary()
    return [claude_exe, "-p", CLAUDE_NO_MCP, "--mcp-config", CLAUDE_EMPTY_MCP, "--tools", "", "--setting-sources", "",
            "--no-session-persistence", "--disable-slash-commands", "--output-format", "stream-json", "--verbose",
            "--model", model or CLAUDE_MODEL, "--effort", effort or os.environ.get(DEFAULT_EFFORT_ENV) or CLAUDE_EFFORT]


def parse_claude_stream(stdout):
    """(reply_text, info) from claude -p --output-format stream-json: the result's text when it succeeded ('' for an
    error such as a usage limit), and for the log what the session had and did. Paths (cwd, memory) are left out."""
    info = {"model": None, "tools": None, "mcp_servers": None, "permission_mode": None, "api_key_source": None,
            "status": None, "is_error": None, "stop_reason": None, "num_turns": None, "duration_ms": None,
            "total_cost_usd": None, "tool_calls": 0, "rate_limit": None}
    reply = ""
    for line in stdout.splitlines():
        try:
            event = json.loads(line) if line.strip().startswith("{") else {}
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            servers = event.get("mcp_servers") or []
            info.update(model=event.get("model"), tools=list(event.get("tools") or []),
                        mcp_servers=[s.get("name") if isinstance(s, dict) else s for s in servers],
                        permission_mode=event.get("permissionMode"), api_key_source=event.get("apiKeySource"))
        elif kind == "assistant":
            content = (event.get("message") or {}).get("content") or []
            info["tool_calls"] += sum(1 for block in content if isinstance(block, dict) and block.get("type") == "tool_use")
        elif kind == "rate_limit_event":
            info["rate_limit"] = (event.get("rate_limit_info") or {}).get("status")
        elif kind == "result":
            info.update({key: event.get(key) for key in ("stop_reason", "num_turns", "duration_ms", "total_cost_usd")},
                        status=event.get("subtype"), is_error=bool(event.get("is_error")))
            reply = (event.get("result") or "") if event.get("subtype") == "success" and not info["is_error"] else ""
    return reply, info


def default_backend(backend=None):
    chosen = backend or os.environ.get(DEFAULT_BACKEND_ENV) or "codex"
    if chosen not in BACKENDS:
        raise ValueError(f"unknown judge backend {chosen!r}; expected one of {BACKENDS}")
    return chosen


def default_model(model=None):
    return model or os.environ.get(DEFAULT_MODEL_ENV) or None


def _scrub(text, real_home, *temps):
    for path in temps:
        if path:
            real = os.path.realpath(path)
            text = text.replace(real, "<tmp>").replace(str(path), "<tmp>")
    return text.replace(str(real_home), "~")


def ask(prompt, folder, name, backend=None, model=None, timeout_s=DEFAULT_TIMEOUT_S, real_home=None, binary=None):
    """Run one fresh isolated Codex, agy or Claude session in an empty folder; write prompt, reply and scrubbed log."""
    chosen = default_backend(backend)
    real = real_home or os.path.expanduser("~")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.prompt.txt").write_text(prompt, encoding="utf-8")
    runner = {"codex": _ask_codex, "agy": _ask_agy, "claude": _ask_claude}[chosen]
    reply, log = runner(prompt, folder / f"{name}.reply.txt", default_model(model), timeout_s, real, binary)
    (folder / f"{name}.log.txt").write_text(log, encoding="utf-8")
    return reply


def _ask_codex(prompt, reply_path, model, timeout_s, real, binary):
    cmd = list(CODEX_CMD) + list(CODEX_NO_APPS) + (["-m", model] if model else []) + ["-o", str(reply_path), "-"]
    with tempfile.TemporaryDirectory(prefix="judge-cwd-") as empty:
        try:
            done = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout_s,
                                  cwd=empty, env=codex_env(real=os.path.join(real, ".codex")))
            log = f"backend codex\nexit {done.returncode}\n--- stderr (tail)\n{done.stderr[-4000:]}\n"
        except subprocess.TimeoutExpired:
            log = f"backend codex\ntimed out after {timeout_s} s\n"
        log = _scrub(log, real, empty)
    return (reply_path.read_text(encoding="utf-8") if reply_path.exists() else ""), log


def _ask_agy(prompt, reply_path, model, timeout_s, real, binary):
    """A reply only from the model asked for: agy falls back to its default model when it doesn't know the one named."""
    with tempfile.TemporaryDirectory(prefix="judge-cwd-") as empty, \
            tempfile.TemporaryDirectory(prefix="agy-home-") as home:
        env = agy_env(folder=home, real=real, model=model)
        cmd = agy_command(os.path.join(home, AGY_SETTINGS_FILE), model=model, timeout_s=timeout_s,
                          binary=binary or agy_binary(real=real))
        reply = ""
        try:
            done = subprocess.run(cmd, input=agy_stream_input(prompt), capture_output=True, text=True,
                                  timeout=timeout_s, cwd=empty, env=env)
            reply, info = parse_agy_stream(done.stdout)
            note = f"asked for {model}, the session ran {info['model']}: reply dropped\n"
            reply, note = ("", note) if model and info["model"] and info["model"] != model else (reply, "")
            if reply:
                reply_path.write_text(reply, encoding="utf-8")
            meta = json.dumps(info, ensure_ascii=False)
            log = f"backend agy\n{note}exit {done.returncode}\ninfo {meta}\n--- stderr (tail)\n{done.stderr[-4000:]}\n"
        except subprocess.TimeoutExpired:
            log = f"backend agy\ntimed out after {timeout_s} s\n"
        log = _scrub(log, real, empty, home)
    return reply, log


def _ask_claude(prompt, reply_path, model, timeout_s, real, binary):
    """A reply only from a session that had no tool and no MCP server and called none: one that did is no judge of
    the kind calibrated, and its reply is dropped (the judges then retry or count the items unanswered)."""
    model, effort = model or CLAUDE_MODEL, os.environ.get(DEFAULT_EFFORT_ENV) or CLAUDE_EFFORT
    with tempfile.TemporaryDirectory(prefix="judge-cwd-") as empty, \
            tempfile.TemporaryDirectory(prefix="claude-home-") as home:
        cmd = claude_command(model=model, effort=effort, binary=binary or claude_binary(real=real))
        reply = ""
        try:
            done = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout_s,
                                  cwd=empty, env=claude_env(folder=home, real=real))
            reply, info = parse_claude_stream(done.stdout)
            note = ""
            if info["tools"] != [] or info["mcp_servers"] != [] or info["tool_calls"]:
                reply, note = "", "not isolated: the session had tools or MCP servers (or no init event); reply dropped\n"
            if reply:
                reply_path.write_text(reply, encoding="utf-8")
            meta = json.dumps(info, ensure_ascii=False)
            log = (f"backend claude\nmodel {model} effort {effort}\n{note}exit {done.returncode}\ninfo {meta}\n"
                   f"--- stderr (tail)\n{done.stderr[-4000:]}\n")
        except subprocess.TimeoutExpired:
            log = f"backend claude\nmodel {model} effort {effort}\ntimed out after {timeout_s} s\n"
        log = _scrub(log, real, empty, home)
    return reply, log
