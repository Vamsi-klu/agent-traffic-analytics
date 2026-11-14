"""Reading back what cake.js uploaded to the stand-in collector (plan steps S1.3, S1.4).

collect.ndjson has one line per upload as it arrived; a batch can arrive twice (docs/collect-format.md: a copy parked
in sessionStorage is sent again), so batches are told apart by (s, pv, seq), as cake's collector does. A page view is
everything one page load sent; a visit is everything one browser tab sent under one visit id.
"""
import json
import os

RRWEB_FULL_SNAPSHOT = 2  # rrweb EventType
RRWEB_META = 4
RRWEB_INCREMENTAL = 3
RRWEB_MOUSE_INTERACTION = 2  # IncrementalSource
RRWEB_CLICK = 2  # MouseInteractions


def read_ndjson(path):
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load(out_dir):
    """Every upload, as the collector logged it: {"at", "gz", "wire_bytes", "cookie", "content_type", "batch"}."""
    return read_ndjson(os.path.join(out_dir, "collect.ndjson"))


def unique(entries):
    """Batches without repeats, first arrival kept."""
    seen, batches = set(), []
    for entry in entries:
        batch = entry["batch"]
        key = (batch["s"], batch["pv"], batch["seq"])
        if key not in seen:
            seen.add(key)
            batches.append(batch)
    return batches


def page_views(batches):
    """{pv: {"s", "pv", "seqs", "urls", "e", "r", "x", "page", "tokens"}} in arrival order of the records."""
    views = {}
    for batch in sorted(batches, key=lambda b: (b["pv"], b["seq"])):
        view = views.setdefault(batch["pv"], {"s": batch["s"], "pv": batch["pv"], "seqs": [], "urls": [], "e": [],
                                              "r": [], "x": [], "page": None, "tokens": set()})
        view["seqs"].append(batch["seq"])
        view["urls"].append(batch["u"])
        if batch.get("st"):
            view["tokens"].add(batch["st"])
        for stream in ("e", "r", "x"):
            view[stream].extend(batch[stream])
        for record in batch["x"]:
            if record.get("ty") == "page" and view["page"] is None:
                view["page"] = record
    return views


def visits(views):
    """{s: [page views in the order the pages opened]}; page views whose page record never arrived come last."""
    grouped = {}
    for view in views.values():
        grouped.setdefault(view["s"], []).append(view)
    for s in grouped:
        grouped[s].sort(key=lambda v: v["page"]["n"] if v["page"] else float("inf"))
    return grouped


def visit_in(grouped, started_ms, ended_ms):
    """The visit whose first page opened between started_ms and ended_ms (one test run = one visit)."""
    found = [s for s, views in grouped.items()
             if views[0]["page"] and started_ms <= views[0]["page"]["t"] <= ended_ms]
    return grouped[found[0]] if len(found) == 1 else None


def records(view, stream, kind):
    return [r for r in view[stream] if r.get("ty") == kind]


def full_snapshots(view):
    return [e for e in view["e"] if e.get("type") == RRWEB_FULL_SNAPSHOT]


def replay_clicks(view):
    return [e for e in view["e"] if e.get("type") == RRWEB_INCREMENTAL
            and e["data"].get("source") == RRWEB_MOUSE_INTERACTION and e["data"].get("type") == RRWEB_CLICK]


def path_of(url, base):
    return url[len(base):] if url.startswith(base) else url
