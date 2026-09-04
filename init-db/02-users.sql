CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    session_uuid VARCHAR(64) DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO usuarios (username, password_hash, role)
VALUES ('admin', '$2b$12$GlP4XrgEDxbfV8QLk44BtePNYhVzkwYTDmmDTbUsKX.fBf4pXmB82', 'admin')
ON CONFLICT (username) DO NOTHING;
