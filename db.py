"""
Shift Scheduler Database Module
SQLite backend for team shift scheduling with squads, availability, and assignments.
"""

import sqlite3
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional


DB_PATH = Path(__file__).parent.parent / "data" / "shift_scheduler.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -64000;
PRAGMA temp_store = MEMORY;
PRAGMA mmap_size = 268435456;

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#2563eb',
    initial_shift_offset INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    role TEXT DEFAULT 'operator',
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(name, team_id)
);

CREATE TABLE IF NOT EXISTS availability_exceptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    reason TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS shift_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_date TEXT NOT NULL,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    shift INTEGER NOT NULL CHECK (shift IN (1, 2)),
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    is_substitute INTEGER DEFAULT 0,
    substitute_for_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(schedule_date, team_id, shift, person_id)
);

CREATE TABLE IF NOT EXISTS shift_swaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_date TEXT NOT NULL,
    person_a_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    person_b_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    shift_a INTEGER NOT NULL CHECK (shift_a IN (1, 2)),
    shift_b INTEGER NOT NULL CHECK (shift_b IN (1, 2)),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS schedule_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_assignments_date ON shift_assignments(schedule_date);
CREATE INDEX IF NOT EXISTS idx_assignments_team_shift ON shift_assignments(team_id, shift);
CREATE INDEX IF NOT EXISTS idx_availability_person_date ON availability_exceptions(person_id, start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_swaps_date ON shift_swaps(schedule_date);
"""


def get_conn() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize the database schema."""
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        _run_migrations(conn)
        conn.commit()
    finally:
        conn.close()


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Run idempotent schema migrations."""
    cur = conn.execute("PRAGMA table_info(people)")
    columns = {row["name"] for row in cur.fetchall()}
    
    # Add columns if missing
    if "role" not in columns:
        conn.execute("ALTER TABLE people ADD COLUMN role TEXT DEFAULT 'operator'")
    if "active" not in columns:
        conn.execute("ALTER TABLE people ADD COLUMN active INTEGER DEFAULT 1")
    
    # Check teams table for initial_shift_offset
    cur = conn.execute("PRAGMA table_info(teams)")
    team_columns = {row["name"] for row in cur.fetchall()}
    if "initial_shift_offset" not in team_columns:
        conn.execute("ALTER TABLE teams ADD COLUMN initial_shift_offset INTEGER DEFAULT 0")


def get_teams() -> list[sqlite3.Row]:
    """Get all teams."""
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM teams ORDER BY id").fetchall()
    finally:
        conn.close()


def get_team(team_id: int) -> Optional[sqlite3.Row]:
    """Get a single team by ID."""
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    finally:
        conn.close()


def create_team(name: str, color: str = '#2563eb', initial_shift_offset: int = 0) -> int:
    """Create a new team."""
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO teams (name, color, initial_shift_offset) VALUES (?, ?, ?)",
            (name, color, initial_shift_offset)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_team(team_id: int, name: str, color: str, initial_shift_offset: int = 0) -> None:
    """Update a team."""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE teams SET name = ?, color = ?, initial_shift_offset = ? WHERE id = ?",
            (name, color, initial_shift_offset, team_id)
        )
        conn.commit()
    finally:
        conn.close()


def delete_team(team_id: int) -> None:
    """Delete a team."""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))
        conn.commit()
    finally:
        conn.close()


def get_people(team_id: Optional[int] = None, active_only: bool = True) -> list[sqlite3.Row]:
    """Get all people, optionally filtered by team."""
    conn = get_conn()
    try:
        if team_id is not None:
            if active_only:
                return conn.execute(
                    "SELECT * FROM people WHERE team_id = ? AND active = 1 ORDER BY name",
                    (team_id,)
                ).fetchall()
            return conn.execute(
                "SELECT * FROM people WHERE team_id = ? ORDER BY name",
                (team_id,)
            ).fetchall()
        if active_only:
            return conn.execute(
                "SELECT * FROM people WHERE active = 1 ORDER BY team_id, name"
            ).fetchall()
        return conn.execute("SELECT * FROM people ORDER BY team_id, name").fetchall()
    finally:
        conn.close()


def get_person(person_id: int) -> Optional[sqlite3.Row]:
    """Get a single person by ID."""
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
    finally:
        conn.close()


def create_person(name: str, team_id: int, role: str = 'operator') -> int:
    """Create a new person."""
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO people (name, team_id, role) VALUES (?, ?, ?)",
            (name, team_id, role)
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError(f"Person '{name}' already exists in this team")
    finally:
        conn.close()


def update_person(person_id: int, name: str, team_id: int, role: str, active: int) -> None:
    """Update a person."""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE people SET name = ?, team_id = ?, role = ?, active = ? WHERE id = ?",
            (name, team_id, role, active, person_id)
        )
        conn.commit()
    finally:
        conn.close()


def delete_person(person_id: int) -> None:
    """Delete a person."""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM people WHERE id = ?", (person_id,))
        conn.commit()
    finally:
        conn.close()


def get_availability_exceptions(person_id: Optional[int] = None) -> list[sqlite3.Row]:
    """Get availability exceptions, optionally for a specific person."""
    conn = get_conn()
    try:
        if person_id is not None:
            return conn.execute(
                "SELECT * FROM availability_exceptions WHERE person_id = ? ORDER BY start_date",
                (person_id,)
            ).fetchall()
        return conn.execute(
            "SELECT ae.*, p.name as person_name, p.team_id FROM availability_exceptions ae "
            "JOIN people p ON ae.person_id = p.id ORDER BY ae.start_date"
        ).fetchall()
    finally:
        conn.close()


def add_availability_exception(person_id: int, start_date: date, end_date: date, reason: str = '') -> int:
    """Add an availability exception (unavailable period)."""
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO availability_exceptions (person_id, start_date, end_date, reason) VALUES (?, ?, ?, ?)",
            (person_id, start_date.isoformat(), end_date.isoformat(), reason)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def delete_availability_exception(exception_id: int) -> None:
    """Delete an availability exception."""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM availability_exceptions WHERE id = ?", (exception_id,))
        conn.commit()
    finally:
        conn.close()


def is_person_available(person_id: int, check_date: date) -> bool:
    """Check if a person is available on a given date."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM availability_exceptions "
            "WHERE person_id = ? AND start_date <= ? AND end_date >= ?",
            (person_id, check_date.isoformat(), check_date.isoformat())
        ).fetchone()
        return row is None
    finally:
        conn.close()


def get_shift_assignments(start_date: date, end_date: date) -> list[sqlite3.Row]:
    """Get shift assignments in a date range."""
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT sa.*, p.name as person_name, p.team_id, t.name as team_name, t.color as team_color "
            "FROM shift_assignments sa "
            "JOIN people p ON sa.person_id = p.id "
            "JOIN teams t ON sa.team_id = t.id "
            "WHERE sa.schedule_date BETWEEN ? AND ? "
            "ORDER BY sa.schedule_date, sa.team_id, sa.shift",
            (start_date.isoformat(), end_date.isoformat())
        ).fetchall()
    finally:
        conn.close()


def get_shift_assignments_for_date(schedule_date: date) -> list[sqlite3.Row]:
    """Get shift assignments for a specific date."""
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT sa.*, p.name as person_name, p.team_id, t.name as team_name, t.color as team_color "
            "FROM shift_assignments sa "
            "JOIN people p ON sa.person_id = p.id "
            "JOIN teams t ON sa.team_id = t.id "
            "WHERE sa.schedule_date = ? "
            "ORDER BY sa.team_id, sa.shift",
            (schedule_date.isoformat(),)
        ).fetchall()
    finally:
        conn.close()


def set_shift_assignment(
    schedule_date: date,
    team_id: int,
    shift: int,
    person_id: int,
    is_substitute: int = 0,
    substitute_for_id: Optional[int] = None,
    notes: str = ''
) -> int:
    """Set or update a shift assignment."""
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO shift_assignments 
               (schedule_date, team_id, shift, person_id, is_substitute, substitute_for_id, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(schedule_date, team_id, shift, person_id) DO UPDATE SET
               is_substitute = excluded.is_substitute,
               substitute_for_id = excluded.substitute_for_id,
               notes = excluded.notes""",
            (schedule_date.isoformat(), team_id, shift, person_id, is_substitute, substitute_for_id, notes)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def delete_shift_assignment(assignment_id: int) -> None:
    """Delete a shift assignment."""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM shift_assignments WHERE id = ?", (assignment_id,))
        conn.commit()
    finally:
        conn.close()


def clear_shift_assignments(start_date: date, end_date: date) -> None:
    """Clear all shift assignments in a date range."""
    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM shift_assignments WHERE schedule_date BETWEEN ? AND ?",
            (start_date.isoformat(), end_date.isoformat())
        )
        conn.commit()
    finally:
        conn.close()


def get_shift_swaps(start_date: date, end_date: date) -> list[sqlite3.Row]:
    """Get shift swaps in a date range."""
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT ss.*, pa.name as person_a_name, pb.name as person_b_name "
            "FROM shift_swaps ss "
            "JOIN people pa ON ss.person_a_id = pa.id "
            "JOIN people pb ON ss.person_b_id = pb.id "
            "WHERE ss.schedule_date BETWEEN ? AND ? "
            "ORDER BY ss.schedule_date",
            (start_date.isoformat(), end_date.isoformat())
        ).fetchall()
    finally:
        conn.close()


def add_shift_swap(
    schedule_date: date,
    person_a_id: int,
    person_b_id: int,
    shift_a: int,
    shift_b: int
) -> int:
    """Add a shift swap between two people."""
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO shift_swaps (schedule_date, person_a_id, person_b_id, shift_a, shift_b) VALUES (?, ?, ?, ?, ?)",
            (schedule_date.isoformat(), person_a_id, person_b_id, shift_a, shift_b)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def delete_shift_swap(swap_id: int) -> None:
    """Delete a shift swap."""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM shift_swaps WHERE id = ?", (swap_id,))
        conn.commit()
    finally:
        conn.close()


def get_metadata(key: str, default: Any = None) -> Any:
    """Get a metadata value."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM schedule_metadata WHERE key = ?", (key,)).fetchone()
        if row:
            return json.loads(row["value"])
        return default
    finally:
        conn.close()


def set_metadata(key: str, value: Any) -> None:
    """Set a metadata value."""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO schedule_metadata (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')",
            (key, json.dumps(value))
        )
        conn.commit()
    finally:
        conn.close()