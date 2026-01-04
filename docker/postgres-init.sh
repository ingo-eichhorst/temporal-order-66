#!/bin/bash
set -e

# This script creates multiple databases in a single PostgreSQL instance
# It runs automatically when the container starts for the first time

echo "Creating databases: temporal and langfuse"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create temporal database
    CREATE DATABASE temporal;
    GRANT ALL PRIVILEGES ON DATABASE temporal TO postgres;

    -- Create langfuse database
    CREATE DATABASE langfuse;
    GRANT ALL PRIVILEGES ON DATABASE langfuse TO postgres;
EOSQL

echo "Databases created successfully"
