"""Building a release of AgentCake: what tools/release.py runs. Not shipped, not imported by agentcake.

A release is four files, made from one git commit and nothing else, so that building the same commit again gives the
same bytes (with the same Python, its zlib, and Node: release.json "toolchain"):

- agentcake-<version>-py3-none-any.whl: the package, with the local pages compiled into it and cake.js minified, without
  what only a checkout uses (release.json "package_files"); no dependencies. `uv tool install` or pip installs it; a
  server unpacks it (SERVER.md).
- agentcake.pyz: the same package as one file that Python runs: `python3 agentcake.pyz <command>` (pyz_main.py).
- agentcake-<version>.tar.gz: the release folder, bin/agentcake and the package, with what a server install needs
  (SERVER.md, deploy/cake.service, deploy/Caddyfile, docker-compose.yml, Dockerfile, .dockerignore and the wheel); it
  is also a source distribution.
- SHA256SUMS: their hashes, for `shasum -a 256 -c SHA256SUMS`.

The modules, in the order build.py runs them:

- settings.py: release.json, and the error every step raises;
- source.py: the commit, its time (every file in the release carries it) and a clean copy of it to build in;
- bundled_lists.py: the lists that ship with AgentCake: refreshed online before a release, checked at build;
- caddyfile.py: deploy/Caddyfile's trusted proxies, Cloudflare's ranges from those lists: written at refresh, checked
  at build;
- readme.py: README's pictures, on main in the repository, named at the release's tag in what the release ships;
- webapp.py: `npm ci && npm run build` of web/, copied into the package;
- notices.py: the third-party notices that build writes into the pages, checked once they are in the package;
- middleware.py: the sites' middleware, edge/, copied into the package, its WordPress plugin naming the version being
  released;
- cakejs.py: cake.js minified with esbuild;
- commands.py: running npm, esbuild and build_js.py;
- project.py: the version, the metadata from pyproject.toml, and which files are the package;
- reproducible.py: zip and tar files whose bytes depend only on their contents and the commit's time;
- wheel.py, pyz.py (with pyz_main.py), archive.py, checksums.py: the four files;
- scan.py: what must never be in a release (compiled Python, node_modules, this computer's paths, the git user);
- build.py: all of the above, into the output folder.
"""
