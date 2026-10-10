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

CREATE TABLE IF NOT EXISTS settings (
    group_name TEXT NOT NULL,
    name       TEXT NOT NULL,
    value      TEXT,
    PRIMARY KEY (group_name, name)
);

CREATE INDEX IF NOT EXISTS idx_request_actor_time ON request(actor_id, start_utc);
CREATE INDEX IF NOT EXISTS idx_request_host_time ON request(host_id, start_utc);
CREATE INDEX IF NOT EXISTS idx_request_time ON request(start_utc);
CREATE INDEX IF NOT EXISTS idx_request_status ON request(downstream_status);
CREATE INDEX IF NOT EXISTS idx_burst_actor_host_start ON burst(actor_id, host_id, start_time);
CREATE INDEX IF NOT EXISTS idx_burst_start_end ON burst(start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_request_category_category ON request_category(category_id, request_id);
CREATE INDEX IF NOT EXISTS idx_burst_category_category ON burst_category(category_id, burst_id);
