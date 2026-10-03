# Shift Scheduler - API Reference

## shiftcore Package

Main entry point for the core scheduling library.

```python
from shiftcore import (
    # Models
    RotationGroup, Team, Person, AvailabilityException,
    ShiftAssignment, ShiftSwap, PersonShiftCounter,
    NotificationQueue, ShiftType, ScheduleResult,
    # Rotation
    RotationEngine, get_team_shift, get_all_team_shifts,
    create_default_rotation_group, calculate_team_offsets,
    # Constraints
    validate_all_constraints, check_one_shift_per_day,
    check_rest_hours, check_max_consecutive, get_violations,
    # Fairness
    FairnessEngine,
    # Scheduler
    generate_schedule, find_substitute,
    # Swaps
    validate_swap, get_swap_violations,
    # Notifications
    NotificationService, SMTPConfig,
    # Storage
    SQLiteRepository,
    # Exceptions
    ConstraintViolation, NoEligibleSubstitute,
    NotificationFailed, RotationError, StorageError,
    # Constants
    SHIFT_DEFINITIONS, MAX_CONSECUTIVE, DEFAULT_PATTERNS,
    SHIFT_MODELS, TEAM_COLORS,
)
```

---

## Models

### ShiftType (IntEnum)

```python
class ShiftType(IntEnum):
    OFF = 0
    FIRST = 1    # 06:00-14:00
    SECOND = 2   # 14:00-22:00
    THIRD = 3    # 22:00-06:00 (crosses midnight)
```

### RotationGroup

```python
@dataclass
class RotationGroup:
    id: Optional[int] = None
    name: str = ""
    shift_model: str = "2-shift"  # "2-shift" or "3-shift"
    pattern: list[int] = field(default_factory=list)
    cycle_start_date: date = field(default_factory=date.today)
    active: bool = True
    created_at: str = ""

    @property
    def pattern_length(self) -> int:
        return len(self.pattern)

    def get_shift_for_offset(self, offset: int, target_date: date) -> ShiftType:
        """Get shift type for a team at given offset on target date."""

    @classmethod
    def create_default(
        cls, name: str, shift_model: str, cycle_start: date
    ) -> "RotationGroup":
        """Create a rotation group with default pattern for the shift model."""

    def get_team_count(self) -> int:
        """Get the required number of teams for this shift model."""

    def get_shifts(self) -> list[ShiftType]:
        """Get the shift types used in this model."""

    def get_max_consecutive(self) -> dict[ShiftType, int]:
        """Get max consecutive shifts per shift type."""
```

### Team

```python
@dataclass
class Team:
    id: Optional[int] = None
    name: str = ""
    color: str = "#2563eb"
    rotation_group_id: int = 0
    offset: int = 0  # Pattern index offset (0..pattern_length-1)
    created_at: str = ""

    def get_shift_for_date(self, rotation: RotationGroup, target_date: date) -> ShiftType:
        """Get this team's shift for a specific date."""
```

### Person

```python
@dataclass
class Person:
    id: Optional[int] = None
    name: str = ""
    team_id: int = 0
    role: str = "operator"
    active: bool = True
    telegram_chat_id: Optional[str] = None
    email: Optional[str] = None
    created_at: str = ""
```

### AvailabilityException

```python
@dataclass
class AvailabilityException:
    id: Optional[int] = None
    person_id: int = 0
    start_date: date = field(default_factory=date.today)
    end_date: date = field(default_factory=date.today)
    reason: str = ""
    created_at: str = ""

    def covers_date(self, check_date: date) -> bool:
        """Check if this exception covers the given date."""
```

### ShiftAssignment

```python
@dataclass
class ShiftAssignment:
    id: Optional[int] = None
    schedule_date: date = field(default_factory=date.today)
    shift_type: ShiftType = ShiftType.FIRST
    person_id: int = 0
    team_id: int = 0
    is_substitute: bool = False
    substitute_for_id: Optional[int] = None
    notes: str = ""
    created_at: str = ""
```

### ShiftSwap

```python
@dataclass
class ShiftSwap:
    id: Optional[int] = None
    schedule_date: date = field(default_factory=date.today)
    person_a_id: int = 0
    person_b_id: int = 0
    shift_a: ShiftType = ShiftType.FIRST
    shift_b: ShiftType = ShiftType.SECOND
    approved: bool = True
    created_at: str = ""
```

### PersonShiftCounter

```python
@dataclass
class PersonShiftCounter:
    person_id: int = 0
    period_start: date = field(default_factory=date.today)
    shift_count: int = 0
    last_assignment_date: Optional[date] = None
```

### NotificationQueue

```python
@dataclass
class NotificationQueue:
    id: Optional[int] = None
    target_type: str = ""  # person_dm, team_group, all_teams_group, email
    target_id: str = ""    # chat_id, email, or 'all'
    message: str = ""
    status: str = "pending"  # pending, sent, failed
    retries: int = 0
    created_at: str = ""
    sent_at: Optional[str] = None
```

### ScheduleResult

```python
@dataclass
class ScheduleResult:
    assignments: list[ShiftAssignment] = field(default_factory=list)
    unfilled_shifts: list[dict] = field(default_factory=list)
    substitutions: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    fairness_report: dict = field(default_factory=dict)
```

---

## Constants

### SHIFT_DEFINITIONS

```python
SHIFT_DEFINITIONS = {
    ShiftType.FIRST:  {"name": "1st", "start_hour": 6,  "end_hour": 14, "hours": 8},
    ShiftType.SECOND: {"name": "2nd", "start_hour": 14, "end_hour": 22, "hours": 8},
    ShiftType.THIRD:  {"name": "3rd", "start_hour": 22, "end_hour": 6,  "hours": 8},
}
```

### MAX_CONSECUTIVE

```python
MAX_CONSECUTIVE = {
    ShiftType.FIRST:  5,
    ShiftType.SECOND: 5,
    ShiftType.THIRD:  3,
}
```

### DEFAULT_PATTERNS

```python
DEFAULT_PATTERNS = {
    "2-shift": [1, 1, 2, 2, 0, 0],           # 6 days
    "3-shift": [1, 1, 2, 2, 0, 0, 3, 3, 0, 0], # 10 days
}
```

### SHIFT_MODELS

Centralized configuration for all shift models:

```python
SHIFT_MODELS = {
    "2-shift": {
        "name": "2-Shift (Day/Swing)",
        "pattern": [1, 1, 2, 2, 0, 0],
        "pattern_length": 6,
        "team_count": 3,
        "shifts": [ShiftType.FIRST, ShiftType.SECOND],
        "max_consecutive": {ShiftType.FIRST: 5, ShiftType.SECOND: 5},
    },
    "3-shift": {
        "name": "3-Shift (Day/Swing/Night)",
        "pattern": [1, 1, 2, 2, 0, 0, 3, 3, 0, 0],
        "pattern_length": 10,
        "team_count": 5,
        "shifts": [ShiftType.FIRST, ShiftType.SECOND, ShiftType.THIRD],
        "max_consecutive": {
            ShiftType.FIRST: 5,
            ShiftType.SECOND: 5,
            ShiftType.THIRD: 3,
        },
    },
}
```

**Usage:**
```python
from shiftcore import SHIFT_MODELS, RotationGroup

# Get model info
model = SHIFT_MODELS["3-shift"]
print(model["team_count"])  # 5
print(model["max_consecutive"][ShiftType.THIRD])  # 3

# Create rotation group with defaults
rotation = RotationGroup.create_default("My Rotation", "3-shift", date(2026, 1, 1))
```

### TEAM_COLORS

Default color palette for auto-assigned teams:

```python
TEAM_COLORS = [
    "#ef4444",  # Red - Team 1
    "#3b82f6",  # Blue - Team 2
    "#22c55e",  # Green - Team 3
    "#f59e0b",  # Amber - Team 4
    "#a855f7",  # Purple - Team 5
]
```

Used automatically when creating teams for a rotation group.

---

## Rotation Engine

### RotationEngine

```python
class RotationEngine:
    def __init__(self, rotation_group: RotationGroup):
        """Initialize with a rotation group."""

    def get_team_shift(self, team_offset: int, target_date: date) -> ShiftType:
        """Get shift type for a team at given offset on target date."""

    def get_all_team_shifts(self, team_offsets: list[int], target_date: date) -> dict[int, ShiftType]:
        """Get shifts for all teams on a specific date."""

    def get_team_schedule_for_period(self, team_offset: int, start_date: date, end_date: date) -> list[tuple[date, ShiftType]]:
        """Get full schedule for a team over a date range."""

    def get_rotation_schedule_for_period(self, team_offsets: list[int], start_date: date, end_date: date) -> dict[int, list[tuple[date, ShiftType]]]:
        """Get full schedule for all teams over a date range."""

    def get_off_teams(self, team_offsets: list[int], target_date: date) -> list[int]:
        """Get list of team offsets that are OFF on target date."""

    def get_on_shift_teams(self, team_offsets: list[int], target_date: date, shift_type: ShiftType) -> list[int]:
        """Get list of team offsets working a specific shift on target date."""

    def validate_pattern(self) -> tuple[bool, str]:
        """Validate rotation pattern is well-formed."""
```

### Convenience Functions

```python
def get_team_shift(rotation: RotationGroup, team_offset: int, target_date: date) -> ShiftType:
    """Convenience function to get team shift."""

def get_all_team_shifts(rotation: RotationGroup, team_offsets: list[int], target_date: date) -> dict[int, ShiftType]:
    """Convenience function to get all team shifts."""

def create_default_rotation_group(name: str, shift_model: str, cycle_start: date) -> RotationGroup:
    """Create a rotation group with default pattern for the shift model."""

def calculate_team_offsets(pattern_length: int, team_count: int) -> list[int]:
    """Calculate evenly distributed offsets for teams."""
```

---

## Constraints

### Individual Validators

```python
def check_one_shift_per_day(
    person_id: int,
    target_date: date,
    assignments: list[ShiftAssignment],
    exclude_assignment_id: Optional[int] = None,
) -> tuple[bool, str]:
    """Check person has at most 1 shift on target_date."""

def check_rest_hours(
    person_id: int,
    target_date: date,
    proposed_shift: ShiftType,
    assignments: list[ShiftAssignment],
    shift_defs: dict = None,
) -> tuple[bool, str]:
    """Check 12-hour rest between shifts."""

def check_max_consecutive(
    person_id: int,
    target_date: date,
    proposed_shift: ShiftType,
    assignments: list[ShiftAssignment],
    max_consecutive: dict = None,
) -> tuple[bool, str]:
    """Check max consecutive working days constraint."""

def check_availability(
    person_id: int,
    target_date: date,
    exceptions: list[AvailabilityException],
) -> tuple[bool, str]:
    """Check if person has availability exception on target date."""

def check_active_status(person: Person) -> tuple[bool, str]:
    """Check if person is active."""
```

### Combined Validation

```python
def validate_all_constraints(
    person: Person,
    target_date: date,
    proposed_shift: ShiftType,
    assignments: list[ShiftAssignment],
    exceptions: list[AvailabilityException],
    shift_defs: dict = None,
    max_consecutive: dict = None,
    exclude_assignment_id: Optional[int] = None,
) -> tuple[bool, str]:
    """Validate all constraints for a proposed assignment. Returns (is_valid, error_message)."""

def get_violations(
    person: Person,
    target_date: date,
    proposed_shift: ShiftType,
    assignments: list[ShiftAssignment],
    exceptions: list[AvailabilityException],
    shift_defs: dict = None,
    max_consecutive: dict = None,
    exclude_assignment_id: Optional[int] = None,
) -> list[str]:
    """Get list of all constraint violations (for detailed reporting)."""
```

---

## Fairness Engine

### FairnessEngine

```python
class FairnessEngine:
    def __init__(self, window_days: int = 28):
        """Initialize with rolling window size (default 28 days)."""

    def get_window_start(self, reference_date: date) -> date:
        """Calculate window start date for a reference date."""

    def get_window_end(self, window_start: date) -> date:
        """Calculate window end date from start."""

    def get_shift_counts(
        self,
        person_ids: list[int],
        window_start: date,
        window_end: date,
        assignments: list[ShiftAssignment],
    ) -> dict[int, int]:
        """Get shift counts for persons in the given window."""

    def get_last_assignment(
        self,
        person_id: int,
        window_end: date,
        assignments: list[ShiftAssignment],
    ) -> Optional[date]:
        """Get most recent assignment date for person before window_end."""

    def select_candidate(
        self,
        eligible_person_ids: list[int],
        reference_date: date,
        assignments: list[ShiftAssignment],
        counters: dict[int, PersonShiftCounter] = None,
    ) -> Optional[int]:
        """
        Select best candidate from eligible persons.
        Priority: 1) Fewest shifts in window, 2) Oldest last assignment.
        """

    def record_assignment(
        self,
        person_id: int,
        assignment_date: date,
        counters: dict[int, PersonShiftCounter],
    ) -> None:
        """Record an assignment in the fairness counters."""

    def get_fairness_report(
        self,
        person_ids: list[int],
        reference_date: date,
        assignments: list[ShiftAssignment],
        counters: dict[int, PersonShiftCounter] = None,
    ) -> dict:
        """Generate fairness report for all persons."""
```

---

## Scheduler

### generate_schedule

```python
def generate_schedule(
    rotation: RotationGroup,
    teams: list[Team],
    persons: list[Person],
    exceptions: list[AvailabilityException],
    existing_assignments: list[ShiftAssignment],
    start_date: date,
    end_date: date,
    shift_defs: dict = None,
    max_consecutive: dict = None,
    fairness_engine: FairnessEngine = None,
) -> ScheduleResult:
    """
    Generate complete schedule for date range.
    Returns ScheduleResult with assignments, unfilled, substitutions, conflicts, fairness_report.
    """
```

### find_substitute

```python
def find_substitute(
    rotation: RotationGroup,
    teams: list[Team],
    persons: list[Person],
    exceptions: list[AvailabilityException],
    assignments: list[ShiftAssignment],
    target_date: date,
    shift_type: ShiftType,
    exclude_person_ids: list[int],
    shift_defs: dict = None,
    max_consecutive: dict = None,
    fairness_engine: FairnessEngine = None,
) -> Optional[Person]:
    """
    Find eligible substitute from teams that are OFF on target_date.
    Returns best candidate per fairness, or None if none eligible.
    """
```

---

## Swaps

### validate_swap

```python
def validate_swap(
    person_a: Person,
    person_b: Person,
    target_date: date,
    shift_a: ShiftType,
    shift_b: ShiftType,
    assignments: list[ShiftAssignment],
    exceptions: list[AvailabilityException],
    shift_defs: dict = None,
    max_consecutive: dict = None,
) -> tuple[bool, str]:
    """
    Validate a proposed swap between two persons.
    Simulates the swap and checks all constraints for both persons.
    """
```

### get_swap_violations

```python
def get_swap_violations(
    person_a: Person,
    person_b: Person,
    target_date: date,
    shift_a: ShiftType,
    shift_b: ShiftType,
    assignments: list[ShiftAssignment],
    exceptions: list[AvailabilityException],
    shift_defs: dict = None,
    max_consecutive: dict = None,
) -> dict[str, list[str]]:
    """Get detailed violations for both persons in a proposed swap."""
```

---

## Notifications

### SMTPConfig

```python
@dataclass
class SMTPConfig:
    host: str = "smtp.gmail.com"
    port: int = 587
    username: str = ""
    password: str = ""
    from_email: str = "Shift Scheduler <noreply@localhost>"
    use_tls: bool = True
```

### NotificationService

```python
class NotificationService:
    def __init__(
        self,
        telegram_token: str = "",
        smtp_config: SMTPConfig = None,
        max_retries: int = 3,
        retry_delay: float = 5.0,
    ):
        """Initialize notification service."""

    def queue_notification(self, target_type: str, target_id: str, message: str) -> NotificationQueue:
        """Add notification to queue."""

    def queue_multiple(self, notifications: list[tuple[str, str, str]]) -> list[NotificationQueue]:
        """Queue multiple notifications at once."""

    async def process_queue(self, limit: int = 100) -> dict:
        """Process pending notifications with retry logic."""

    async def start_processor(self, interval: float = 30.0):
        """Start background queue processor."""

    def stop_processor(self):
        """Stop background queue processor."""

    def get_pending_count(self) -> int:
        """Get count of pending notifications."""

    def get_failed_notifications(self) -> list[NotificationQueue]:
        """Get failed notifications for manual retry."""

    def retry_failed(self, notification_ids: list[int] = None):
        """Reset failed notifications to pending for retry."""
```

### Message Templates

```python
def format_assignment_notification(person_name: str, date: str, shift: str, team: str) -> str:
    """Format new assignment notification."""

def format_substitution_notification(original_name: str, substitute_name: str, date: str, shift: str, team: str) -> str:
    """Format substitution notification."""

def format_swap_notification(person_a: str, shift_a: str, person_b: str, shift_b: str, date: str) -> str:
    """Format swap notification."""

def format_schedule_regenerated_notification(start_date: str, end_date: str, stats: dict) -> str:
    """Format schedule regenerated notification."""
```

---

## Storage

### SQLiteRepository

```python
class SQLiteRepository:
    def __init__(self, db_path: Path):
        """Initialize repository with database path."""

    # Rotation Group
    def get_rotation_group(self) -> Optional[RotationGroup]:
        """Get the active rotation group."""

    def get_rotation_group_by_id(self, group_id: int) -> Optional[RotationGroup]:
        """Get rotation group by ID."""

    def create_rotation_group(self, group: RotationGroup) -> int:
        """Create a new rotation group. Deactivates existing active group."""

    def update_rotation_group(self, group: RotationGroup) -> None:
        """Update rotation group."""

    def delete_rotation_group(self, group_id: int) -> None:
        """Delete rotation group."""

# Teams
    def get_teams(self, group_id: Optional[int] = None) -> list[Team]:
        """Get all teams, optionally filtered by rotation group."""

    def get_team(self, team_id: int) -> Optional[Team]:
        """Get team by ID."""

    def create_team(self, team: Team) -> int:
        """Create a new team."""

    def update_team(self, team: Team) -> None:
        """Update team."""

    def delete_team(self, team_id: int) -> None:
        """Delete team."""

    def create_teams_for_rotation_group(self, rotation_group_id: int) -> list[Team]:
        """Auto-create teams for a rotation group based on its shift model.
        Deletes existing teams for the group and creates new ones with correct offsets and colors."""

    def get_team_member_count(self, team_id: int) -> int:
        """Get the number of active persons assigned to a team."""

    def get_all_team_member_counts(
        self, group_id: Optional[int] = None
    ) -> dict[int, int]:
        """Get member counts for all teams, optionally filtered by rotation group."""

    # Persons
    def get_persons(self, team_id: Optional[int] = None, active_only: bool = True) -> list[Person]:
        """Get all persons, optionally filtered by team."""

    def get_person(self, person_id: int) -> Optional[Person]:
        """Get person by ID."""

    def create_person(self, person: Person) -> int:
        """Create a new person."""

    def update_person(self, person: Person) -> None:
        """Update person."""

    def delete_person(self, person_id: int) -> None:
        """Delete person."""

    # Availability Exceptions
    def get_exceptions(self, person_id: Optional[int] = None) -> list[AvailabilityException]:
        """Get availability exceptions."""

    def add_exception(self, exc: AvailabilityException) -> int:
        """Add availability exception."""

    def delete_exception(self, exception_id: int) -> None:
        """Delete availability exception."""

    def is_person_available(self, person_id: int, check_date: date) -> bool:
        """Check if person is available on given date."""

    # Shift Assignments
    def get_assignments(self, start_date: date, end_date: date) -> list[ShiftAssignment]:
        """Get shift assignments in date range."""

    def get_assignments_for_date(self, target_date: date) -> list[ShiftAssignment]:
        """Get assignments for a specific date."""

    def get_assignments_for_person(self, person_id: int, start_date: date, end_date: date) -> list[ShiftAssignment]:
        """Get assignments for a specific person in date range."""

    def save_assignment(self, assignment: ShiftAssignment) -> int:
        """Save or update a shift assignment."""

    def save_assignments(self, assignments: list[ShiftAssignment]) -> None:
        """Save multiple assignments in a transaction."""

    def clear_assignments(self, start_date: date, end_date: date) -> None:
        """Clear all assignments in date range."""

    def delete_assignment(self, assignment_id: int) -> None:
        """Delete a shift assignment."""

    # Shift Swaps
    def get_swaps(self, start_date: date, end_date: date) -> list[ShiftSwap]:
        """Get shift swaps in date range."""

    def save_swap(self, swap: ShiftSwap) -> int:
        """Save a shift swap."""

    def delete_swap(self, swap_id: int) -> None:
        """Delete a shift swap."""

    # Person Shift Counters
    def get_shift_counters(self, person_ids: list[int], period_start: date) -> dict[int, PersonShiftCounter]:
        """Get shift counters for persons in a period."""

    def save_shift_counter(self, counter: PersonShiftCounter) -> None:
        """Save or update a shift counter."""

    # Notifications
    def queue_notification(self, target_type: str, target_id: str, message: str) -> int:
        """Queue a notification."""

    def get_pending_notifications(self, limit: int = 100) -> list[NotificationQueue]:
        """Get pending notifications."""

    def mark_notification_sent(self, notification_id: int) -> None:
        """Mark notification as sent."""

    def mark_notification_failed(self, notification_id: int) -> None:
        """Mark notification as failed."""

    # Metadata
    def set_metadata(self, key: str, value: str) -> None:
        """Set metadata value."""

    def get_metadata(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get metadata value."""
```

---

## Exceptions

```python
class ShiftCoreError(Exception):
    """Base exception for shiftcore."""

class ConstraintViolation(ShiftCoreError):
    """Raised when a scheduling constraint is violated."""
    def __init__(self, message: str, constraint_type: str = "", person_id: int = 0, date: str = "")

class NoEligibleSubstitute(ShiftCoreError):
    """Raised when no eligible substitute can be found."""
    def __init__(self, message: str = "No eligible substitute found", date: str = "", shift_type: int = 0)

class NotificationFailed(ShiftCoreError):
    """Raised when notification delivery fails after retries."""
    def __init__(self, message: str, target_type: str = "", target_id: str = "", retries: int = 0)

class RotationError(ShiftCoreError):
    """Raised when rotation configuration is invalid."""
    def __init__(self, message: str, rotation_group_id: int = 0)

class StorageError(ShiftCoreError):
    """Raised when database operation fails."""
    def __init__(self, message: str, operation: str = "", table: str = "")

class ValidationError(ShiftCoreError):
    """Raised when input validation fails."""
    def __init__(self, message: str, field: str = "", value: str = "")
```

---

## Adapter Functions (`shiftcore_adapter.py`)

The adapter provides a simplified API for the desktop UI and adds utility functions:

### Team Management

```python
def create_teams_for_rotation_group(rotation_group_id: int) -> list[dict]:
    """Auto-create teams for a rotation group based on its shift model.
    Returns list of team dicts."""

def get_team_member_count(team_id: int) -> int:
    """Get the number of active persons assigned to a team."""

def get_all_team_member_counts(group_id: Optional[int] = None) -> dict[int, int]:
    """Get member counts for all teams, optionally filtered by rotation group."""

def get_shift_model_info(shift_model: str) -> dict:
    """Get information about a shift model from SHIFT_MODELS."""
```

### Person Management

```python
def create_person_unassigned(
    name: str,
    role: str = "operator",
    telegram_chat_id: str = None,
    email: str = None,
) -> int:
    """Create a new person without team assignment (team_id=0).
    Returns person ID. Assign to team later with assign_person_to_team()."""

def assign_person_to_team(person_id: int, team_id: int) -> None:
    """Assign an existing person to a team."""

def import_people_from_csv(csv_content: str) -> list[dict]:
    """Import people from CSV content.
    Expected columns: name, role, telegram, email
    Returns list of created person dicts with IDs."""

def generate_demo_people(count: int = 15) -> list[dict]:
    """Generate demo people for testing.
    Returns list of created person dicts with IDs."""
```

### Usage Examples

```python
from shiftcore_adapter import (
    create_teams_for_rotation_group,
    create_person_unassigned,
    assign_person_to_team,
    import_people_from_csv,
    generate_demo_people,
    get_shift_model_info,
)

# Auto-create teams for rotation group
teams = create_teams_for_rotation_group(rotation_group_id=1)
print(f"Created {len(teams)} teams")

# Create unassigned person, then assign
person_id = create_person_unassigned("John Doe", "lead", telegram_chat_id="12345")
assign_person_to_team(person_id, team_id=1)

# Import from CSV
csv_data = """name,role,telegram,email
Alice Smith,operator,user123,alice@example.com
Bob Jones,lead,user456,bob@example.com"""
imported = import_people_from_csv(csv_data)
print(f"Imported {len(imported)} people")

# Generate demo data
demo = generate_demo_people(20)
print(f"Generated {len(demo)} demo people")

# Get shift model info
info = get_shift_model_info("3-shift")
print(info["team_count"])  # 5
print(info["max_consecutive"])  # {1: 5, 2: 5, 3: 3}
```