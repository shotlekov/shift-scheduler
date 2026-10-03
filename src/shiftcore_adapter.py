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
    """Convert a dataclass object to a dict, or return as-is if already a dict."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
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
        return True

    # Check if model is actually changing
    if rotation.shift_model == shift_model:
        return True  # No change needed

    # Model is changing - need to regenerate teams and clear schedule
    rotation.shift_model = shift_model
    _get_repo().update_rotation_group(rotation)

    # Regenerate teams for the new model
    create_teams_for_rotation_group(rotation.id)

    # Clear all shift assignments (different team structure)
    _get_repo().clear_assignments(date(1900, 1, 1), date(2100, 1, 1))

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


def generate_schedule(
    start_date: date, end_date: date, cycle_start: date, use_substitutes: bool = True
):
    """Generate a complete schedule for the date range."""
    rotation = _get_repo().get_rotation_group()
    if not rotation:
        raise ValueError("No rotation group configured")

    teams = _get_repo().get_teams()
    persons = _get_repo().get_persons()
    exceptions = _get_repo().get_exceptions()

    # Get existing assignments
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
    )

    # Save assignments to database
    _get_repo().save_assignments(result.assignments)

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
    """Get a grid view of the schedule for display."""
    assignments = _get_repo().get_assignments(start_date, end_date)

    # Build lookup
    assignment_map = {}
    for a in assignments:
        key = (a.schedule_date, a.team_id, int(a.shift_type))
        assignment_map[key] = a

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
