-- Run this once against your new Supabase Postgres database
-- (Supabase dashboard -> SQL Editor -> paste -> Run).

CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    phone         TEXT,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE watches (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- what to watch (same shape the railway API itself expects)
    from_city        TEXT NOT NULL,
    to_city          TEXT NOT NULL,
    date_of_journey  DATE NOT NULL,
    train_model      TEXT NOT NULL,        -- e.g. "721"
    train_label      TEXT NOT NULL,        -- e.g. "Mohanagar Express (721)"
    seat_classes     TEXT[] NOT NULL DEFAULT '{}',  -- empty = "any class"
    seat_class_param TEXT NOT NULL DEFAULT 'S_CHAIR',  -- required search param

    -- how many tickets they're after
    tickets_needed   INTEGER NOT NULL DEFAULT 1,
    tickets_acquired INTEGER NOT NULL DEFAULT 0,

    -- billing + lifecycle
    is_paid          BOOLEAN NOT NULL DEFAULT false,
    status           TEXT NOT NULL DEFAULT 'pending_payment',
        -- pending_payment | active | reminder | done | stopped

    -- worker bookkeeping
    action_token     TEXT NOT NULL,         -- random per-watch secret for email action links
    last_counts      JSONB NOT NULL DEFAULT '{}',  -- per-class online counts as of last poll
    last_pinged_at   TIMESTAMPTZ,

    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_watches_active ON watches (status, is_paid);

CREATE TABLE ping_log (
    id           SERIAL PRIMARY KEY,
    watch_id     INTEGER NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
    seat_class   TEXT NOT NULL,
    seats_online INTEGER NOT NULL,
    fare         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- single-row table just for the "token expired" notify-once flag,
-- equivalent to what state.json used to track
CREATE TABLE worker_state (
    id                      INTEGER PRIMARY KEY DEFAULT 1,
    token_expired_notified  BOOLEAN NOT NULL DEFAULT false,
    CHECK (id = 1)
);
INSERT INTO worker_state (id) VALUES (1);
