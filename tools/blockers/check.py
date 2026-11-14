#!/usr/bin/env python3
"""Would the content blockers visitors run block cake.js or its uploads? Run before each release; needs the internet.

    python3 -I tools/blockers/check.py [--dir DIR] [--report FILE]

Checks every request a visitor's browser makes to AgentCake (targets.requests(): the routes of the public listener
under SERVER.md's path_prefix on its example site, and the same on the local page's address) against the default
filter lists of uBlock Origin, Brave (Standard and Aggressive mode) and AdGuard, as they are today: each blocker's
catalog says which lists are on by default (blockers.json). The lists, a venv and the pinned matcher (adblock, the
Python bindings of Brave's adblock-rust, installed by hash) go into DIR, by default a new temporary folder removed at
the end; nothing goes into the repository or into AgentCake. Prints each request with what blocks it (rule, list,
line) and the address and sha256 of every list it read; --report writes all of it as JSON.

Exit code 0: no current request is blocked (a route kept only for old pages may be, as SERVER.md says); 1: a current
request is blocked, and the lines say by what; 2: a catalog, a list or the matcher could not be fetched, so nothing
was decided. live.py checks the same in a real Chromium with uBO Lite.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.blockers import targets  # noqa: E402  (the repository is put on sys.path first)

HERE = os.path.dirname(os.path.abspath(__file__))
USER_AGENT = "agentcake-blocker-check"
FETCH_TIMEOUT_S = 60
OK, BLOCKED, UNDECIDED = 0, 1, 2


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as answer:
        return answer.read()


def download_lists(conf, folder):
    """[{blocker, name, url, path, sha256, bytes, hosts, standard_first_party}] of every default list, fetched once per
    address; raises OSError naming what could not be fetched."""
    seen, out = {}, []
    for blocker, spec in conf["blockers"].items():
        catalog = json.loads(fetch(spec["catalog"])) if "catalog" in spec else None
        for name, url, standard_first_party in targets.lists_of(blocker, catalog, conf):
            if url not in seen:
                try:
                    body = fetch(url)
                except OSError as e:
                    raise OSError(f"{blocker}: {name}: {url}: {e}") from e
                path = os.path.join(folder, hashlib.sha256(url.encode()).hexdigest()[:16] + ".txt")
                with open(path, "wb") as f:
                    f.write(body)
                seen[url] = {"path": path, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                             "hosts": targets.hosts_format(body.decode("utf-8", "replace"))}
            out.append(dict(seen[url], blocker=blocker, name=name, url=url,
                            standard_first_party=standard_first_party))
    return out


def matcher_python(conf, folder):
    """A venv in folder with the pinned matcher installed by hash; its python."""
    venv = os.path.join(folder, "venv")
    subprocess.run([sys.executable, "-m", "venv", venv], check=True)
    pin = conf["matcher"]
    requirements = os.path.join(folder, "requirements.txt")
    with open(requirements, "w", encoding="utf-8") as f:
        f.write(f"{pin['package']}=={pin['version']} " + " ".join(f"--hash=sha256:{h}" for h in pin["sha256"]) + "\n")
    python = os.path.join(venv, "bin", "python")
    subprocess.run([python, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "--no-deps",
                    "--only-binary=:all:", "--require-hashes", "-r", requirements], check=True)
    return python


def match(python, lists, reqs, folder):
    job, answer = os.path.join(folder, "job.json"), os.path.join(folder, "answer.json")
    with open(job, "w", encoding="utf-8") as f:
        json.dump({"lists": lists, "requests": reqs}, f)
    subprocess.run([python, "-I", os.path.join(HERE, "match.py"), job, answer], check=True)
    with open(answer, encoding="utf-8") as f:
        return json.load(f)


def where(rule, list_names, lists):
    """'<list> line <n>' for each list of the names that writes the rule."""
    out = []
    for item in lists:
        if item["name"] in list_names:
            with open(item["path"], encoding="utf-8", errors="replace") as f:
                out += [f"{item['name']} line {n}" for n in targets.line_of(rule, f.read())]
    return out


def judge(reqs, answers, lists):
    """Rows of the report and the requests that fail the check (blocked and not legacy)."""
    rows, failing = [], []
    for req, answer in zip(reqs, answers):
        row = dict(req, verdicts={})
        for blocker, v in answer.items():
            if v["blocked"]:
                named = {hit["list"] for hit in v["lists"] if hit["rule"] == v["rule"]}
                v = dict(v, written_at=where(v["rule"], named, lists))
                if not req["legacy"]:
                    failing.append((req, blocker, v))
            row["verdicts"][blocker] = v
        rows.append(row)
    return rows, failing


def show(rows, failing, lists):
    for row in rows:
        blocked = {b: v for b, v in row["verdicts"].items() if v["blocked"]}
        state = "blocked" if blocked else "passes"
        if blocked and row["legacy"]:
            state = "blocked, expected (kept only for old pages)"
        print(f"{row['label']:34} {row['url']:52} {state}")
        for blocker, v in blocked.items():
            print(f"    {blocker}: {v['rule']}  ({'; '.join(v['written_at']) or 'line not found'})")
    print(f"\nlists read ({len(lists)}):")
    for item in lists:
        print(f"  {item['blocker']}: {item['name']}  {item['url']}  sha256 {item['sha256']}")
    current = sum(not r["legacy"] for r in rows)
    print(f"\nblockers: {len({r['label'] for r, _, _ in failing})} of {current} current requests blocked")


def run(folder, report):
    conf = targets.settings()
    reqs = [dict(r, first_party=targets.first_party(r["url"], r["page"])) for r in targets.requests(conf)]
    try:
        lists = download_lists(conf, folder)
        python = matcher_python(conf, folder)
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"blockers: could not check, nothing decided: {e}")
        return UNDECIDED
    rows, failing = judge(reqs, match(python, lists, reqs, folder), lists)
    show(rows, failing, lists)
    if report:
        with open(report, "w", encoding="utf-8") as f:
            json.dump({"matcher": conf["matcher"], "lists": [{k: v for k, v in i.items() if k != "path"}
                                                             for i in lists], "requests": rows}, f, indent=1)
    return BLOCKED if failing else OK


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", help="keep the lists and the venv here instead of a temporary folder")
    parser.add_argument("--report", help="write the whole result as JSON to this file")
    args = parser.parse_args(argv)
    folder = args.dir or tempfile.mkdtemp(prefix="agentcake-blockers-")
    os.makedirs(folder, exist_ok=True)
    try:
        return run(folder, args.report)
    finally:
        if not args.dir:
            shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
