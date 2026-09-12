"""Database and pgvector verification script for MediLab AI.

Run with:
    uv run python scripts/verify_db.py
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("ERROR: DATABASE_URL is not set in environment or .env file.")
    sys.exit(1)

print("Connecting to database...")
try:
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        db_name = conn.execute(text("SELECT current_database();")).scalar()
        pg_version = conn.execute(text("SELECT version();")).scalar()
        short_version = pg_version.split(",")[0] if pg_version else "Unknown"

        # Check pgvector extension
        vector_version = conn.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
        ).scalar()

        print("-" * 50)
        print(f"  Database Name:     {db_name}")
        print(f"  PostgreSQL:        {short_version}")
        print(f"  pgvector Version:  {vector_version or 'NOT INSTALLED'}")
        print("  Connection Status: OK")
        print("-" * 50)

        if not vector_version:
            print("WARNING: 'vector' extension is not installed.")
            print("Run 'CREATE EXTENSION IF NOT EXISTS vector;' in PostgreSQL.")
            sys.exit(2)
        else:
            print("All database checks passed successfully!")

except Exception as exc:
    print(f"ERROR: Failed to connect to database: {exc}")
    sys.exit(1)
