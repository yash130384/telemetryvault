-- 001_initial_schema.sql: Core schema for TelemetryVault

CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(64) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
    id BIGSERIAL PRIMARY KEY,
    track VARCHAR(64) NOT NULL DEFAULT 'unknown',
    car VARCHAR(64) NOT NULL DEFAULT 'unknown',
    driver VARCHAR(64) NOT NULL DEFAULT 'unknown',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    frame_count INT NOT NULL DEFAULT 0,
    duration_seconds FLOAT NOT NULL DEFAULT 0.0,
    total_laps INT NOT NULL DEFAULT 0,
    best_lap_time_ms INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_track_started ON sessions(track, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_is_active ON sessions(is_active);

CREATE TABLE IF NOT EXISTS laps (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    lap_number INT NOT NULL,
    lap_time_ms INT,
    is_valid BOOLEAN NOT NULL DEFAULT TRUE,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    sector1_ms INT,
    sector2_ms INT,
    sector3_ms INT,
    max_speed FLOAT DEFAULT 0.0,
    avg_speed FLOAT DEFAULT 0.0,
    frame_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(session_id, lap_number)
);

CREATE INDEX IF NOT EXISTS idx_laps_session_lap ON laps(session_id, lap_number);

CREATE TABLE IF NOT EXISTS telemetry_frames (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    lap_number INT NOT NULL DEFAULT 0,
    timestamp TIMESTAMPTZ NOT NULL,
    session_time FLOAT DEFAULT 0.0,
    lap_time_ms INT DEFAULT 0,
    track_pos FLOAT DEFAULT 0.0,
    speed FLOAT NOT NULL DEFAULT 0.0,
    rpm INT NOT NULL DEFAULT 0,
    max_rpm INT DEFAULT 8500,
    gear INT NOT NULL DEFAULT 0,
    throttle FLOAT NOT NULL DEFAULT 0.0,
    brake FLOAT NOT NULL DEFAULT 0.0,
    clutch FLOAT DEFAULT 0.0,
    steer FLOAT NOT NULL DEFAULT 0.0,
    coord_x FLOAT DEFAULT 0.0,
    coord_y FLOAT DEFAULT 0.0,
    coord_z FLOAT DEFAULT 0.0,
    yaw_rate FLOAT DEFAULT 0.0,
    g_force_lat FLOAT DEFAULT 0.0,
    g_force_lon FLOAT DEFAULT 0.0,
    tyre_press_fl FLOAT DEFAULT 0.0,
    tyre_press_fr FLOAT DEFAULT 0.0,
    tyre_press_rl FLOAT DEFAULT 0.0,
    tyre_press_rr FLOAT DEFAULT 0.0,
    tyre_temp_fl FLOAT DEFAULT 0.0,
    tyre_temp_fr FLOAT DEFAULT 0.0,
    tyre_temp_rl FLOAT DEFAULT 0.0,
    tyre_temp_rr FLOAT DEFAULT 0.0,
    brake_temp_fl FLOAT DEFAULT 0.0,
    brake_temp_fr FLOAT DEFAULT 0.0,
    brake_temp_rl FLOAT DEFAULT 0.0,
    brake_temp_rr FLOAT DEFAULT 0.0,
    fuel FLOAT DEFAULT 0.0,
    raw_data JSONB
);

CREATE INDEX IF NOT EXISTS idx_telemetry_frames_session_time ON telemetry_frames(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_telemetry_frames_session_lap_pos ON telemetry_frames(session_id, lap_number, track_pos);
CREATE INDEX IF NOT EXISTS idx_telemetry_frames_session_id ON telemetry_frames(session_id);
