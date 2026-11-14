# Installing AgentCake: instructions for an AI coding assistant

You are installing **AgentCake 0.4.0** for the user. AgentCake does AI agent behavior analysis for a website: for
each visit it shows whether a human, an AI agent or a bot was acting, and when a human and an agent took turns, with
the replay and the reasons. It runs only on this computer (macOS or Linux): one program and one small database in
`~/.cake`, and a **local page** at `http://127.0.0.1:7878/`. The first time the user opens it, it asks them to register,
then shows them how to connect their website. The command is `agentcake`.

How to work:

- **One command per step**, as written. Do not chain commands with `&&`, `;` or `|`, and do not set variables
  (`NAME=value`): approval rules match a command by how it starts, so plain commands need the fewest approvals.
- After each step, do its **Check**. If a check fails, stop and tell the user what failed; do not skip it.
- Steps marked **ASK** need the user's answer before you go on. Everything else you can do yourself.
- Do not `git clone` or build anything: the release is already built. Work in the folder you were started in; the
  downloads go there.

## Step 1. Choose how to install

If you are already in AgentCake's own folder (its source, or the unpacked release folder `agentcake-0.4.0/`), skip
to step 4: the command is that folder's `bin/agentcake`, by its full path (it needs `python3` 3.11 or newer).

Otherwise, look for uv:

```sh
uv --version
```

If it prints a version, install with uv (**route A**). If not, look for Python:

```sh
python3 --version
```

If it prints Python 3.11 or newer, use AgentCake as one file, `agentcake.pyz` (**route B**). If there is neither uv
nor such a Python, **ASK** the user which of these they want installed, install nothing without their yes, and then
start again at step 1:

- uv, which brings its own Python (with Homebrew: `brew install uv`): https://docs.astral.sh/uv/getting-started/installation/
- a newer Python: https://www.python.org/downloads/

## Step 2. Download the release and check it

The release page is https://github.com/tartini-ai/agent-behavior-analysis/releases/tag/v0.4.0
If the user gave you another release page for this version, download the same files from there. First the checksums:

```sh
curl -fsSLO https://github.com/tartini-ai/agent-behavior-analysis/releases/download/v0.4.0/SHA256SUMS
```

Route A, the wheel:

```sh
curl -fsSLO https://github.com/tartini-ai/agent-behavior-analysis/releases/download/v0.4.0/agentcake-0.4.0-py3-none-any.whl
```

Route B, the one-file version:

```sh
curl -fsSLO https://github.com/tartini-ai/agent-behavior-analysis/releases/download/v0.4.0/agentcake.pyz
```

**Private preview.** While the repository is private, these addresses need a GitHub sign-in: curl stops with
`The requested URL returned error: 404`, and this file could only be read with `gh`. Then download with the GitHub
CLI instead of the curl commands above. First see whether it is signed in:

```sh
gh auth status
```

If it is, download every file of the release into this folder:

```sh
gh release download v0.4.0 --repo tartini-ai/agent-behavior-analysis
```

If `gh` is missing or not signed in, **ASK** the user to set it up in their own terminal, signed in to an account
that can see the repository, and wait; never sign in for them:

- the GitHub CLI: https://cli.github.com/
- then `gh auth login`

If gh says `release not found`, the signed-in account cannot see the repository: tell the user, and do not try
other addresses.

Then check what you downloaded, whichever way you downloaded it:

```sh
shasum -a 256 -c SHA256SUMS --ignore-missing
```

On Linux without `shasum`:

```sh
sha256sum -c SHA256SUMS --ignore-missing
```

**Check:** this command alone decides: the file you downloaded is listed with `OK`. Do not print hashes and compare
them yourself; without that `OK` line the download is not checked. If it says `FAILED`, or that no file was verified,
do not install or run it: tell the user the download does not match the release.

## Step 3. Install

Route A:

```sh
uv tool install --python 3.14 ./agentcake-0.4.0-py3-none-any.whl
```

uv installs the `agentcake` command in its own folder for tools, and downloads Python 3.14 if this computer has none
(3.14 keeps replays smaller). Then ask uv where the command is:

```sh
uv tool dir --bin
```

The command is `agentcake` in the folder it prints, for example `/Users/<name>/.local/bin/agentcake`. Run it by that
full path every time, whether or not the folder is on PATH; if you mention PATH to the user, say what doctor's
"agentcake on PATH" line says (step 5). If uv suggests adding the folder to PATH (`uv tool update-shell`), do not: that
edits shell profiles.

Route B: nothing to install. The command is `python3` followed by the full path of `agentcake.pyz` in this folder, for
example `python3 /Users/<name>/agentcake/agentcake.pyz`. Leave the file where it is: it is AgentCake.

**From here on, `agentcake` in a command stands for that full command.** Write it out in full every time, also where
AgentCake's own messages say just `agentcake`.

**Check:** `agentcake --version` prints `agentcake 0.4.0`.

## Step 4. Start AgentCake

```sh
agentcake start
```

It runs AgentCake in the background on 127.0.0.1 (port 7878) and prints the local page's address. If it says
AgentCake is already running, run `agentcake status`: its `"version"` should be `0.4.0`. An older version is an
earlier install using the same data folder: **ASK** the user before you stop it with `agentcake stop`, then start
again. Its visits stay, and this version reads them.

## Step 5. Self-check

```sh
agentcake doctor
```

Each line says PASS, FAIL, WARN or SKIP. On a fresh install every line says PASS except "visit received", which fails
until AgentCake has received a visit: run `agentcake ping` (one test visit, marked as a test, so it never counts as a
real visit), then doctor again. WARN and SKIP are not failures; pass on to the user what such a line
says. The last line says the user's own website is not connected: that is expected.

**Check:** no line says FAIL.

## Step 6. Tell the user

```sh
agentcake setup --print
```

It prints the local page's address and what to tell the user. Tell the user, in their language:

1. **Open the local page** at the address it printed (`http://127.0.0.1:7878/` unless the port was changed).
2. **Registering is theirs to do.** The first time they open the local page, AgentCake asks them to register: e-mail
   address required, company optional, sent to Tartini AI only when they press "Register & Continue"
   ([`PRIVACY.md`](PRIVACY.md)). Give them the page's address and nothing more: never fill in their e-mail address,
   never press "Register & Continue" for them, and do not open the page in a browser yourself to do it. The page
   script, collecting visits and the command line work without registering.
3. **Then the page shows how to connect their website**, step by step: its address, where AgentCake runs (this
   computer, for a site that runs on it; for a public website, AgentCake on a server the site can reach:
   [`SERVER.md`](SERVER.md)), the line to add to its pages, and the first visit when it arrives. Visitors of a public
   website cannot reach 127.0.0.1 on this computer.
4. **Offer to connect it for them**, in one line; do it only if they ask (below).
5. Route B only: AgentCake runs from the folder that holds `agentcake.pyz`, so that folder has to stay.

## Connect the user's website (only if the user asks)

In the website's code folder:

```sh
agentcake setup --print --site
```

It detects the framework and prints, step by step, the settings to save, the one line to add to the site's pages and,
for a site with server code, the middleware that gives AgentCake the server's half of each visit. Follow it exactly.
Change nothing else: no formatting, no other files, no installs beyond the ones it prints, no commits.

- **site_domain**: find it in the repository (a `CNAME` file, `homepage` in `package.json`, a deploy config, the
  canonical URL in the HTML). **ASK** the user only if you cannot find it; if you cannot ask, use `localhost` and say
  so at the end.
- **site_url**: start the site the way it runs on this computer (its dev server, for example) and save the address of
  one of its pages, with the dev server's own port, so that doctor opens it as a browser does and checks the page
  script and the middleware's token:

  ```sh
  agentcake config set site_url http://localhost:3000/
  ```

  If the site cannot run here, skip this and say so: doctor then checks the site's files only.
- Run `agentcake doctor` again. A FAIL line names what is missing (the page script, the middleware); fix only that.

Then tell the user what is left for them: deploying the site change; for visitors of a public website, AgentCake has
to run on a server the website can reach, since their browsers cannot reach 127.0.0.1 on this computer
([`SERVER.md`](SERVER.md)); and mentioning session recording in the site's privacy notice
([`docs/privacy-notice-template.md`](docs/privacy-notice-template.md)).

## If you run in a sandbox

- A command that writes outside the current folder (uv's folders, `~/.cake`) may fail with `Operation not permitted`
  or `Read-only file system`, and so would every step after it. **ASK** the user to allow it, or to run the rest in
  their own terminal: then write out all the remaining commands at once, in order (step 3's install, `agentcake
  start`, `agentcake doctor`; on route A, `uv tool dir --bin` first, and `agentcake` in the folder it prints), and
  go on from what they send back. Do not try other folders, and never sudo.
- A sandbox without network access cannot download: curl stops with `Could not resolve host` or
  `Couldn't connect to server`, and gh with `error connecting to api.github.com`. Tell the user there is no network
  access here, and ask them to give you network access or to run the step in their own terminal. Do not say a server
  is down or has to be started.
- Nor can it reach 127.0.0.1. doctor then says no connection is allowed from here and that AgentCake may well be
  running. Do not start it again: ask the user to run `agentcake doctor` in their own terminal, or to give you network
  access (Codex: `-c sandbox_workspace_write.network_access=true`).

## Never

- Never use sudo, never install anything but AgentCake without asking, never edit shell profiles or other projects.
- Never register for the user, and never type their e-mail address anywhere.
- Never send the site key or any data anywhere except the user's own AgentCake.
- Never commit or push the user's repositories.
