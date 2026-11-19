-- Tabluo: schema iniziale D1 (SQLite). Il catalogo e le licenze vivono in Git
-- (games/<slug>/manifest.json + license.json); qui solo stato dinamico.

-- Kill switch: un gioco presente qui con status 'suspended' non viene caricato.
CREATE TABLE game_status (
  slug        TEXT PRIMARY KEY,
  status      TEXT NOT NULL CHECK (status IN ('active', 'suspended')),
  reason      TEXT NOT NULL DEFAULT '',
  updated_at  TEXT NOT NULL
);

-- Telemetria aggregata e anonima: nessun identificativo utente.
CREATE TABLE events_daily (
  day            TEXT NOT NULL,           -- YYYY-MM-DD (UTC)
  slug           TEXT NOT NULL,
  version        TEXT NOT NULL,
  sessions       INTEGER NOT NULL DEFAULT 0,
  completions    INTEGER NOT NULL DEFAULT 0,
  wins           INTEGER NOT NULL DEFAULT 0,
  total_seconds  INTEGER NOT NULL DEFAULT 0,
  errors         INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, slug, version)
);

-- Ad server diretto.
CREATE TABLE advertisers (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL,
  contact     TEXT NOT NULL DEFAULT '',
  vat_id      TEXT NOT NULL DEFAULT '',
  created_at  TEXT NOT NULL
);

CREATE TABLE campaigns (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  advertiser_id   INTEGER NOT NULL REFERENCES advertisers(id),
  name            TEXT NOT NULL,
  kind            TEXT NOT NULL CHECK (kind IN ('direct', 'sponsor')),
  status          TEXT NOT NULL CHECK (status IN ('draft', 'active', 'paused', 'ended')),
  start_date      TEXT NOT NULL,
  end_date        TEXT NOT NULL,
  priority        INTEGER NOT NULL DEFAULT 0,
  impression_cap  INTEGER,                 -- NULL = senza limite
  category        TEXT,                    -- targeting contestuale (NULL = tutte)
  payment_status  TEXT NOT NULL DEFAULT 'unpaid' CHECK (payment_status IN ('unpaid', 'invoiced', 'paid')),
  contract_ref    TEXT NOT NULL DEFAULT '',
  created_at      TEXT NOT NULL
);

CREATE TABLE creatives (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign_id  INTEGER NOT NULL REFERENCES campaigns(id),
  placement    TEXT NOT NULL,              -- es. 'home-top', 'game-side'
  image_path   TEXT NOT NULL,              -- immagine statica sul nostro origin
  alt_text     TEXT NOT NULL,
  click_url    TEXT NOT NULL,              -- solo https://
  width        INTEGER NOT NULL,
  height       INTEGER NOT NULL,
  approved     INTEGER NOT NULL DEFAULT 0 CHECK (approved IN (0, 1))
);
CREATE INDEX creatives_placement ON creatives(placement);

CREATE TABLE ad_daily_stats (
  day          TEXT NOT NULL,
  creative_id  INTEGER NOT NULL,
  placement    TEXT NOT NULL,
  source       TEXT NOT NULL CHECK (source IN ('direct', 'sponsor', 'network')),
  impressions  INTEGER NOT NULL DEFAULT 0,
  clicks       INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, creative_id, placement, source)
);

CREATE TABLE audit_log (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  at       TEXT NOT NULL,
  actor    TEXT NOT NULL,
  action   TEXT NOT NULL,
  entity   TEXT NOT NULL,
  detail   TEXT NOT NULL DEFAULT ''
);
