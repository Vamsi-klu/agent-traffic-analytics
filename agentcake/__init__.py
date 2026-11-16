"""Agent Cake: which visits to a website were an AI agent and which were a human, on your own computer.

One Python process and one SQLite database, standard library only, like PostHog 1.0's self-hosted install. This
package is cake 0.3.4's single cake.py split into one module per job:

- command line: cli.py runs the commands (__main__.py checks the Python version first); daemon.py, site_setup.py,
  doctor.py, ping.py and migrate.py are commands of their own; config.py, datafiles.py, wording.py, paths.py and
  units.py hold the settings, the shipped data files, the words, the paths and the unit conversions;
- HTTP: server.py runs the two listeners, routes.py names the view for each path, responses.py is the value a view
  returns; the resources are collect.py, edge_api.py (POST /edge), the JSON API in api/ (one module per resource),
  assets.py (cake.js, which build_js.py makes, and the compiled local pages of web/); activity.py is when a
  session's actions began and ended;
- uploads: upload.py reads one upload of cake.js, site_origin.py says where it came from, collect_store.py
  keeps it; visit_batches.py and session_replay.py give a visit's uploads and replay back to their readers;
- storage: store.py and schema.sql (SQLite); streams.py, replay_chunks.py, codecs.py, styles.py, storage_config.py,
  maintenance.py and recompress.py (replay chunks); space.py (the disk budget);
- judging: judging.py and detect/;
- the server half: netfacts.py and ip_salt.py (an upload request's network facts, the address hashes' salt),
  edge_secret.py (the secret a site's middleware shares with cake), edge_token.py (the page tokens it signs: made,
  read, kept once); a web server's log: logs.py (`logs import`) reads it with log_formats.py and signs its
  batches with edge_signature.py, edge_api.py takes them, log_match.py and log_report.py keep what they say.

__version__ is the only place the version is written; the wheel build (pyproject.toml) and the release read it here.
"""

__version__ = "0.4.2"
