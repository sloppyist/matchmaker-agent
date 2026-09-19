-- PostgreSQL setup script for Matchmaker Agent
-- Run this as a superuser to create the database and user

-- Create user (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'matchmaker') THEN
        CREATE USER matchmaker WITH PASSWORD 'matchmaker';
    END IF;
END
$$;

-- Create database
SELECT 'CREATE DATABASE matchmaker_db OWNER matchmaker'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'matchmaker_db')\gexec

-- Connect to the database and set up extensions
\c matchmaker_db

-- Enable vector extension (requires pgvector to be installed)
CREATE EXTENSION IF NOT EXISTS vector;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE matchmaker_db TO matchmaker;
GRANT ALL ON SCHEMA public TO matchmaker;

-- Solutions table for RAG (multi-chain support)
CREATE TABLE IF NOT EXISTS solutions (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT,
    tags TEXT[],
    chains TEXT[] DEFAULT ARRAY[]::TEXT[],  -- e.g., ['solana', 'ethereum']
    url TEXT,
    embedding vector(384),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- HNSW index for fast similarity search
CREATE INDEX IF NOT EXISTS solutions_embedding_idx
ON solutions USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS solutions_category_idx ON solutions (category);
CREATE INDEX IF NOT EXISTS solutions_tags_idx ON solutions USING gin(tags);
CREATE INDEX IF NOT EXISTS solutions_chains_idx ON solutions USING gin(chains);

-- Sessions table for conversation persistence
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    user_id TEXT NOT NULL,
    state JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS sessions_platform_user_idx ON sessions (platform, user_id);

-- Proposals table for storing generated documents
CREATE TABLE IF NOT EXISTS proposals (
    id SERIAL PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id),
    problem_statement TEXT,
    design_proposal TEXT,
    final_rfs TEXT,
    status TEXT DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS proposals_session_idx ON proposals (session_id);
CREATE INDEX IF NOT EXISTS proposals_status_idx ON proposals (status);

-- Grant table permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO matchmaker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO matchmaker;

-- Done
SELECT 'Database setup complete!' as status;
