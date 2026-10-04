#!/usr/bin/env python3
"""
Migration script to add base_schedule, schedule_overlays, and schedule_versions tables
to existing shift_scheduler.db database.

Run this script after updating the codebase to migrate existing data.
"""

import sqlite3
from pathlib import Path
from datetime import date

DB_PATH = Path(__file__).parent.parent / "data" / "shift_scheduler.db"

MIGRATION_SQL = """
-- Base schedule: immutable rotation pattern for 18 months
CREATE TABLE IF NOT EXISTS base_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_date TEXT NOT NULL,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    shift_type INTEGER NOT NULL CHECK (shift_type IN (0, 1, 2, 3)),
    cycle_start_date TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(schedule_date, team_id, version)
);

-- Dynamic overlays: substitutions, swaps, exceptions applied on top of base
CREATE TABLE IF NOT EXISTS schedule_overlays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    base_schedule_id INTEGER NOT NULL REFERENCES base_schedule(id) ON DELETE CASCADE,
    overlay_type TEXT NOT NULL CHECK (overlay_type IN ('substitution', 'swap', 'exception', 'manual')),
    person_id INTEGER REFERENCES persons(id) ON DELETE SET NULL,
    original_person_id INTEGER REFERENCES persons(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'cancelled', 'expired')),
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT
);

-- Schedule version tracking for model changes
CREATE TABLE IF NOT EXISTS schedule_versions (
    version INTEGER PRIMARY KEY,
    shift_model TEXT NOT NULL CHECK (shift_model IN ('2-shift', '3-shift')),
    cycle_start_date TEXT NOT NULL,
    team_count INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    is_active INTEGER DEFAULT 1
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_base_schedule_date_team ON base_schedule(schedule_date, team_id, version);
CREATE INDEX IF NOT EXISTS idx_overlays_base_schedule ON schedule_overlays(base_schedule_id, status);
CREATE INDEX IF NOT EXISTS idx_overlays_person_date ON schedule_overlays(person_id, status);
"""


def migrate():
    """Run the migration."""
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        print(
            "Run the application first to create the database, then run this migration."
        )
        return False

    print(f"Migrating database at {DB_PATH}...")

    conn = sqlite3.connect(DB_PATH)
    try:
        # Check current schema version
        cursor = conn.execute("PRAGMA user_version")
        current_version = cursor.fetchone()[0]
        print(f"Current schema version: {current_version}")

        # Run migration
        conn.executescript(MIGRATION_SQL)

        # Update schema version
        conn.execute("PRAGMA user_version = 2")
        conn.commit()

        print("Migration completed successfully!")

        # Verify new tables
        cursor = conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name IN ('base_schedule', 'schedule_overlays', 'schedule_versions')
        """)
        tables = [row[0] for row in cursor.fetchall()]
        print(f"New tables created: {tables}")

        return True

    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    success = migrate()
    exit(0 if success else 1)
