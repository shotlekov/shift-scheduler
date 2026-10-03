"""
SQLite storage layer for shiftcore.
Repository pattern for all data access.
"""

import sqlite3
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from .models import (
    RotationGroup,
    Team,
    Person,
    AvailabilityException,
    ShiftAssignment,
    ShiftSwap,
    PersonShiftCounter,
    NotificationQueue,
    ShiftType,
    SHIFT_MODELS,
    TEAM_COLORS,
)
from .rotation import calculate_team_offsets
from .exceptions import StorageError


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -64000;
PRAGMA temp_store = MEMORY;

CREATE TABLE IF NOT EXISTS rotation_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    shift_model TEXT NOT NULL CHECK (shift_model IN ('2-shift', '3-shift')),
    pattern TEXT NOT NULL,
    cycle_start_date TEXT NOT NULL,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    color TEXT DEFAULT '#2563eb',
    rotation_group_id INTEGER NOT NULL REFERENCES rotation_groups(id) ON DELETE CASCADE,
    offset INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    role TEXT DEFAULT 'operator',
    active INTEGER DEFAULT 1,
    telegram_chat_id TEXT,
    email TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS availability_exceptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    reason TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS shift_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_date TEXT NOT NULL,
    shift_type INTEGER NOT NULL CHECK (shift_type IN (1, 2, 3)),
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    is_substitute INTEGER DEFAULT 0,
    substitute_for_id INTEGER REFERENCES persons(id) ON DELETE SET NULL,
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(schedule_date, shift_type, person_id)
);

CREATE TABLE IF NOT EXISTS shift_swaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_date TEXT NOT NULL,
    person_a_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    person_b_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    shift_a INTEGER NOT NULL CHECK (shift_a IN (1, 2, 3)),
    shift_b INTEGER NOT NULL CHECK (shift_b IN (1, 2, 3)),
    approved INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS person_shift_counters (
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    period_start TEXT NOT NULL,
    shift_count INTEGER DEFAULT 0,
    last_assignment_date TEXT,
    PRIMARY KEY (person_id, period_start)
);

CREATE TABLE IF NOT EXISTS notification_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL CHECK (target_type IN ('person_dm', 'team_group', 'all_teams_group', 'email')),
    target_id TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed')),
    retries INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    sent_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_assignments_date ON shift_assignments(schedule_date);
CREATE INDEX IF NOT EXISTS idx_assignments_person_date ON shift_assignments(person_id, schedule_date);
CREATE INDEX IF NOT EXISTS idx_assignments_team_date ON shift_assignments(team_id, schedule_date);
CREATE INDEX IF NOT EXISTS idx_exceptions_person_date ON availability_exceptions(person_id, start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_swaps_date ON shift_swaps(schedule_date);
CREATE INDEX IF NOT EXISTS idx_notifications_status ON notification_queue(status);
CREATE INDEX IF NOT EXISTS idx_counters_person_period ON person_shift_counters(person_id, period_start);

CREATE TABLE IF NOT EXISTS schedule_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class SQLiteRepository:
    """SQLite repository for all data access."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        """Initialize database schema."""
        conn = self._get_conn()
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        except Exception as e:
            raise StorageError(
                f"Schema initialization failed: {e}", operation="init_schema"
            )
        finally:
            conn.close()

    # --- Rotation Group ---

    def get_rotation_group(self) -> Optional[RotationGroup]:
        """Get the active rotation group."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM rotation_groups WHERE active = 1 ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            return self._row_to_rotation_group(row)
        finally:
            conn.close()

    def get_rotation_group_by_id(self, group_id: int) -> Optional[RotationGroup]:
        """Get rotation group by ID."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM rotation_groups WHERE id = ?", (group_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_rotation_group(row)
        finally:
            conn.close()

    def create_rotation_group(self, group: RotationGroup) -> int:
        """Create a new rotation group. Deactivates existing active group."""
        conn = self._get_conn()
        try:
            # Deactivate existing active groups
            conn.execute("UPDATE rotation_groups SET active = 0 WHERE active = 1")
            cur = conn.execute(
                "INSERT INTO rotation_groups (name, shift_model, pattern, cycle_start_date, active) VALUES (?, ?, ?, ?, 1)",
                (
                    group.name,
                    group.shift_model,
                    json.dumps(group.pattern),
                    group.cycle_start_date.isoformat(),
                ),
            )
            conn.commit()
            return cur.lastrowid or 0 or 0
        except Exception as e:
            raise StorageError(
                f"Failed to create rotation group: {e}",
                operation="create",
                table="rotation_groups",
            )
        finally:
            conn.close()

    def update_rotation_group(self, group: RotationGroup) -> None:
        """Update rotation group."""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE rotation_groups SET name = ?, shift_model = ?, pattern = ?, cycle_start_date = ?, active = ? WHERE id = ?",
                (
                    group.name,
                    group.shift_model,
                    json.dumps(group.pattern),
                    group.cycle_start_date.isoformat(),
                    int(group.active),
                    group.id,
                ),
            )
            conn.commit()
        except Exception as e:
            raise StorageError(
                f"Failed to update rotation group: {e}",
                operation="update",
                table="rotation_groups",
            )
        finally:
            conn.close()

    def delete_rotation_group(self, group_id: int) -> None:
        """Delete rotation group."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM rotation_groups WHERE id = ?", (group_id,))
            conn.commit()
        except Exception as e:
            raise StorageError(
                f"Failed to delete rotation group: {e}",
                operation="delete",
                table="rotation_groups",
            )
        finally:
            conn.close()

    def _row_to_rotation_group(self, row: sqlite3.Row) -> RotationGroup:
        return RotationGroup(
            id=row["id"],
            name=row["name"],
            shift_model=row["shift_model"],
            pattern=json.loads(row["pattern"]),
            cycle_start_date=date.fromisoformat(row["cycle_start_date"]),
            active=bool(row["active"]),
            created_at=row["created_at"],
        )

    # --- Teams ---

    def get_teams(self, group_id: Optional[int] = None) -> list[Team]:
        """Get all teams, optionally filtered by rotation group."""
        conn = self._get_conn()
        try:
            if group_id is not None:
                rows = conn.execute(
                    "SELECT * FROM teams WHERE rotation_group_id = ? ORDER BY offset",
                    (group_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM teams ORDER BY rotation_group_id, offset"
                ).fetchall()
            return [self._row_to_team(row) for row in rows]
        finally:
            conn.close()

    def get_team(self, team_id: int) -> Optional[Team]:
        """Get team by ID."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM teams WHERE id = ?", (team_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_team(row)
        finally:
            conn.close()

    def create_team(self, team: Team) -> int:
        """Create a new team."""
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO teams (name, color, rotation_group_id, offset) VALUES (?, ?, ?, ?)",
                (team.name, team.color, team.rotation_group_id, team.offset),
            )
            conn.commit()
            return cur.lastrowid or 0 or 0
        except Exception as e:
            raise StorageError(
                f"Failed to create team: {e}", operation="create", table="teams"
            )
        finally:
            conn.close()

    def update_team(self, team: Team) -> None:
        """Update team."""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE teams SET name = ?, color = ?, rotation_group_id = ?, offset = ? WHERE id = ?",
                (team.name, team.color, team.rotation_group_id, team.offset, team.id),
            )
            conn.commit()
        except Exception as e:
            raise StorageError(
                f"Failed to update team: {e}", operation="update", table="teams"
            )
        finally:
            conn.close()

    def delete_team(self, team_id: int) -> None:
        """Delete team."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))
            conn.commit()
        except Exception as e:
            raise StorageError(
                f"Failed to delete team: {e}", operation="delete", table="teams"
            )
        finally:
            conn.close()

    def create_teams_for_rotation_group(self, rotation_group_id: int) -> list[Team]:
        """Auto-create teams for a rotation group based on its shift model."""
        rotation = self.get_rotation_group_by_id(rotation_group_id)
        if not rotation:
            raise StorageError(
                f"Rotation group {rotation_group_id} not found",
                operation="create_teams",
                table="teams",
            )

        model = SHIFT_MODELS.get(rotation.shift_model)
        if not model:
            raise StorageError(
                f"Unknown shift model: {rotation.shift_model}",
                operation="create_teams",
                table="teams",
            )

        team_count = model["team_count"]
        pattern_length = model["pattern_length"]
        offsets = calculate_team_offsets(pattern_length, team_count)

        # Delete existing teams for this rotation group
        conn = self._get_conn()
        try:
            conn.execute(
                "DELETE FROM teams WHERE rotation_group_id = ?", (rotation_group_id,)
            )
            conn.commit()
        finally:
            conn.close()

        # Create new teams
        teams = []
        for i, offset in enumerate(offsets):
            team = Team(
                name=f"Team {i + 1}",
                color=TEAM_COLORS[i % len(TEAM_COLORS)],
                rotation_group_id=rotation_group_id,
                offset=offset,
            )
            team_id = self.create_team(team)
            team.id = team_id
            teams.append(team)

        return teams

    def get_team_member_count(self, team_id: int) -> int:
        """Get the number of active persons assigned to a team."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as count FROM persons WHERE team_id = ? AND active = 1",
                (team_id,),
            ).fetchone()
            return row["count"] if row else 0
        finally:
            conn.close()

    def get_all_team_member_counts(
        self, group_id: Optional[int] = None
    ) -> dict[int, int]:
        """Get member counts for all teams, optionally filtered by rotation group."""
        teams = self.get_teams(group_id)
        counts = {}
        for team in teams:
            if team.id is not None:
                counts[team.id] = self.get_team_member_count(team.id)
        return counts

    def _row_to_team(self, row: sqlite3.Row) -> Team:
        return Team(
            id=row["id"],
            name=row["name"],
            color=row["color"],
            rotation_group_id=row["rotation_group_id"],
            offset=row["offset"],
            created_at=row["created_at"],
        )

    # --- Persons ---

    def get_persons(
        self, team_id: Optional[int] = None, active_only: bool = True
    ) -> list[Person]:
        """Get all persons, optionally filtered by team."""
        conn = self._get_conn()
        try:
            if team_id is not None:
                if active_only:
                    rows = conn.execute(
                        "SELECT * FROM persons WHERE team_id = ? AND active = 1 ORDER BY name",
                        (team_id,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM persons WHERE team_id = ? ORDER BY name",
                        (team_id,),
                    ).fetchall()
            else:
                if active_only:
                    rows = conn.execute(
                        "SELECT * FROM persons WHERE active = 1 ORDER BY team_id, name"
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM persons ORDER BY team_id, name"
                    ).fetchall()
            return [self._row_to_person(row) for row in rows]
        finally:
            conn.close()

    def get_person(self, person_id: int) -> Optional[Person]:
        """Get person by ID."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM persons WHERE id = ?", (person_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_person(row)
        finally:
            conn.close()

    def create_person(self, person: Person) -> int:
        """Create a new person."""
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO persons (name, team_id, role, active, telegram_chat_id, email) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    person.name,
                    person.team_id,
                    person.role,
                    int(person.active),
                    person.telegram_chat_id,
                    person.email,
                ),
            )
            conn.commit()
            return cur.lastrowid or 0
        except sqlite3.IntegrityError:
            raise StorageError(
                f"Person '{person.name}' already exists in this team",
                operation="create",
                table="persons",
            )
        except Exception as e:
            raise StorageError(
                f"Failed to create person: {e}", operation="create", table="persons"
            )
        finally:
            conn.close()

    def update_person(self, person: Person) -> None:
        """Update person."""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE persons SET name = ?, team_id = ?, role = ?, active = ?, telegram_chat_id = ?, email = ? WHERE id = ?",
                (
                    person.name,
                    person.team_id,
                    person.role,
                    int(person.active),
                    person.telegram_chat_id,
                    person.email,
                    person.id,
                ),
            )
            conn.commit()
        except Exception as e:
            raise StorageError(
                f"Failed to update person: {e}", operation="update", table="persons"
            )
        finally:
            conn.close()

    def delete_person(self, person_id: int) -> None:
        """Delete person."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM persons WHERE id = ?", (person_id,))
            conn.commit()
        except Exception as e:
            raise StorageError(
                f"Failed to delete person: {e}", operation="delete", table="persons"
            )
        finally:
            conn.close()

    def _row_to_person(self, row: sqlite3.Row) -> Person:
        return Person(
            id=row["id"],
            name=row["name"],
            team_id=row["team_id"],
            role=row["role"],
            active=bool(row["active"]),
            telegram_chat_id=row["telegram_chat_id"],
            email=row["email"],
            created_at=row["created_at"],
        )

    # --- Availability Exceptions ---

    def get_exceptions(
        self, person_id: Optional[int] = None
    ) -> list[AvailabilityException]:
        """Get availability exceptions."""
        conn = self._get_conn()
        try:
            if person_id is not None:
                rows = conn.execute(
                    "SELECT * FROM availability_exceptions WHERE person_id = ? ORDER BY start_date",
                    (person_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM availability_exceptions ORDER BY start_date"
                ).fetchall()
            return [self._row_to_exception(row) for row in rows]
        finally:
            conn.close()

    def add_exception(self, exc: AvailabilityException) -> int:
        """Add availability exception."""
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO availability_exceptions (person_id, start_date, end_date, reason) VALUES (?, ?, ?, ?)",
                (
                    exc.person_id,
                    exc.start_date.isoformat(),
                    exc.end_date.isoformat(),
                    exc.reason,
                ),
            )
            conn.commit()
            return cur.lastrowid or 0
        except Exception as e:
            raise StorageError(
                f"Failed to add exception: {e}",
                operation="create",
                table="availability_exceptions",
            )
        finally:
            conn.close()

    def delete_exception(self, exception_id: int) -> None:
        """Delete availability exception."""
        conn = self._get_conn()
        try:
            conn.execute(
                "DELETE FROM availability_exceptions WHERE id = ?", (exception_id,)
            )
            conn.commit()
        except Exception as e:
            raise StorageError(
                f"Failed to delete exception: {e}",
                operation="delete",
                table="availability_exceptions",
            )
        finally:
            conn.close()

    def is_person_available(self, person_id: int, check_date: date) -> bool:
        """Check if person is available on given date."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT 1 FROM availability_exceptions WHERE person_id = ? AND start_date <= ? AND end_date >= ?",
                (person_id, check_date.isoformat(), check_date.isoformat()),
            ).fetchone()
            return row is None
        finally:
            conn.close()

    def _row_to_exception(self, row: sqlite3.Row) -> AvailabilityException:
        return AvailabilityException(
            id=row["id"],
            person_id=row["person_id"],
            start_date=date.fromisoformat(row["start_date"]),
            end_date=date.fromisoformat(row["end_date"]),
            reason=row["reason"],
            created_at=row["created_at"],
        )

    # --- Shift Assignments ---

    def get_assignments(
        self, start_date: date, end_date: date
    ) -> list[ShiftAssignment]:
        """Get shift assignments in date range."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT sa.*, p.name as person_name, p.team_id as person_team_id, 
                   t.name as team_name, t.color as team_color
                   FROM shift_assignments sa
                   JOIN persons p ON sa.person_id = p.id
                   JOIN teams t ON sa.team_id = t.id
                   WHERE sa.schedule_date BETWEEN ? AND ?
                   ORDER BY sa.schedule_date, sa.team_id, sa.shift_type""",
                (start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
            return [self._row_to_assignment(row) for row in rows]
        finally:
            conn.close()

    def get_assignments_for_date(self, target_date: date) -> list[ShiftAssignment]:
        """Get assignments for a specific date."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT sa.*, p.name as person_name, p.team_id as person_team_id,
                   t.name as team_name, t.color as team_color
                   FROM shift_assignments sa
                   JOIN persons p ON sa.person_id = p.id
                   JOIN teams t ON sa.team_id = t.id
                   WHERE sa.schedule_date = ?
                   ORDER BY sa.team_id, sa.shift_type""",
                (target_date.isoformat(),),
            ).fetchall()
            return [self._row_to_assignment(row) for row in rows]
        finally:
            conn.close()

    def get_assignments_for_person(
        self, person_id: int, start_date: date, end_date: date
    ) -> list[ShiftAssignment]:
        """Get assignments for a specific person in date range."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT sa.*, p.name as person_name, p.team_id as person_team_id,
                   t.name as team_name, t.color as team_color
                   FROM shift_assignments sa
                   JOIN persons p ON sa.person_id = p.id
                   JOIN teams t ON sa.team_id = t.id
                   WHERE sa.person_id = ? AND sa.schedule_date BETWEEN ? AND ?
                   ORDER BY sa.schedule_date""",
                (person_id, start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
            return [self._row_to_assignment(row) for row in rows]
        finally:
            conn.close()

    def save_assignment(self, assignment: ShiftAssignment) -> int:
        """Save or update a shift assignment."""
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """INSERT INTO shift_assignments 
                   (schedule_date, shift_type, person_id, team_id, is_substitute, substitute_for_id, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(schedule_date, shift_type, person_id) DO UPDATE SET
                   team_id = excluded.team_id,
                   is_substitute = excluded.is_substitute,
                   substitute_for_id = excluded.substitute_for_id,
                   notes = excluded.notes""",
                (
                    assignment.schedule_date.isoformat(),
                    int(assignment.shift_type),
                    assignment.person_id,
                    assignment.team_id,
                    int(assignment.is_substitute),
                    assignment.substitute_for_id,
                    assignment.notes,
                ),
            )
            conn.commit()
            return cur.lastrowid or 0
        except Exception as e:
            raise StorageError(
                f"Failed to save assignment: {e}",
                operation="save",
                table="shift_assignments",
            )
        finally:
            conn.close()

    def save_assignments(self, assignments: list[ShiftAssignment]) -> None:
        """Save multiple assignments in a transaction."""
        conn = self._get_conn()
        try:
            for assignment in assignments:
                conn.execute(
                    """INSERT INTO shift_assignments 
                       (schedule_date, shift_type, person_id, team_id, is_substitute, substitute_for_id, notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(schedule_date, shift_type, person_id) DO UPDATE SET
                       team_id = excluded.team_id,
                       is_substitute = excluded.is_substitute,
                       substitute_for_id = excluded.substitute_for_id,
                       notes = excluded.notes""",
                    (
                        assignment.schedule_date.isoformat(),
                        int(assignment.shift_type),
                        assignment.person_id,
                        assignment.team_id,
                        int(assignment.is_substitute),
                        assignment.substitute_for_id,
                        assignment.notes,
                    ),
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise StorageError(
                f"Failed to save assignments: {e}",
                operation="save_batch",
                table="shift_assignments",
            )
        finally:
            conn.close()

    def clear_assignments(self, start_date: date, end_date: date) -> None:
        """Clear all assignments in date range."""
        conn = self._get_conn()
        try:
            conn.execute(
                "DELETE FROM shift_assignments WHERE schedule_date BETWEEN ? AND ?",
                (start_date.isoformat(), end_date.isoformat()),
            )
            conn.commit()
        except Exception as e:
            raise StorageError(
                f"Failed to clear assignments: {e}",
                operation="clear",
                table="shift_assignments",
            )
        finally:
            conn.close()

    def delete_assignment(self, assignment_id: int) -> None:
        """Delete a shift assignment."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM shift_assignments WHERE id = ?", (assignment_id,))
            conn.commit()
        except Exception as e:
            raise StorageError(
                f"Failed to delete assignment: {e}",
                operation="delete",
                table="shift_assignments",
            )
        finally:
            conn.close()

    def _row_to_assignment(self, row: sqlite3.Row) -> ShiftAssignment:
        return ShiftAssignment(
            id=row["id"],
            schedule_date=date.fromisoformat(row["schedule_date"]),
            shift_type=ShiftType(row["shift_type"]),
            person_id=row["person_id"],
            team_id=row["team_id"],
            is_substitute=bool(row["is_substitute"]),
            substitute_for_id=row["substitute_for_id"],
            notes=row["notes"],
            created_at=row["created_at"],
        )

    # --- Shift Swaps ---

    def get_swaps(self, start_date: date, end_date: date) -> list[ShiftSwap]:
        """Get shift swaps in date range."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT ss.*, pa.name as person_a_name, pb.name as person_b_name
                   FROM shift_swaps ss
                   JOIN persons pa ON ss.person_a_id = pa.id
                   JOIN persons pb ON ss.person_b_id = pb.id
                   WHERE ss.schedule_date BETWEEN ? AND ?
                   ORDER BY ss.schedule_date""",
                (start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
            return [self._row_to_swap(row) for row in rows]
        finally:
            conn.close()

    def save_swap(self, swap: ShiftSwap) -> int:
        """Save a shift swap."""
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO shift_swaps (schedule_date, person_a_id, person_b_id, shift_a, shift_b, approved) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    swap.schedule_date.isoformat(),
                    swap.person_a_id,
                    swap.person_b_id,
                    int(swap.shift_a),
                    int(swap.shift_b),
                    int(swap.approved),
                ),
            )
            conn.commit()
            return cur.lastrowid or 0
        except Exception as e:
            raise StorageError(
                f"Failed to save swap: {e}", operation="create", table="shift_swaps"
            )
        finally:
            conn.close()

    def delete_swap(self, swap_id: int) -> None:
        """Delete a shift swap."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM shift_swaps WHERE id = ?", (swap_id,))
            conn.commit()
        except Exception as e:
            raise StorageError(
                f"Failed to delete swap: {e}", operation="delete", table="shift_swaps"
            )
        finally:
            conn.close()

    def _row_to_swap(self, row: sqlite3.Row) -> ShiftSwap:
        return ShiftSwap(
            id=row["id"],
            schedule_date=date.fromisoformat(row["schedule_date"]),
            person_a_id=row["person_a_id"],
            person_b_id=row["person_b_id"],
            shift_a=ShiftType(row["shift_a"]),
            shift_b=ShiftType(row["shift_b"]),
            approved=bool(row["approved"]),
            created_at=row["created_at"],
        )

    # --- Person Shift Counters ---

    def get_shift_counters(
        self, person_ids: list[int], period_start: date
    ) -> dict[int, PersonShiftCounter]:
        """Get shift counters for persons in a period."""
        conn = self._get_conn()
        try:
            placeholders = ",".join("?" * len(person_ids))
            rows = conn.execute(
                f"SELECT * FROM person_shift_counters WHERE person_id IN ({placeholders}) AND period_start = ?",
                (*person_ids, period_start.isoformat()),
            ).fetchall()
            counters = {}
            for row in rows:
                counters[row["person_id"]] = PersonShiftCounter(
                    person_id=row["person_id"],
                    period_start=date.fromisoformat(row["period_start"]),
                    shift_count=row["shift_count"],
                    last_assignment_date=date.fromisoformat(row["last_assignment_date"])
                    if row["last_assignment_date"]
                    else None,
                )
            return counters
        finally:
            conn.close()

    def save_shift_counter(self, counter: PersonShiftCounter) -> None:
        """Save or update a shift counter."""
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO person_shift_counters (person_id, period_start, shift_count, last_assignment_date)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(person_id, period_start) DO UPDATE SET
                   shift_count = excluded.shift_count,
                   last_assignment_date = excluded.last_assignment_date""",
                (
                    counter.person_id,
                    counter.period_start.isoformat(),
                    counter.shift_count,
                    counter.last_assignment_date.isoformat()
                    if counter.last_assignment_date
                    else None,
                ),
            )
            conn.commit()
        except Exception as e:
            raise StorageError(
                f"Failed to save counter: {e}",
                operation="save",
                table="person_shift_counters",
            )
        finally:
            conn.close()

    # --- Notifications ---

    def queue_notification(self, target_type: str, target_id: str, message: str) -> int:
        """Queue a notification."""
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO notification_queue (target_type, target_id, message) VALUES (?, ?, ?)",
                (target_type, target_id, message),
            )
            conn.commit()
            return cur.lastrowid or 0
        except Exception as e:
            raise StorageError(
                f"Failed to queue notification: {e}",
                operation="create",
                table="notification_queue",
            )
        finally:
            conn.close()

    def get_pending_notifications(self, limit: int = 100) -> list[NotificationQueue]:
        """Get pending notifications."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM notification_queue WHERE status = 'pending' ORDER BY created_at LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._row_to_notification(row) for row in rows]
        finally:
            conn.close()

    def mark_notification_sent(self, notification_id: int) -> None:
        """Mark notification as sent."""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE notification_queue SET status = 'sent', sent_at = datetime('now') WHERE id = ?",
                (notification_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_notification_failed(self, notification_id: int) -> None:
        """Mark notification as failed."""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE notification_queue SET status = 'failed', retries = retries + 1 WHERE id = ?",
                (notification_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def _row_to_notification(self, row: sqlite3.Row) -> NotificationQueue:
        return NotificationQueue(
            id=row["id"],
            target_type=row["target_type"],
            target_id=row["target_id"],
            message=row["message"],
            status=row["status"],
            retries=row["retries"],
            created_at=row["created_at"],
            sent_at=row["sent_at"],
        )

    # --- Utility ---

    def get_team_telegram_chat_id(self, team_id: int) -> Optional[str]:
        """Get Telegram chat ID for a team's group."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT telegram_chat_id FROM teams WHERE id = ?", (team_id,)
            ).fetchone()
            return row["telegram_chat_id"] if row else None
        finally:
            conn.close()

    def get_all_teams_telegram_chat_id(self) -> Optional[str]:
        """Get Telegram chat ID for all-teams group."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT value FROM schedule_metadata WHERE key = 'all_teams_telegram_chat_id'"
            ).fetchone()
            return row["value"] if row else None
        finally:
            conn.close()

    def set_metadata(self, key: str, value: str) -> None:
        """Set metadata value."""
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO schedule_metadata (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()

    def get_metadata(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get metadata value."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT value FROM schedule_metadata WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else default
        finally:
            conn.close()
