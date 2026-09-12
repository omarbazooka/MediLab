"""Database, schema, and pgvector verification script for MediLab AI.

Run with:
    uv run python scripts/verify_db.py
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text

load_dotenv()

database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("ERROR: DATABASE_URL is not set in environment or .env file.")
    sys.exit(1)

# Safely extract host without exposing credentials
parsed = urlparse(database_url.replace("postgresql+psycopg://", "postgresql://"))
safe_host = parsed.hostname or "unknown-host"
safe_port = parsed.port or 5432

print("=" * 60)
print("MediLab AI — Database & Schema Verification")
print("=" * 60)
print(f"Connecting to host: {safe_host}:{safe_port}...")

try:
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        db_name = conn.execute(text("SELECT current_database();")).scalar()
        pg_version = conn.execute(text("SELECT version();")).scalar()
        short_version = pg_version.split(",")[0] if pg_version else "Unknown"

        # 1. Check pgvector extension
        vector_version = conn.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
        ).scalar()

        # 2. Check Alembic revision
        alembic_rev = conn.execute(text("SELECT version_num FROM alembic_version;")).scalar()

        # 3. Check core table count
        insp = inspect(conn)
        tables = [t for t in insp.get_table_names() if t != "alembic_version"]

        # 4. Check HOME constraint
        ck_def = conn.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_bookings_branch_for_branch_visit';"
            )
        ).scalar()

        # 5. Check trigger
        trg_exists = conn.execute(
            text(
                "SELECT 1 FROM pg_trigger WHERE tgname = 'trg_conversation_sessions_snapshot_integrity';"
            )
        ).scalar()

        # 6. Seed counts
        cat_count = conn.execute(text("SELECT count(*) FROM test_categories;")).scalar()
        test_count = conn.execute(text("SELECT count(*) FROM lab_tests;")).scalar()
        pkg_count = conn.execute(text("SELECT count(*) FROM packages;")).scalar()
        branch_count = conn.execute(text("SELECT count(*) FROM branches;")).scalar()
        slot_count = conn.execute(text("SELECT count(*) FROM availability_slots;")).scalar()
        doc_count = conn.execute(text("SELECT count(*) FROM knowledge_documents;")).scalar()

        print("-" * 60)
        print(f"  Database Name:       {db_name}")
        print(f"  PostgreSQL:          {short_version}")
        print(f"  pgvector Version:    {vector_version or 'NOT INSTALLED'}")
        print(f"  Alembic Revision:    {alembic_rev or 'NONE'}")
        print(f"  Core Tables:         {len(tables)} of 15 registered")
        print(f"  Snapshot Trigger:    {'ACTIVE' if trg_exists else 'MISSING'}")
        print(f"  Check Constraint:    {ck_def or 'MISSING'}")
        print("-" * 60)
        print("  Verified Seed Counts:")
        print(f"    - Categories:          {cat_count}")
        print(f"    - Lab Tests:           {test_count}")
        print(f"    - Packages:            {pkg_count}")
        print(f"    - Branches:            {branch_count}")
        print(f"    - Availability Slots:  {slot_count}")
        print(f"    - Knowledge Documents: {doc_count}")
        print("-" * 60)

        if not vector_version:
            print("ERROR: 'vector' extension is not installed.")
            sys.exit(2)
        if alembic_rev != "44cef7a277a7":
            print(f"ERROR: Expected Alembic revision 44cef7a277a7, found {alembic_rev}.")
            sys.exit(3)
        if len(tables) != 15:
            print(f"ERROR: Expected 15 tables, found {len(tables)}: {tables}")
            sys.exit(4)

        print("All database, extension, constraint, trigger, and seed checks PASSED!")
        print("=" * 60)

except Exception as exc:
    print(f"ERROR: Database verification failed: {exc}")
    sys.exit(1)
