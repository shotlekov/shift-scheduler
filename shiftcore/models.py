"""
Data models for shift scheduling.
Pure Python dataclasses with no external dependencies.
"""

from dataclasses import dataclass, field
from datetime import date, time
from enum import IntEnum
from typing import Optional
import json


class ShiftType(IntEnum):
    """Shift type enumeration."""

    OFF = 0
    FIRST = 1  # 06:00-14:00
    SECOND = 2  # 14:00-22:00
    THIRD = 3  # 22:00-06:00 (crosses midnight)


# Shift model configurations
SHIFT_MODELS = {
    "2-shift": {
        "name": "2-Shift (Day/Swing)",
        "pattern": [1, 1, 2, 2, 0, 0],  # 6 days: 1st, 1st, 2nd, 2nd, off, off
        "pattern_length": 6,
        "team_count": 3,
        "shifts": [ShiftType.FIRST, ShiftType.SECOND],
        "max_consecutive": {ShiftType.FIRST: 5, ShiftType.SECOND: 5},
    },
    "3-shift": {
        "name": "3-Shift (Day/Swing/Night)",
        "pattern": [
            1,
            1,
            2,
            2,
            0,
            0,
            3,
            3,
            0,
            0,
        ],  # 10 days: 1st, 1st, 2nd, 2nd, off, off, 3rd, 3rd, off, off
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


# Default team colors (auto-assigned)
TEAM_COLORS = [
    "#ef4444",  # Red - Team 1
    "#3b82f6",  # Blue - Team 2
    "#22c55e",  # Green - Team 3
    "#f59e0b",  # Amber - Team 4
    "#a855f7",  # Purple - Team 5
]


@dataclass
class RotationGroup:
    """Rotation group configuration."""

    id: Optional[int] = None
    name: str = ""
    shift_model: str = "2-shift"  # "2-shift" or "3-shift"
    pattern: list[int] = field(default_factory=list)  # e.g., [1,1,2,2,0,0]
    cycle_start_date: date = field(default_factory=date.today)
    active: bool = True
    created_at: str = ""

    def __post_init__(self):
        if isinstance(self.pattern, str):
            self.pattern = json.loads(self.pattern)
        if isinstance(self.cycle_start_date, str):
            self.cycle_start_date = date.fromisoformat(self.cycle_start_date)

    @property
    def pattern_length(self) -> int:
        return len(self.pattern)

    def get_shift_for_offset(self, offset: int, target_date: date) -> ShiftType:
        """Get shift type for a team at given offset on target date."""
        if not self.pattern:
            return ShiftType.OFF
        days_diff = (target_date - self.cycle_start_date).days
        pattern_index = (days_diff + offset) % self.pattern_length
        return ShiftType(self.pattern[pattern_index])

    @classmethod
    def create_default(
        cls, name: str, shift_model: str, cycle_start: date
    ) -> "RotationGroup":
        """Create a rotation group with default pattern for the shift model."""
        if shift_model not in SHIFT_MODELS:
            raise ValueError(f"Unknown shift model: {shift_model}")
        model = SHIFT_MODELS[shift_model]
        return cls(
            name=name,
            shift_model=shift_model,
            pattern=model["pattern"],
            cycle_start_date=cycle_start,
            active=True,
        )

    def get_team_count(self) -> int:
        """Get the required number of teams for this shift model."""
        return SHIFT_MODELS[self.shift_model]["team_count"]

    def get_shifts(self) -> list[ShiftType]:
        """Get the shift types used in this model."""
        return SHIFT_MODELS[self.shift_model]["shifts"]

    def get_max_consecutive(self) -> dict[ShiftType, int]:
        """Get max consecutive shifts per shift type."""
        return SHIFT_MODELS[self.shift_model]["max_consecutive"]


@dataclass
class Team:
    """Team within a rotation group."""

    id: Optional[int] = None
    name: str = ""
    color: str = "#2563eb"
    rotation_group_id: int = 0
    offset: int = 0  # Pattern index offset (0..pattern_length-1)
    created_at: str = ""

    def get_shift_for_date(
        self, rotation: RotationGroup, target_date: date
    ) -> ShiftType:
        """Get this team's shift for a specific date."""
        return rotation.get_shift_for_offset(self.offset, target_date)


@dataclass
class Person:
    """Person/operator."""

    id: Optional[int] = None
    name: str = ""
    team_id: int = 0
    role: str = "operator"
    active: bool = True
    telegram_chat_id: Optional[str] = None
    email: Optional[str] = None
    created_at: str = ""


@dataclass
class AvailabilityException:
    """Availability exception (sick, vacation, etc.)."""

    id: Optional[int] = None
    person_id: int = 0
    start_date: date = field(default_factory=date.today)
    end_date: date = field(default_factory=date.today)
    reason: str = ""
    created_at: str = ""

    def __post_init__(self):
        if isinstance(self.start_date, str):
            self.start_date = date.fromisoformat(self.start_date)
        if isinstance(self.end_date, str):
            self.end_date = date.fromisoformat(self.end_date)

    def covers_date(self, check_date: date) -> bool:
        """Check if this exception covers the given date."""
        return self.start_date <= check_date <= self.end_date


@dataclass
class ShiftAssignment:
    """Shift assignment for a person on a specific date."""

    id: Optional[int] = None
    schedule_date: date = field(default_factory=date.today)
    shift_type: ShiftType = ShiftType.FIRST
    person_id: int = 0
    team_id: int = 0
    is_substitute: bool = False
    substitute_for_id: Optional[int] = None
    notes: str = ""
    created_at: str = ""

    def __post_init__(self):
        if isinstance(self.schedule_date, str):
            self.schedule_date = date.fromisoformat(self.schedule_date)
        if isinstance(self.shift_type, int):
            self.shift_type = ShiftType(self.shift_type)


@dataclass
class ShiftSwap:
    """Shift swap between two persons."""

    id: Optional[int] = None
    schedule_date: date = field(default_factory=date.today)
    person_a_id: int = 0
    person_b_id: int = 0
    shift_a: ShiftType = ShiftType.FIRST
    shift_b: ShiftType = ShiftType.SECOND
    approved: bool = True
    created_at: str = ""

    def __post_init__(self):
        if isinstance(self.schedule_date, str):
            self.schedule_date = date.fromisoformat(self.schedule_date)
        if isinstance(self.shift_a, int):
            self.shift_a = ShiftType(self.shift_a)
        if isinstance(self.shift_b, int):
            self.shift_b = ShiftType(self.shift_b)


@dataclass
class PersonShiftCounter:
    """Fairness counter for a person in a rolling window."""

    person_id: int = 0
    period_start: date = field(default_factory=date.today)
    shift_count: int = 0
    last_assignment_date: Optional[date] = None

    def __post_init__(self):
        if isinstance(self.period_start, str):
            self.period_start = date.fromisoformat(self.period_start)
        if self.last_assignment_date and isinstance(self.last_assignment_date, str):
            self.last_assignment_date = date.fromisoformat(self.last_assignment_date)


@dataclass
class NotificationQueue:
    """Queued notification for delivery."""

    id: Optional[int] = None
    target_type: str = ""  # person_dm, team_group, all_teams_group, email
    target_id: str = ""  # chat_id, email, or 'all'
    message: str = ""
    status: str = "pending"  # pending, sent, failed
    retries: int = 0
    created_at: str = ""
    sent_at: Optional[str] = None


@dataclass
class ScheduleResult:
    """Result of schedule generation."""

    assignments: list[ShiftAssignment] = field(default_factory=list)
    unfilled_shifts: list[dict] = field(default_factory=list)
    substitutions: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    fairness_report: dict = field(default_factory=dict)


@dataclass
class BaseSchedule:
    """Immutable base schedule entry - rotation pattern only."""

    id: Optional[int] = None
    schedule_date: date = field(default_factory=date.today)
    team_id: int = 0
    shift_type: ShiftType = ShiftType.OFF
    cycle_start_date: date = field(default_factory=date.today)
    version: int = 1
    created_at: str = ""

    def __post_init__(self):
        if isinstance(self.schedule_date, str):
            self.schedule_date = date.fromisoformat(self.schedule_date)
        if isinstance(self.cycle_start_date, str):
            self.cycle_start_date = date.fromisoformat(self.cycle_start_date)
        if isinstance(self.shift_type, int):
            self.shift_type = ShiftType(self.shift_type)


@dataclass
class ScheduleOverlay:
    """Dynamic overlay on base schedule - substitutions, swaps, exceptions."""

    id: Optional[int] = None
    base_schedule_id: int = 0
    overlay_type: str = ""  # substitution, swap, exception, manual
    person_id: Optional[int] = None
    original_person_id: Optional[int] = None
    status: str = "active"  # active, cancelled, expired
    created_at: str = ""
    expires_at: Optional[date] = None

    def __post_init__(self):
        if self.expires_at and isinstance(self.expires_at, str):
            self.expires_at = date.fromisoformat(self.expires_at)


@dataclass
class ScheduleVersion:
    """Schedule version tracking for model changes."""

    version: int = 0
    shift_model: str = "2-shift"
    cycle_start_date: date = field(default_factory=date.today)
    team_count: int = 0
    created_at: str = ""
    is_active: bool = True

    def __post_init__(self):
        if isinstance(self.cycle_start_date, str):
            self.cycle_start_date = date.fromisoformat(self.cycle_start_date)


# Shift definitions (hours)
SHIFT_DEFINITIONS = {
    ShiftType.FIRST: {"name": "1st", "start_hour": 6, "end_hour": 14, "hours": 8},
    ShiftType.SECOND: {"name": "2nd", "start_hour": 14, "end_hour": 22, "hours": 8},
    ShiftType.THIRD: {
        "name": "3rd",
        "start_hour": 22,
        "end_hour": 6,
        "hours": 8,
    },  # crosses midnight
}

# Max consecutive shifts per shift type (defaults, overridden by shift model)
MAX_CONSECUTIVE = {
    ShiftType.FIRST: 5,
    ShiftType.SECOND: 5,
    ShiftType.THIRD: 3,
}

# Default patterns (legacy, use SHIFT_MODELS instead)
DEFAULT_PATTERNS = {
    "2-shift": [1, 1, 2, 2, 0, 0],  # 6 days
    "3-shift": [1, 1, 2, 2, 0, 0, 3, 3, 0, 0],  # 10 days
}
