"""Resolve retired product IDs in previously downloaded list snapshots."""


def canonical_names(names, retired_ids):
    """Move the former entry's User-Agent patterns to the canonical entry when both exist."""
    entries = {entry["id"]: entry for entry in names}
    for retired_id, canonical_id in retired_ids.items():
        retired = entries.get(retired_id)
        canonical = entries.get(canonical_id)
        if retired is None or canonical is None:
            continue
        merged = dict(canonical, patterns=canonical["patterns"] + retired["patterns"],
                      sources=list(dict.fromkeys(canonical["sources"] + retired["sources"])))
        if "evidence" in retired:
            merged.setdefault("evidence", retired["evidence"])
        entries[canonical_id] = merged
        del entries[retired_id]
    return entries
