"""
Compatibility adapter that maps legacy db.py/scheduler.py functions to shiftcore.
This allows the existing Tkinter UI to work with the new shiftcore package
without major refactoring, while we plan the full UI migration.
"""

import sys
from pathlib import Path
from datetime import date, timedelta
from typing import Optional, Any
from dataclasses import asdict

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shiftcore import (
    SQLiteRepository,
    RotationGroup,
    Team,
    Person,
    AvailabilityException,
    ShiftAssignment,
    ShiftSwap,
    ShiftType,
    generate_schedule as core_generate_schedule,
    find_substitute as core_find_substitute,
    FairnessEngine,
    SHIFT_MODELS,
    BaseSchedule,
    ScheduleOverlay,
    ScheduleVersion,
)
from shiftcore.rotation import (
    RotationEngine,
    create_default_rotation_group,
    calculate_team_offsets,
)
from shiftcore.models import SHIFT_DEFINITIONS, MAX_CONSECUTIVE

# Database path
DB_PATH = PROJECT_ROOT / "data" / "shift_scheduler.db"

# Initialize repository
_repo = None


def _get_repo():
    """Get or create the SQLite repository."""
    global _repo
    if _repo is None:
        _repo = SQLiteRepository(DB_PATH)
    return _repo


# Export for use by app.py
get_repo = _get_repo


def _to_dict(obj):
    """Convert a dataclass object to a dict, or return as-is if already a dict.
    Converts date/datetime objects to ISO format strings."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "__dataclass_fields__"):
        result = asdict(obj)
        # Convert date/datetime objects to ISO format strings
        for key, value in result.items():
            if hasattr(value, "isoformat"):
                result[key] = value.isoformat()
        return result
    return obj


def init_db():
    """Initialize the database (no-op since SQLiteRepository does this on init)."""
    _get_repo()


# --- Rotation Group ---


def get_rotation_group():
    """Get the active rotation group."""
    return _get_repo().get_rotation_group()


def create_rotation_group(
    name: str, shift_model: str = "2-shift", cycle_start: Optional[date] = None
) -> int:
    """Create a new rotation group."""
    if cycle_start is None:
        cycle_start = date.today()
    group = create_default_rotation_group(name, shift_model, cycle_start)
    return _get_repo().create_rotation_group(group)


# --- Teams ---


def get_teams():
    """Get all teams."""
    teams = _get_repo().get_teams()
    return [_to_dict(t) for t in teams]


def get_team(team_id: int):
    """Get a single team by ID."""
    team = _get_repo().get_team(team_id)
    return _to_dict(team)


def create_team(name: str, color: str = "#2563eb", initial_shift_offset: int = 0):
    """Create a new team."""
    # Get the active rotation group
    rotation = _get_repo().get_rotation_group()
    if not rotation:
        # Create default rotation group
        group_id = create_rotation_group("Default Rotation", "2-shift", date.today())
        rotation = _get_repo().get_rotation_group()
        if not rotation:
            raise ValueError("Failed to create rotation group")

    team = Team(
        name=name,
        color=color,
        rotation_group_id=rotation.id,
        offset=initial_shift_offset,
    )
    return _get_repo().create_team(team)


def update_team(team_id: int, name: str, color: str, initial_shift_offset: int = 0):
    """Update a team."""
    team = _get_repo().get_team(team_id)
    if not team:
        raise ValueError(f"Team {team_id} not found")
    team.name = name
    team.color = color
    team.offset = initial_shift_offset
    _get_repo().update_team(team)


def delete_team(team_id: int):
    """Delete a team."""
    _get_repo().delete_team(team_id)


def create_teams_for_rotation_group(rotation_group_id: int):
    """Auto-create teams for a rotation group based on its shift model."""
    teams = _get_repo().create_teams_for_rotation_group(rotation_group_id)
    return [_to_dict(t) for t in teams]


def get_team_member_count(team_id: int) -> int:
    """Get the number of active persons assigned to a team."""
    return _get_repo().get_team_member_count(team_id)


def get_all_team_member_counts(group_id: Optional[int] = None) -> dict[int, int]:
    """Get member counts for all teams, optionally filtered by rotation group."""
    return _get_repo().get_all_team_member_counts(group_id)


def get_shift_model_info(shift_model: str) -> dict:
    """Get information about a shift model."""
    return SHIFT_MODELS.get(shift_model, {})


def get_current_shift_model() -> str:
    """Get the currently active shift model from the rotation group."""
    rotation = _get_repo().get_rotation_group()
    if rotation:
        return rotation.shift_model
    return "2-shift"


def set_shift_model(shift_model: str) -> bool:
    """
    Switch the shift model. This regenerates teams for the new model.
    Returns True if successful, False otherwise.
    """
    if shift_model not in SHIFT_MODELS:
        raise ValueError(f"Unknown shift model: {shift_model}")

    rotation = _get_repo().get_rotation_group()
    if not rotation:
        # Create new rotation group with the model
        create_rotation_group("Default Rotation", shift_model, date.today())
        rotation = _get_repo().get_rotation_group()
        if rotation:
            create_teams_for_rotation_group(rotation.id)
        return True

    # Check if model is actually changing
    if rotation.shift_model == shift_model:
        return True  # No change needed

    # Model is changing - need to regenerate teams and clear schedule
    # Update rotation group with new model and correct pattern
    model = SHIFT_MODELS[shift_model]
    rotation.shift_model = shift_model
    rotation.pattern = model["pattern"]
    repo = _get_repo()
    repo.update_rotation_group(rotation)

    # Delete ALL teams from ALL rotation groups, then recreate for current
    conn = repo._get_conn()
    try:
        conn.execute("DELETE FROM teams")
        conn.commit()
    finally:
        conn.close()

    # Regenerate teams for the new model
    create_teams_for_rotation_group(rotation.id)

    # Clear all shift assignments (different team structure)
    repo.clear_assignments(date(1900, 1, 1), date(2100, 1, 1))

    # Also set all people to unassigned (team_id = NULL)
    conn = repo._get_conn()
    try:
        conn.execute("UPDATE persons SET team_id = NULL")
        conn.commit()
    finally:
        conn.close()

    return True


def create_person_unassigned(
    name: str,
    role: str = "operator",
    telegram_chat_id: str = None,
    email: str = None,
):
    """Create a new person without team assignment."""
    person = Person(
        name=name,
        team_id=0,  # Will be assigned later
        role=role,
        active=True,
        telegram_chat_id=telegram_chat_id,
        email=email,
    )
    return _get_repo().create_person(person)


def assign_person_to_team(person_id: int, team_id: int):
    """Assign a person to a team."""
    person = _get_repo().get_person(person_id)
    if not person:
        raise ValueError(f"Person {person_id} not found")
    person.team_id = team_id
    _get_repo().update_person(person)


def import_people_from_csv(csv_content: str) -> list[dict]:
    """Import people from CSV content. Expected columns: name,role,telegram,email"""
    import csv
    import io

    results = []
    reader = csv.DictReader(io.StringIO(csv_content))
    for row in reader:
        name = row.get("name", "").strip()
        if not name:
            continue
        role = row.get("role", "operator").strip()
        telegram = row.get("telegram", "").strip() or None
        email = row.get("email", "").strip() or None

        person_id = create_person_unassigned(name, role, telegram, email)
        results.append(
            {
                "id": person_id,
                "name": name,
                "role": role,
                "telegram": telegram,
                "email": email,
            }
        )
    return results


def generate_demo_people(count: int = 15) -> list[dict]:
    """Generate demo people for testing."""
    import random

    roles = ["operator", "lead", "supervisor"]
    first_names = [
        "Alex",
        "Jordan",
        "Taylor",
        "Casey",
        "Morgan",
        "Riley",
        "Avery",
        "Quinn",
        "Blake",
        "Cameron",
        "Drew",
        "Emery",
        "Finley",
        "Hayden",
        "Jesse",
        "Kai",
        "Logan",
        "Marley",
        "Noah",
        "Peyton",
        "Reese",
        "Skyler",
        "Tatum",
        "Wyatt",
    ]
    last_names = [
        "Smith",
        "Johnson",
        "Williams",
        "Brown",
        "Jones",
        "Garcia",
        "Miller",
        "Davis",
        "Rodriguez",
        "Martinez",
        "Hernandez",
        "Lopez",
        "Gonzalez",
        "Wilson",
        "Anderson",
        "Thomas",
        "Taylor",
        "Moore",
        "Jackson",
        "Martin",
        "Lee",
        "Perez",
        "Thompson",
    ]

    results = []
    for i in range(count):
        name = f"{random.choice(first_names)} {random.choice(last_names)}"
        role = random.choice(roles)
        telegram = (
            f"user{random.randint(100000, 999999)}" if random.random() > 0.3 else None
        )
        email = (
            f"{name.lower().replace(' ', '.')}@example.com"
            if random.random() > 0.3
            else None
        )

        person_id = create_person_unassigned(name, role, telegram, email)
        results.append(
            {
                "id": person_id,
                "name": name,
                "role": role,
                "telegram": telegram,
                "email": email,
            }
        )
    return results


# --- Persons ---


def get_people(team_id: Optional[int] = None, active_only: bool = True):
    """Get all people, optionally filtered by team."""
    persons = _get_repo().get_persons(team_id, active_only)
    return [_to_dict(p) for p in persons]


def get_person(person_id: int):
    """Get a single person by ID."""
    person = _get_repo().get_person(person_id)
    return _to_dict(person)


def create_person(
    name: str,
    team_id: int,
    role: str = "operator",
    telegram_chat_id: str = None,
    email: str = None,
):
    """Create a new person."""
    person = Person(
        name=name,
        team_id=team_id,
        role=role,
        active=True,
        telegram_chat_id=telegram_chat_id,
        email=email,
    )
    return _get_repo().create_person(person)


def update_person(
    person_id: int,
    name: str,
    team_id: int,
    role: str,
    active: int,
    telegram_chat_id: str = None,
    email: str = None,
):
    """Update a person."""
    person = _get_repo().get_person(person_id)
    if not person:
        raise ValueError(f"Person {person_id} not found")
    person.name = name
    person.team_id = team_id
    person.role = role
    person.active = bool(active)
    person.telegram_chat_id = telegram_chat_id
    person.email = email
    _get_repo().update_person(person)


def delete_person(person_id: int):
    """Delete a person."""
    _get_repo().delete_person(person_id)


# --- Availability Exceptions ---


def get_availability_exceptions(person_id: Optional[int] = None):
    """Get availability exceptions."""
    exceptions = _get_repo().get_exceptions(person_id)
    return [_to_dict(e) for e in exceptions]


def add_availability_exception(
    person_id: int, start_date: date, end_date: date, reason: str = ""
):
    """Add an availability exception."""
    exc = AvailabilityException(
        person_id=person_id,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
    )
    return _get_repo().add_exception(exc)


def delete_availability_exception(exception_id: int):
    """Delete an availability exception."""
    _get_repo().delete_exception(exception_id)


def is_person_available(person_id: int, check_date: date) -> bool:
    """Check if a person is available on a given date."""
    return _get_repo().is_person_available(person_id, check_date)


# --- Shift Assignments ---


def get_shift_assignments(start_date: date, end_date: date):
    """Get shift assignments in a date range."""
    assignments = _get_repo().get_assignments(start_date, end_date)
    return [_to_dict(a) for a in assignments]


def get_shift_assignments_for_date(schedule_date: date):
    """Get shift assignments for a specific date."""
    assignments = _get_repo().get_assignments_for_date(schedule_date)
    return [_to_dict(a) for a in assignments]


def set_shift_assignment(
    schedule_date: date,
    team_id: int,
    shift: int,
    person_id: int,
    is_substitute: int = 0,
    substitute_for_id: Optional[int] = None,
    notes: str = "",
):
    """Set or update a shift assignment."""
    assignment = ShiftAssignment(
        schedule_date=schedule_date,
        shift_type=ShiftType(shift),
        person_id=person_id,
        team_id=team_id,
        is_substitute=bool(is_substitute),
        substitute_for_id=substitute_for_id,
        notes=notes,
    )
    return _get_repo().save_assignment(assignment)


def delete_shift_assignment(assignment_id: int):
    """Delete a shift assignment."""
    _get_repo().delete_assignment(assignment_id)


def clear_shift_assignments(start_date: date, end_date: date):
    """Clear all shift assignments in a date range."""
    _get_repo().clear_assignments(start_date, end_date)


# --- Shift Swaps ---


def get_shift_swaps(start_date: date, end_date: date):
    """Get shift swaps in a date range."""
    swaps = _get_repo().get_swaps(start_date, end_date)
    return [_to_dict(s) for s in swaps]


def add_shift_swap(
    schedule_date: date, person_a_id: int, person_b_id: int, shift_a: int, shift_b: int
):
    """Add a shift swap."""
    swap = ShiftSwap(
        schedule_date=schedule_date,
        person_a_id=person_a_id,
        person_b_id=person_b_id,
        shift_a=ShiftType(shift_a),
        shift_b=ShiftType(shift_b),
    )
    return _get_repo().save_swap(swap)


def delete_shift_swap(swap_id: int):
    """Delete a shift swap."""
    _get_repo().delete_swap(swap_id)


# --- Metadata ---


def get_metadata(key: str, default: Any = None):
    """Get a metadata value."""
    return _get_repo().get_metadata(key, default)


def set_metadata(key: str, value: Any):
    """Set a metadata value."""
    _get_repo().set_metadata(key, value)


# --- Scheduler Functions ---


def get_rotation_state(reference_date: date, cycle_start: date):
    """Calculate rotation state for a given date relative to cycle start."""
    days_diff = (reference_date - cycle_start).days
    day_in_cycle = days_diff % 6
    return type("RotationState", (), {"day_in_cycle": day_in_cycle})()


def get_team_shift_for_date(team_id: int, check_date: date, cycle_start: date):
    """Determine which shift a team should work on a given date."""
    rotation = _get_repo().get_rotation_group()
    if not rotation:
        return None

    team = _get_repo().get_team(team_id)
    if not team:
        return None

    engine = RotationEngine(rotation)
    shift = engine.get_team_shift(team.offset, check_date)

    if shift == ShiftType.OFF:
        return None
    return shift


def get_shift_for_date_all_teams(check_date: date, cycle_start: date):
    """Get shifts for all teams on a specific date."""
    rotation = _get_repo().get_rotation_group()
    if not rotation:
        return {}

    teams = _get_repo().get_teams()
    engine = RotationEngine(rotation)
    team_offsets = [t.offset for t in teams]
    shifts = engine.get_all_team_shifts(team_offsets, check_date)

    return {t.id: shifts.get(t.offset) for t in teams}


def validate_shift_constraints(
    person_id: int, check_date: date, proposed_shift, cycle_start: date
):
    """Validate constraints for assigning a person to a shift."""
    from shiftcore import validate_all_constraints

    person = _get_repo().get_person(person_id)
    if not person:
        return False, "Person not found"

    if not person.active:
        return False, "Person is inactive"

    if not _get_repo().is_person_available(person_id, check_date):
        return False, "Person has availability exception (unavailable)"

    # Get all assignments for constraint checking
    assignments = _get_repo().get_assignments(
        check_date - __import__("datetime").timedelta(days=7),
        check_date + __import__("datetime").timedelta(days=7),
    )

    # Convert to ShiftAssignment objects
    shift_assignments = []
    for a in assignments:
        shift_assignments.append(
            ShiftAssignment(
                schedule_date=a.schedule_date,
                shift_type=a.shift_type,
                person_id=a.person_id,
                team_id=a.team_id,
            )
        )

    exceptions = _get_repo().get_exceptions(person_id)

    valid, error = validate_all_constraints(
        person=person,
        target_date=check_date,
        proposed_shift=proposed_shift,
        assignments=shift_assignments,
        exceptions=exceptions,
        shift_defs=SHIFT_DEFINITIONS,
        max_consecutive=MAX_CONSECUTIVE,
    )

    return valid, error


def find_available_substitutes(
    team_id: int, check_date: date, shift, exclude_person_ids: list, cycle_start: date
):
    """Find available people from the resting team to substitute."""
    from shiftcore import find_substitute

    rotation = _get_repo().get_rotation_group()
    if not rotation:
        return []

    teams = _get_repo().get_teams()
    persons = _get_repo().get_persons()
    exceptions = _get_repo().get_exceptions()
    assignments = _get_repo().get_assignments(
        check_date - __import__("datetime").timedelta(days=7),
        check_date + __import__("datetime").timedelta(days=7),
    )

    # Convert to ShiftAssignment objects
    shift_assignments = []
    for a in assignments:
        shift_assignments.append(
            ShiftAssignment(
                schedule_date=a.schedule_date,
                shift_type=a.shift_type,
                person_id=a.person_id,
                team_id=a.team_id,
            )
        )

    fairness = FairnessEngine()

    substitute = core_find_substitute(
        rotation=rotation,
        teams=teams,
        persons=persons,
        exceptions=exceptions,
        assignments=shift_assignments,
        target_date=check_date,
        shift_type=shift,
        exclude_person_ids=exclude_person_ids,
        shift_defs=SHIFT_DEFINITIONS,
        max_consecutive=MAX_CONSECUTIVE,
        fairness_engine=fairness,
    )

    if substitute:
        return [
            {
                "person_id": substitute.id,
                "name": substitute.name,
                "team_id": substitute.team_id,
                "role": substitute.role,
                "valid": True,
                "error": "",
            }
        ]
    return []


def initialize_base_schedule(
    start_date: date,
    end_date: date,
    cycle_start: date,
    version: int = 1,
) -> dict:
    """
    Initialize the base schedule (immutable rotation pattern) for a date range.
    This should be run ONCE when setting up a new rotation or changing models.

    Returns info about the initialization.
    """
    rotation = _get_repo().get_rotation_group()
    if not rotation:
        raise ValueError("No rotation group configured")

    teams = _get_repo().get_teams()
    if not teams:
        raise ValueError("No teams configured. Run 'Regenerate Teams' first.")

    # Clear existing base schedule for this version
    _get_repo().clear_base_schedule(version)

    # Create schedule version record
    model = SHIFT_MODELS[rotation.shift_model]
    schedule_version = ScheduleVersion(
        version=version,
        shift_model=rotation.shift_model,
        cycle_start_date=cycle_start,
        team_count=model["team_count"],
    )
    _get_repo().create_schedule_version(schedule_version)

    # Generate base schedule entries (rotation pattern only, no people)
    engine = RotationEngine(rotation)
    team_offsets = [t.offset for t in teams]
    team_by_offset = {t.offset: t for t in teams}

    base_schedules = []
    current = start_date
    while current <= end_date:
        team_shifts = engine.get_all_team_shifts(team_offsets, current)

        for offset, shift_type in team_shifts.items():
            team = team_by_offset[offset]
            base = BaseSchedule(
                schedule_date=current,
                team_id=team.id,
                shift_type=shift_type,
                cycle_start_date=cycle_start,
                version=version,
            )
            base_schedules.append(base)

        current += __import__("datetime").timedelta(days=1)

    # Batch insert base schedule
    _get_repo().create_base_schedule_batch(base_schedules)

    return {
        "base_schedule_entries": len(base_schedules),
        "version": version,
        "shift_model": rotation.shift_model,
        "cycle_start": cycle_start.isoformat(),
        "date_range": f"{start_date} to {end_date}",
    }


def reinitialize_base_schedule(
    start_date: date,
    end_date: date,
    cycle_start: date,
    new_version: int = None,
) -> dict:
    """
    Reinitialize the base schedule - used when changing shift models (2↔3 shift).
    This clears ALL existing data and creates a fresh base schedule with new version.
    """
    rotation = _get_repo().get_rotation_group()
    if not rotation:
        raise ValueError("No rotation group configured")

    # Determine new version number
    if new_version is None:
        active_version = _get_repo().get_active_schedule_version()
        new_version = (active_version.version + 1) if active_version else 1

    # Clear all existing data for fresh start
    repo = _get_repo()
    conn = repo._get_conn()
    try:
        # Clear base schedule (all versions)
        conn.execute("DELETE FROM base_schedule")
        # Clear all overlays
        conn.execute("DELETE FROM schedule_overlays")
        # Clear all assignments
        conn.execute("DELETE FROM shift_assignments")
        # Clear unfilled shifts
        conn.execute("DELETE FROM unfilled_shifts")
        # Clear shift swaps
        conn.execute("DELETE FROM shift_swaps")
        # Clear person shift counters
        conn.execute("DELETE FROM person_shift_counters")
        # Set all people to unassigned
        conn.execute("UPDATE persons SET team_id = NULL")
        conn.commit()
    finally:
        conn.close()

    # Regenerate teams for the new model (handled by set_shift_model)
    # Then initialize new base schedule
    return initialize_base_schedule(start_date, end_date, cycle_start, new_version)


def generate_schedule(
    start_date: date,
    end_date: date,
    cycle_start: date,
    use_substitutes: bool = False,
    manual_overrides: dict = None,
):
    """
    Generate squad assignments (overlays) for the date range.
    Uses existing base schedule + applies overlays for substitutions, swaps, exceptions.

    Args:
        manual_overrides: Dict of {(team_id, date): shift_type} for manual first days config
        use_substitutes: If True, auto-assign substitutes. If False (default), return unfilled shifts
                         with recommended substitutes for admin review.
    """
    rotation = _get_repo().get_rotation_group()
    if not rotation:
        raise ValueError("No rotation group configured")

    # Check if base schedule exists for this version
    active_version = _get_repo().get_active_schedule_version()
    if not active_version:
        raise ValueError(
            "Base schedule not initialized. Run 'Initialize Base Schedule' first."
        )

    version = active_version.version

    teams = _get_repo().get_teams()
    persons = _get_repo().get_persons()
    exceptions = _get_repo().get_exceptions()

    # Get base schedule for the date range
    base_schedule = _get_repo().get_base_schedule(start_date, end_date, version)
    if not base_schedule:
        raise ValueError(
            f"No base schedule found for version {version}. Run initialization first."
        )

    # Get existing overlays (substitutions, swaps, exceptions)
    existing_overlays = _get_repo().get_overlays_for_date_range(
        start_date, end_date, version
    )

    # Build base schedule lookup: (date, team_id) -> shift_type
    base_lookup = {}
    for bs in base_schedule:
        base_lookup[(bs.schedule_date, bs.team_id)] = bs.shift_type

    # Build overlay lookup: (date, team_id) -> list of overlays
    overlay_lookup = {}
    for overlay in existing_overlays:
        # Get base_schedule entry to find date/team
        base_entry = _get_repo().get_base_schedule_for_date(
            overlay.base_schedule_id, version
        )
        # Actually we need to get the base_schedule entry for this overlay
        # Let's query it differently
        pass

    # For now, use the core generate_schedule which handles all logic
    # Get existing assignments from shift_assignments table
    existing = _get_repo().get_assignments(start_date, end_date)
    existing_assignments = []
    for a in existing:
        existing_assignments.append(
            ShiftAssignment(
                schedule_date=a.schedule_date,
                shift_type=a.shift_type,
                person_id=a.person_id,
                team_id=a.team_id,
                is_substitute=a.is_substitute,
                substitute_for_id=a.substitute_for_id,
                notes=a.notes,
            )
        )

    fairness = FairnessEngine()

    result = core_generate_schedule(
        rotation=rotation,
        teams=teams,
        persons=persons,
        exceptions=exceptions,
        existing_assignments=existing_assignments,
        start_date=start_date,
        end_date=end_date,
        shift_defs=SHIFT_DEFINITIONS,
        max_consecutive=MAX_CONSECUTIVE,
        fairness_engine=fairness,
        auto_substitute=use_substitutes,
    )

    # Apply manual overrides for first 2 days
    if manual_overrides:
        for (team_id, config_date), shift_type in manual_overrides.items():
            if start_date <= config_date <= end_date:
                if shift_type == 0:  # OFF - remove any assignment for this team/date
                    result.assignments = [
                        a
                        for a in result.assignments
                        if not (a.team_id == team_id and a.schedule_date == config_date)
                    ]
                else:
                    # Find and update the assignment for this team/date
                    for assignment in result.assignments:
                        if (
                            assignment.team_id == team_id
                            and assignment.schedule_date == config_date
                        ):
                            assignment.shift_type = ShiftType(shift_type)
                            break

    # Save assignments to database (these become overlays of type 'manual' or 'substitution')
    _get_repo().save_assignments(result.assignments)

    # Save unfilled shifts to database
    _get_repo().save_unfilled_shifts(result.unfilled_shifts)

    # Format results for UI
    return {
        "assignments": [
            {
                "date": a.schedule_date.isoformat(),
                "team_id": a.team_id,
                "shift": int(a.shift_type),
                "person_id": a.person_id,
                "person_name": _get_repo().get_person(a.person_id).name
                if _get_repo().get_person(a.person_id)
                else "Unknown",
                "is_substitute": a.is_substitute,
                "notes": a.notes,
            }
            for a in result.assignments
        ],
        "conflicts": result.conflicts,
        "substitutes_used": result.substitutions,
        "unfilled_shifts": result.unfilled_shifts,
        "fairness_report": result.fairness_report,
    }


def get_schedule_grid(start_date: date, end_date: date, cycle_start: date):
    """
    Get a grid view of the schedule for display.
    Reads from base_schedule + overlays (assignments, swaps, exceptions).
    """
    # Get active version
    active_version = _get_repo().get_active_schedule_version()
    if not active_version:
        # Fallback to old method if no base schedule
        return _get_schedule_grid_legacy(start_date, end_date, cycle_start)

    version = active_version.version

    # Get base schedule
    base_schedule = _get_repo().get_base_schedule(start_date, end_date, version)

    # Get assignments (overlays)
    assignments = _get_repo().get_assignments(start_date, end_date)

    # Get swaps
    swaps = _get_repo().get_swaps(start_date, end_date)

    # Get exceptions
    exceptions = _get_repo().get_exceptions()

    # Build lookups
    base_lookup = {}
    for bs in base_schedule:
        base_lookup[(bs.schedule_date, bs.team_id)] = bs.shift_type

    assignment_map = {}
    for a in assignments:
        key = (a.schedule_date.isoformat(), a.team_id, int(a.shift_type))
        assignment_map[key] = a

    # Build swap lookup: (date, person_id) -> swap info
    swap_map = {}
    for s in swaps:
        key_a = (s.schedule_date, s.person_a_id)
        key_b = (s.schedule_date, s.person_b_id)
        swap_map[key_a] = {
            "person_id": s.person_b_id,
            "shift": s.shift_b,
            "type": "swap_out",
        }
        swap_map[key_b] = {
            "person_id": s.person_a_id,
            "shift": s.shift_a,
            "type": "swap_in",
        }

    # Build exception lookup: (date, person_id) -> True
    exception_map = {}
    for exc in exceptions:
        current = exc.start_date
        while current <= exc.end_date:
            exception_map[(current, exc.person_id)] = True
            current += __import__("datetime").timedelta(days=1)

    rotation = _get_repo().get_rotation_group()
    teams = _get_repo().get_teams()

    grid = []
    current = start_date
    while current <= end_date:
        date_str = current.isoformat()

        row = {"date": date_str, "day_name": current.strftime("%A"), "teams": {}}

        for team in teams:
            # Get base shift from base_schedule
            base_shift = base_lookup.get((current, team.id))

            if base_shift is None or base_shift == ShiftType.OFF:
                row["teams"][team.id] = {
                    "shift": "OFF",
                    "person": None,
                    "is_sub": False,
                    "is_swapped": False,
                    "is_unavailable": False,
                }
            else:
                # Check for assignment
                key = (date_str, team.id, int(base_shift))
                assignment = assignment_map.get(key)

                if assignment:
                    person = _get_repo().get_person(assignment.person_id)
                    person_name = person.name if person else "Unknown"

                    # Check if this person is swapped on this date
                    swap_info = swap_map.get((current, assignment.person_id))
                    is_swapped = swap_info is not None

                    # Check if person is unavailable (exception)
                    is_unavailable = exception_map.get(
                        (current, assignment.person_id), False
                    )

                    row["teams"][team.id] = {
                        "shift": base_shift.name,
                        "person": person_name,
                        "person_id": assignment.person_id,
                        "is_sub": assignment.is_substitute,
                        "is_swapped": is_swapped,
                        "is_unavailable": is_unavailable,
                        "notes": assignment.notes,
                    }
                else:
                    # Check if unfilled shift with recommended substitute
                    unfilled_shifts = _get_repo().get_unfilled_shifts(current, current)
                    unfilled = None
                    for u in unfilled_shifts:
                        if u["team_id"] == team.id and u["shift_type"] == int(
                            base_shift
                        ):
                            unfilled = u
                            break

                    if unfilled:
                        row["teams"][team.id] = {
                            "shift": base_shift.name,
                            "person": "NEEDS COVERAGE",
                            "person_id": None,
                            "is_sub": False,
                            "is_swapped": False,
                            "is_unavailable": False,
                            "unfilled": True,
                            "recommended_substitute_id": unfilled.get(
                                "recommended_substitute_id"
                            ),
                            "recommended_substitute_name": unfilled.get(
                                "recommended_substitute_name"
                            ),
                            "recommended_substitute_team_id": unfilled.get(
                                "recommended_substitute_team_id"
                            ),
                            "reason": unfilled.get("reason"),
                        }
                    else:
                        row["teams"][team.id] = {
                            "shift": base_shift.name,
                            "person": "UNASSIGNED",
                            "person_id": None,
                            "is_sub": False,
                            "is_swapped": False,
                            "is_unavailable": False,
                        }

        grid.append(row)
        current += __import__("datetime").timedelta(days=1)

    return grid


def _get_schedule_grid_legacy(start_date: date, end_date: date, cycle_start: date):
    """Legacy schedule grid method (fallback)."""
    assignments = _get_repo().get_assignments(start_date, end_date)

    assignment_map = {}
    for a in assignments:
        key = (a.schedule_date.isoformat(), a.team_id, int(a.shift_type))
        assignment_map[key] = a

    unfilled_shifts = _get_repo().get_unfilled_shifts(start_date, end_date)
    unfilled_map = {}
    for u in unfilled_shifts:
        key = (u["date"], u["team_id"], u["shift"])
        unfilled_map[key] = u

    rotation = _get_repo().get_rotation_group()
    teams = _get_repo().get_teams()

    grid = []
    current = start_date
    while current <= end_date:
        date_str = current.isoformat()

        if rotation:
            engine = RotationEngine(rotation)
            team_offsets = [t.offset for t in teams]
            team_shifts = engine.get_all_team_shifts(team_offsets, current)
        else:
            team_shifts = {}

        row = {"date": date_str, "day_name": current.strftime("%A"), "teams": {}}

        for team in teams:
            shift = team_shifts.get(team.offset)
            if shift is None or shift == ShiftType.OFF:
                row["teams"][team.id] = {
                    "shift": "OFF",
                    "person": None,
                    "is_sub": False,
                }
            else:
                key = (date_str, team.id, int(shift))
                assignment = assignment_map.get(key)
                if assignment:
                    person = _get_repo().get_person(assignment.person_id)
                    row["teams"][team.id] = {
                        "shift": shift.name,
                        "person": person.name if person else "Unknown",
                        "person_id": assignment.person_id,
                        "is_sub": assignment.is_substitute,
                        "notes": assignment.notes,
                    }
                else:
                    unfilled_key = (date_str, team.id, shift.name)
                    unfilled = unfilled_map.get(unfilled_key)
                    if unfilled:
                        row["teams"][team.id] = {
                            "shift": shift.name,
                            "person": "NEEDS COVERAGE",
                            "person_id": None,
                            "is_sub": False,
                            "notes": "",
                            "unfilled": True,
                            "recommended_substitute_id": unfilled.get(
                                "recommended_substitute_id"
                            ),
                            "recommended_substitute_name": unfilled.get(
                                "recommended_substitute_name"
                            ),
                            "recommended_substitute_team_id": unfilled.get(
                                "recommended_substitute_team_id"
                            ),
                            "reason": unfilled.get("reason"),
                        }
                    else:
                        row["teams"][team.id] = {
                            "shift": shift.name,
                            "person": "UNASSIGNED",
                            "person_id": None,
                            "is_sub": False,
                            "notes": "",
                        }

        grid.append(row)
        current += __import__("datetime").timedelta(days=1)

    return grid


def get_person_schedule(person_id: int, start_date: date, end_date: date):
    """Get a person's schedule for a date range."""
    assignments = _get_repo().get_assignments_for_person(
        person_id, start_date, end_date
    )

    schedule = []
    for a in assignments:
        team = _get_repo().get_team(a.team_id)
        schedule.append(
            {
                "date": a.schedule_date.isoformat(),
                "team": team.name if team else "Unknown",
                "shift": a.shift_type.name,
                "is_substitute": a.is_substitute,
                "notes": a.notes,
            }
        )

    return sorted(schedule, key=lambda x: x["date"])
