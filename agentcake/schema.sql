-- Agent Cake's database (SQLite in WAL mode, $CAKE_HOME/cake.db). store.db() runs this on every open: every statement
-- is IF NOT EXISTS (the one INSERT, WHERE NOT EXISTS). A database made by an older cake gets the newer columns from
-- store.ADDED_COLUMNS.
-- Replays are not in here: they are compressed 10-second chunks in $CAKE_HOME/replays/<date>/<hour>.bin, and the
-- chunks table says where each one is (S2.2, replay_chunks.py and streams.py).

-- One row per visit (cake.js's session id): what cake.js reported, and the latest verdict.
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, start_ms INT, end_ms INT, url TEXT, ua TEXT,
    webdriver INT, sec_fetch TEXT, source TEXT, group_id TEXT, verdict TEXT, human_pct INT, agent_pct INT, unsure_pct INT,
    segs TEXT, is_test INT DEFAULT 0,
    origin TEXT DEFAULT 'site',                         -- 0.3.2: site or other (site_origin.py); 'demo' = the demo shop, until D37
    judged_ms INT DEFAULT 0, net TEXT,                  -- 0.3.3: lazy judging, network facts
    replay_freed_ms INT, events_dropped INT DEFAULT 0,  -- 0.3.4: space
    events_refused INT DEFAULT 0,                       -- S2.1: records over the per-session limit
    -- S3.4: the four layers' verdict (judging.py): class, Agent row, name, confidence, reasons and layers (JSON), the
    -- rest of the verdict (JSON: judging, display name, operator, kind, name certainty and method, category,
    -- verification, impersonating). source, group_id, verdict, the *_pct columns and segs are written from it too.
    verdict_class TEXT, agent_row TEXT, agent_name TEXT, confidence TEXT, reasons TEXT, layers TEXT,
    verdict_detail TEXT,
    -- S5.1 (D30): the first and the last recorded action on the events' clock (activity.py), kept with the verdict:
    -- a session's length is the time between them.
    first_action_ms INT, last_action_ms INT,
    -- S3.7: the version of the judge that made the verdict (judging.model_version(): a fingerprint of its code and
    -- data files); a session an older judge judged is judged anew (judging.py).
    model_version TEXT);

-- Small events the dashboard and the timeline count: one row each, body a JSON object with "kind" (pageview, click,
-- mark...). cake 0.3.4's collect wrote each rrweb event here too (a body without "kind"); since S2.1 collect keeps
-- them in chunks, and `agentcake migrate` copies the 0.3.4 rows into chunks and keeps them.
CREATE TABLE IF NOT EXISTS events(session_id TEXT, ts INT, body TEXT);
CREATE INDEX IF NOT EXISTS ev_s ON events(session_id, ts);

-- 0.3.3: the server half of each page, one row per verified token (token id = primary key: accepted once). S4.2: the
-- page view that brought it first (pv); how many other page views of the visit brought it again (reuses: the browser
-- showed them a stored copy of the page, after a 304 or going back); whether the upload request collect saw has the
-- page request's User-Agent, Accept-Language and network (ua_match, lang_match, net_match: 1 the same, 0 different,
-- NULL when either side does not say), a signal for the verdict's reasons.
CREATE TABLE IF NOT EXISTS srv(id TEXT PRIMARY KEY, session_id TEXT, recv_ms INT, page_ms INT, path TEXT,
    body TEXT, net_match INT,
    pv TEXT, ua_match INT, lang_match INT, reuses INT DEFAULT 0);  -- S4.2: reuse and the comparisons
CREATE INDEX IF NOT EXISTS srv_s ON srv(session_id, page_ms);

-- S2.2: where each sealed chunk of a session's stream (rrweb, raw, env) is: file under replays/, byte range, time
-- range, event count, codec and level, raw (uncompressed) size, the stylesheets it refers to (space-separated hashes),
-- and whether the night recompression wrote it (one archived chunk per stream holds a whole session).
CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, stream TEXT NOT NULL,
    t_start INT NOT NULL, t_end INT NOT NULL, n_events INT NOT NULL, file TEXT NOT NULL, byte_offset INT NOT NULL,
    byte_length INT NOT NULL, raw_bytes INT NOT NULL, codec TEXT NOT NULL, level INT NOT NULL, styles TEXT,
    archived INT NOT NULL DEFAULT 0, created_ms INT NOT NULL);
CREATE INDEX IF NOT EXISTS chunks_s ON chunks(session_id, stream, t_start);
CREATE INDEX IF NOT EXISTS chunks_f ON chunks(file);

-- S2.5: running totals the disk budget reads on every collect instead of summing a table (space.py). 'chunk_bytes'
-- is the bytes of all live chunks: SQLite keeps it on every insert, delete and resize of a chunks row, whoever
-- writes it (collect, recompression, reclaim, migrate). A database whose chunks are older than these triggers starts
-- from their sum, once: afterwards the row exists and the INSERT selects nothing.
CREATE TABLE IF NOT EXISTS totals(name TEXT PRIMARY KEY, value INT NOT NULL) WITHOUT ROWID;
CREATE TRIGGER IF NOT EXISTS chunks_bytes_add AFTER INSERT ON chunks BEGIN
    UPDATE totals SET value = value + NEW.byte_length WHERE name = 'chunk_bytes'; END;
CREATE TRIGGER IF NOT EXISTS chunks_bytes_drop AFTER DELETE ON chunks BEGIN
    UPDATE totals SET value = value - OLD.byte_length WHERE name = 'chunk_bytes'; END;
CREATE TRIGGER IF NOT EXISTS chunks_bytes_resize AFTER UPDATE OF byte_length ON chunks BEGIN
    UPDATE totals SET value = value - OLD.byte_length + NEW.byte_length WHERE name = 'chunk_bytes'; END;
INSERT INTO totals(name, value) SELECT 'chunk_bytes', (SELECT COALESCE(SUM(byte_length), 0) FROM chunks)
    WHERE NOT EXISTS (SELECT 1 FROM totals WHERE name = 'chunk_bytes');

-- S2.2: the 10-second windows still being filled, uncompressed (one JSON line per event), until they are sealed.
CREATE TABLE IF NOT EXISTS open_chunks(session_id TEXT NOT NULL, stream TEXT NOT NULL, window_ms INT NOT NULL,
    t_start INT NOT NULL, t_end INT NOT NULL, n_events INT NOT NULL, lines TEXT NOT NULL, updated_ms INT NOT NULL,
    PRIMARY KEY(session_id, stream, window_ms));
CREATE INDEX IF NOT EXISTS open_chunks_u ON open_chunks(updated_ms);

-- S2.2: each stylesheet text rrweb copied into a snapshot, stored once (compressed) and referred to by its hash.
CREATE TABLE IF NOT EXISTS styles(hash TEXT PRIMARY KEY, body BLOB NOT NULL, codec TEXT NOT NULL, raw_bytes INT NOT NULL,
    created_ms INT NOT NULL);

-- Stretches of a session judged human, agent or unsure (judging.py, S3.4 wiring): actor is who the verdict says acted
-- (an Agent's or a Human's decided runs are all theirs), model the behaviour model's own label, share its mean chance
-- that an agent acted, n_actions its actions. sessions.segs keeps 0.3.4's JSON copy for the old pages.
CREATE TABLE IF NOT EXISTS segments(session_id TEXT NOT NULL, t_start INT NOT NULL, t_end INT NOT NULL,
    actor TEXT NOT NULL, share REAL, n_actions INT, model TEXT, reasons TEXT, PRIMARY KEY(session_id, t_start)) WITHOUT ROWID;

-- Who an agent is, one row per candidate name and the layer that found it (S3.4): method, certainty, evidence (JSON).
CREATE TABLE IF NOT EXISTS labels(session_id TEXT NOT NULL, name TEXT NOT NULL, layer TEXT NOT NULL, method TEXT,
    certainty TEXT, evidence TEXT, judged_ms INT, PRIMARY KEY(session_id, name, layer)) WITHOUT ROWID;

-- S2.3: the network facts of each collect request, copies of a batch too (netfacts.request_facts, JSON: the kept
-- header values, header names in order, where it came from; with the load balancer, the address's published range,
-- relay / CDN / cloud class, country and its salted hashes), and the batch it brought (page view, number; NULL for a
-- cake 0.3.4 batch). Results only: never the visitor's address.
CREATE TABLE IF NOT EXISTS requests(session_id TEXT NOT NULL, recv_ms INT NOT NULL, seq INT, facts TEXT NOT NULL,
    pv TEXT);
CREATE INDEX IF NOT EXISTS requests_s ON requests(session_id, recv_ms);

-- S2.1: each batch cake.js sent (upload format v1, docs/collect-format.md), keyed the way the format tells a batch
-- sent twice: visit, page view, batch number. Its header: when cake.js made it (t, epoch ms) and when it arrived, the
-- page's URL then (u: a single-page app changes it), what made it (why), cake.js's own drop counts so far (dr, JSON),
-- its records per stream, and the id of the server-half token it brought (srv.id) when cake verified one.
CREATE TABLE IF NOT EXISTS batches(session_id TEXT NOT NULL, pv TEXT NOT NULL, seq INT NOT NULL, recv_ms INT NOT NULL,
    t REAL, url TEXT, why TEXT, dropped TEXT, n_rrweb INT NOT NULL, n_raw INT NOT NULL, n_env INT NOT NULL,
    token_id TEXT, PRIMARY KEY(session_id, pv, seq)) WITHOUT ROWID;

-- S2.1: what collect refused, by reason (bad_body, too_large, site_key, version, no_session, bad_batch, post_limit,
-- session_limit, bad_record): how many uploads, how many records they held, and when the last one came.
CREATE TABLE IF NOT EXISTS refusals(reason TEXT PRIMARY KEY, posts INT NOT NULL, records INT NOT NULL,
    last_ms INT NOT NULL) WITHOUT ROWID;

-- The database's own state as JSON values: schema version, what `agentcake migrate` did. A person's settings stay
-- in config.json.
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_ms INT NOT NULL) WITHOUT ROWID;
