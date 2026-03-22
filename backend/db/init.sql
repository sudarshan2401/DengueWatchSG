CREATE TABLE IF NOT EXISTS planning_area_risk (
    id            SERIAL PRIMARY KEY,
    planning_area VARCHAR(100)  NOT NULL,
    risk_level    VARCHAR(10)   NOT NULL CHECK (risk_level IN ('Low', 'Medium', 'High')),
    score         NUMERIC(6, 4) NOT NULL, -- Format: 50.1234 (0.0000 to 100.0000), likelihood of dengue outbreak in percentage
    week          VARCHAR(8)    NOT NULL, -- Format: e.g., "2025-W01", "2025-W02", etc.
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    UNIQUE (planning_area, week)
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id             SERIAL PRIMARY KEY,
    email          VARCHAR(254) NOT NULL UNIQUE,
    planning_areas TEXT[]       NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_par_week ON planning_area_risk (week);