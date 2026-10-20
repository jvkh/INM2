-- Initial schema for Internet Noise Monitor (SQLite).
-- Enable foreign key enforcement on every connection with PRAGMA foreign_keys = ON.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS actor (
    actor_id    INTEGER PRIMARY KEY,
    ip          TEXT NOT NULL UNIQUE,
    first_time  TEXT NOT NULL,
    last_time   TEXT NOT NULL,
    provider    TEXT,
    asn         TEXT,
    city        TEXT,
    country     TEXT
);

CREATE TABLE IF NOT EXISTS host (
    host_id INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE,
    known   INTEGER NOT NULL DEFAULT 0 CHECK (known IN (0, 1))
);

-- Configured hostnames that belong to this installation (case-insensitive).
CREATE TABLE IF NOT EXISTS known_host (
    name TEXT PRIMARY KEY COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS request (
    request_id              INTEGER PRIMARY KEY,
    actor_id                INTEGER NOT NULL REFERENCES actor(actor_id) ON DELETE CASCADE,
    host_id                 INTEGER REFERENCES host(host_id) ON DELETE SET NULL,
    client_addr             TEXT,
    duration                INTEGER,
    downstream_status       INTEGER,
    downstream_content_size INTEGER,
    request_addr            TEXT,
    request_host            TEXT,
    request_method          TEXT,
    request_path            TEXT,
    request_scheme          TEXT,
    start_utc               TEXT NOT NULL,
    user_agent              TEXT
);

CREATE TABLE IF NOT EXISTS category (
    category_id   INTEGER PRIMARY KEY,
    category_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS request_category (
    request_id  INTEGER NOT NULL REFERENCES request(request_id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES category(category_id) ON DELETE CASCADE,
    PRIMARY KEY (request_id, category_id)
);

CREATE TABLE IF NOT EXISTS burst (
    burst_id    INTEGER PRIMARY KEY,
    actor_id    INTEGER NOT NULL REFERENCES actor(actor_id) ON DELETE CASCADE,
    host_id     INTEGER REFERENCES host(host_id) ON DELETE SET NULL,
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL,
    avg_count   REAL NOT NULL DEFAULT 0,
    read_count  INTEGER NOT NULL DEFAULT 0,
    write_count INTEGER NOT NULL DEFAULT 0,
    other_count INTEGER NOT NULL DEFAULT 0,
    CHECK (end_time >= start_time)
);

CREATE TABLE IF NOT EXISTS burst_category (
    burst_id    INTEGER NOT NULL REFERENCES burst(burst_id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES category(category_id) ON DELETE CASCADE,
    request_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (burst_id, category_id)
);

-- A request can be assigned to at most one burst.
CREATE TABLE IF NOT EXISTS burst_request (
    request_id INTEGER PRIMARY KEY REFERENCES request(request_id) ON DELETE CASCADE,
    burst_id   INTEGER NOT NULL REFERENCES burst(burst_id) ON DELETE CASCADE
);

-- Durable findings from all incident detectors, grouped by type, source, and host.
CREATE TABLE IF NOT EXISTS incident (
    incident_id          INTEGER PRIMARY KEY,
    incident_type        TEXT NOT NULL DEFAULT 'path_scan',
    actor_id             INTEGER NOT NULL REFERENCES actor(actor_id) ON DELETE CASCADE,
    host_id              INTEGER REFERENCES host(host_id) ON DELETE SET NULL,
    first_seen           TEXT NOT NULL,
    last_seen            TEXT NOT NULL,
    request_count        INTEGER NOT NULL,
    indicator_count      INTEGER NOT NULL DEFAULT 0,
    indicators           TEXT NOT NULL DEFAULT '[]',
    summary              TEXT NOT NULL DEFAULT '{}',
    state                TEXT NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'acknowledged', 'resolved'))
);

CREATE TABLE IF NOT EXISTS incident_request (
    incident_id INTEGER NOT NULL REFERENCES incident(incident_id) ON DELETE CASCADE,
    request_id  INTEGER NOT NULL REFERENCES request(request_id) ON DELETE CASCADE,
    PRIMARY KEY (incident_id, request_id)
);

-- One incident may satisfy more than one detector criterion.
CREATE TABLE IF NOT EXISTS incident_criterion (
    incident_id   INTEGER NOT NULL REFERENCES incident(incident_id) ON DELETE CASCADE,
    incident_type TEXT NOT NULL,
    PRIMARY KEY (incident_id, incident_type)
);
INSERT OR IGNORE INTO incident_criterion (incident_id, incident_type)
SELECT incident_id, incident_type FROM incident;

CREATE TABLE IF NOT EXISTS settings (
    group_name TEXT NOT NULL,
    name       TEXT NOT NULL,
    value      TEXT,
    PRIMARY KEY (group_name, name)
);

-- Honeypot events are separate from imported proxy requests so their captured
-- POST bodies can be inspected without changing traffic or burst totals.
CREATE TABLE IF NOT EXISTS honeypot_event (
    event_id       TEXT PRIMARY KEY,
    time           TEXT NOT NULL,
    client_ip      TEXT,
    provider       TEXT,
    asn            TEXT,
    country        TEXT,
    city           TEXT,
    host           TEXT,
    scheme         TEXT,
    session_id     TEXT,
    session_phase  TEXT,
    method         TEXT NOT NULL,
    path           TEXT NOT NULL,
    user_agent     TEXT,
    content_type   TEXT,
    body_bytes     INTEGER NOT NULL DEFAULT 0,
    body_clipped   INTEGER NOT NULL DEFAULT 0 CHECK (body_clipped IN (0, 1)),
    body_sha256    TEXT,
    rule           TEXT,
    status         INTEGER,
    duration       INTEGER NOT NULL DEFAULT 0,
    body_text      TEXT,
    body_base64    TEXT,
    body_file      TEXT
);

CREATE INDEX IF NOT EXISTS idx_request_actor_time ON request(actor_id, start_utc);
CREATE INDEX IF NOT EXISTS idx_request_host_time ON request(host_id, start_utc);
CREATE INDEX IF NOT EXISTS idx_request_time ON request(start_utc);
CREATE INDEX IF NOT EXISTS idx_honeypot_event_time ON honeypot_event(time DESC);
CREATE INDEX IF NOT EXISTS idx_honeypot_event_ip_time ON honeypot_event(client_ip, time DESC);
CREATE INDEX IF NOT EXISTS idx_honeypot_event_method_time ON honeypot_event(method, time DESC);
CREATE INDEX IF NOT EXISTS idx_request_status ON request(downstream_status);
-- Burst reconstruction groups requests by actor and host inside a time range.
CREATE INDEX IF NOT EXISTS idx_request_actor_host_time ON request(actor_id, host_id, start_utc);
-- Maintenance removes actors by last activity; new-actor views filter by first activity.
CREATE INDEX IF NOT EXISTS idx_actor_last_time ON actor(last_time);
CREATE INDEX IF NOT EXISTS idx_actor_first_time ON actor(first_time);
CREATE INDEX IF NOT EXISTS idx_burst_actor_host_start ON burst(actor_id, host_id, start_time);
CREATE INDEX IF NOT EXISTS idx_burst_start_end ON burst(start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_request_category_category ON request_category(category_id, request_id);
CREATE INDEX IF NOT EXISTS idx_burst_category_category ON burst_category(category_id, burst_id);
CREATE INDEX IF NOT EXISTS idx_burst_request_burst ON burst_request(burst_id, request_id);
CREATE INDEX IF NOT EXISTS idx_incident_actor_host_type_last ON incident(actor_id, host_id, incident_type, last_seen);
CREATE INDEX IF NOT EXISTS idx_incident_actor_time ON incident(actor_id, first_seen, last_seen);
CREATE INDEX IF NOT EXISTS idx_incident_criterion_type ON incident_criterion(incident_type, incident_id);
CREATE INDEX IF NOT EXISTS idx_incident_state_last ON incident(state, last_seen);
CREATE INDEX IF NOT EXISTS idx_incident_last_seen ON incident(last_seen DESC, incident_id DESC);
CREATE INDEX IF NOT EXISTS idx_incident_first_seen ON incident(first_seen, incident_id);
CREATE INDEX IF NOT EXISTS idx_incident_type_last ON incident(incident_type, last_seen DESC, incident_id DESC);
CREATE INDEX IF NOT EXISTS idx_incident_request_request ON incident_request(request_id, incident_id);
