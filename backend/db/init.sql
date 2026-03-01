-- DengueWatch SG — PostgreSQL schema initialisation
-- Run once on first startup (handled by docker-entrypoint-initdb.d).

-- Planning area risk scores (populated weekly by SageMaker inference)
CREATE TABLE IF NOT EXISTS planning_area_risk (
    id              SERIAL PRIMARY KEY,
    planning_area   VARCHAR(100) NOT NULL,
    risk_level      VARCHAR(10)  NOT NULL CHECK (risk_level IN ('Low', 'Medium', 'High')),
    score           NUMERIC(6, 4) NOT NULL,   -- model output probability 0–1
    week            VARCHAR(8)   NOT NULL,    -- ISO format e.g. "2024-W10"
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (planning_area, week)
);

-- Mapping of postal codes to planning areas (static lookup table)
CREATE TABLE IF NOT EXISTS postal_code_mapping (
    postal_code     CHAR(6)      PRIMARY KEY,
    planning_area   VARCHAR(100) NOT NULL
);

-- Email subscriptions
CREATE TABLE IF NOT EXISTS subscriptions (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(254) NOT NULL UNIQUE,
    postal_codes    TEXT[]       NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Index for notification queries
CREATE INDEX IF NOT EXISTS idx_par_week ON planning_area_risk (week);
CREATE INDEX IF NOT EXISTS idx_pcm_area ON postal_code_mapping (planning_area);
