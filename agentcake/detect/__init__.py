"""Judging who acted in a session: a human or an AI agent, and which agent.

verdict.py makes one conclusion per session from four layers, each in its own modules:
  name and verification  verdict_identity.py; the bundled lists (lists.py, built by lists_build.py, lists_names.py,
                         lists_ranges.py, lists_keys.py); Web Bot Auth (webbotauth.py, httpsig.py, sfv.py, ed25519.py,
                         keydirectory.py)
  environment            env_rules.py and predicate.py (the rule table and its language), env_signals.py (what the
                         rules read from a session), markers.py (agent products' marks on the page and when each was
                         there), verdict_soft.py (when soft traces count)
  behaviour              behavior.py (whether the model runs), model.py and timeline.py (the model), features.py,
                         segment.py and rrweb_events.py (its input)
attribute.py names the agent; crawler.py and weak.py add the reasons that never change a verdict; verdict_text.py
words every reason. schedule.py says when a session is judged; agentcake/judging.py does it and agentcake/evidence.py
reads its evidence from the database. Nothing in this package reads the database, and only lists_build.py goes online
(when a release is built, when `agentcake lists update` runs, and once a month in the process `agentcake serve`
starts for the update, agentcake/updates.py; never in the process that judges).
"""
