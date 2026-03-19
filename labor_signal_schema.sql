CREATE TABLE IF NOT EXISTS labor_signal_master (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    region_code TEXT NOT NULL,
    region_name TEXT NOT NULL,
    dataset_name TEXT NOT NULL,
    metric_group TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    entity_code TEXT,
    metric_value REAL NOT NULL,
    metric_unit TEXT NOT NULL,
    time_period_label TEXT NOT NULL,
    time_period_start TEXT,
    time_period_end TEXT,
    seasonality TEXT,
    notes TEXT,
    created_at INTEGER DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS labor_region_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    region_code TEXT NOT NULL,
    region_name TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    unemployment_rate REAL,
    top_industries_json TEXT,
    top_occupations_json TEXT,
    summary_signal_score REAL DEFAULT 0,
    created_at INTEGER DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS role_opportunity_score (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    region_code TEXT NOT NULL,
    role_name TEXT NOT NULL,
    demand_score REAL NOT NULL,
    wage_score REAL NOT NULL,
    growth_score REAL NOT NULL,
    employment_volume_score REAL NOT NULL,
    transferability_score REAL NOT NULL,
    entry_friction_score REAL NOT NULL,
    overall_opportunity_score REAL NOT NULL,
    recommended_for_fast_entry INTEGER DEFAULT 0,
    recommended_for_upskill INTEGER DEFAULT 0,
    recommended_for_pivot INTEGER DEFAULT 0,
    created_at INTEGER DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS user_skill_gap_report (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    target_role TEXT NOT NULL,
    region_code TEXT NOT NULL,
    current_match_score REAL NOT NULL,
    missing_skills_json TEXT,
    missing_certifications_json TEXT,
    training_priority_json TEXT,
    estimated_readiness_days INTEGER NOT NULL,
    recommended_path TEXT NOT NULL,
    created_at INTEGER DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS market_route_decision (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    region_code TEXT NOT NULL,
    recommended_route TEXT NOT NULL,
    primary_role_target TEXT NOT NULL,
    secondary_role_target TEXT,
    reason_codes_json TEXT,
    confidence_score REAL NOT NULL,
    created_at INTEGER DEFAULT (strftime('%s','now'))
);
