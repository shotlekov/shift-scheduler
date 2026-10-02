# shiftcore - Shift Scheduling Core Library

"""
Core scheduling logic for shift management.
Pure Python package with no UI dependencies.
"""

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
)
from .rotation import (
    get_team_shift,
    get_all_team_shifts,
    RotationEngine,
)
from .constraints import (
    validate_all_constraints,
    check_one_shift_per_day,
    check_rest_hours,
    check_max_consecutive,
    get_violations,
)
from .fairness import FairnessEngine
from .scheduler import (
    generate_schedule,
    find_substitute,
    ScheduleResult,
)
from .swaps import validate_swap, get_swap_violations
from .notifications import NotificationService, SMTPConfig
from .storage import SQLiteRepository
from .exceptions import (
    ConstraintViolation,
    NoEligibleSubstitute,
    NotificationFailed,
    RotationError,
)

__version__ = "0.1.0"
__all__ = [
    # Models
    "RotationGroup",
    "Team",
    "Person",
    "AvailabilityException",
    "ShiftAssignment",
    "ShiftSwap",
    "PersonShiftCounter",
    "NotificationQueue",
    "ShiftType",
    # Rotation
    "get_team_shift",
    "get_all_team_shifts",
    "RotationEngine",
    # Constraints
    "validate_all_constraints",
    "check_one_shift_per_day",
    "check_rest_hours",
    "check_max_consecutive",
    # Fairness
    "FairnessEngine",
    # Scheduler
    "generate_schedule",
    "find_substitute",
    "ScheduleResult",
    # Swaps
    "validate_swap",
    "get_swap_violations",
    # Notifications
    "NotificationService",
    "SMTPConfig",
    # Storage
    "SQLiteRepository",
    # Exceptions
    "ConstraintViolation",
    "NoEligibleSubstitute",
    "NotificationFailed",
    "RotationError",
]
