-- Securelytics database schema (runs automatically on first Postgres start)

CREATE TABLE IF NOT EXISTS transactions (
    trans_id      TEXT PRIMARY KEY,
    event_ts      TIMESTAMPTZ NOT NULL,       -- when the payment happened
    card_ref      TEXT NOT NULL,              -- pseudonymous card id (sha256 prefix)
    card_last4    TEXT NOT NULL,
    merchant      TEXT NOT NULL,
    category      TEXT NOT NULL,
    amt           NUMERIC(12, 2) NOT NULL,
    model_name    TEXT NOT NULL,              -- model that made the decision (admin-selected)
    score         REAL NOT NULL,
    decision      TEXT NOT NULL CHECK (decision IN ('APPROVE', 'REVIEW', 'BLOCK')),
    shadow_scores JSONB,                      -- {"hist_gb": 0.01, "xgboost": 0.02, ...} every model on this txn
    is_fraud      SMALLINT,                   -- ground-truth label when available (simulation only)
    scoring_ms    REAL,                       -- time inside the scorer
    e2e_ms        REAL,                       -- producer send -> decision
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_txn_processed_at ON transactions (processed_at);
CREATE INDEX IF NOT EXISTS ix_txn_decision ON transactions (decision);
CREATE INDEX IF NOT EXISTS ix_txn_model ON transactions (model_name);

CREATE TABLE IF NOT EXISTS alerts (
    trans_id      TEXT PRIMARY KEY REFERENCES transactions (trans_id),
    event_ts      TIMESTAMPTZ NOT NULL,
    card_ref      TEXT NOT NULL,
    card_last4    TEXT NOT NULL,
    merchant      TEXT NOT NULL,
    category      TEXT NOT NULL,
    amt           NUMERIC(12, 2) NOT NULL,
    model_name    TEXT NOT NULL,
    score         REAL NOT NULL,
    decision      TEXT NOT NULL,
    reasons       JSONB NOT NULL DEFAULT '[]',
    features      JSONB,
    is_fraud      SMALLINT,
    analyst_label SMALLINT,                   -- feedback loop: 1 fraud, 0 legitimate
    reviewed_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_alerts_created_at ON alerts (created_at);

CREATE TABLE IF NOT EXISTS dead_letters (
    id           BIGSERIAL PRIMARY KEY,
    payload      TEXT NOT NULL,
    error        TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Audit log of admin model switches
CREATE TABLE IF NOT EXISTS model_switches (
    id           BIGSERIAL PRIMARY KEY,
    from_model   TEXT,
    to_model     TEXT NOT NULL,
    switched_by  TEXT NOT NULL,
    note         TEXT,
    switched_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
