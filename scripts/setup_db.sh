#!/bin/bash
# Database setup script for Matchmaker Agent

set -e

echo "Setting up Matchmaker Agent database..."

# Check if psql is available
if ! command -v psql &> /dev/null; then
    echo "Error: psql is not installed. Please install PostgreSQL client."
    exit 1
fi

# Default connection parameters
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="matchmaker_db"
APP_USER="matchmaker"
APP_PASSWORD="${APP_PASSWORD:-matchmaker}"

# Create user and database
echo "Creating database user and database..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" <<EOF
-- Create user if not exists
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$APP_USER') THEN
        CREATE USER $APP_USER WITH PASSWORD '$APP_PASSWORD';
    END IF;
END
\$\$;

-- Create database if not exists
SELECT 'CREATE DATABASE $DB_NAME OWNER $APP_USER'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\gexec
EOF

# Connect to the new database and set up extensions
echo "Setting up pgvector extension and schema..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" <<EOF
-- Enable vector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $APP_USER;
GRANT ALL ON SCHEMA public TO $APP_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $APP_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $APP_USER;
EOF

echo "Database setup complete!"
echo ""
echo "Connection string: postgresql://$APP_USER:$APP_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"
echo ""
echo "Next steps:"
echo "  1. Copy .env.example to .env and update DATABASE_URL"
echo "  2. Run: matchmaker setup-db"
echo "  3. Run: matchmaker seed (optional - adds sample solutions)"
