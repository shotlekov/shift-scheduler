"""
Constraint validators for shift scheduling.
Enforces: 1 shift/day, 12h rest, max consecutive shifts, availability.
"""

from datetime import date, time, timedelta
from typing import Optional
from .models import (
    ShiftAssignment,
    AvailabilityException,
    Person,
    ShiftType,
    SHIFT_DEFINITIONS,
    MAX_CONSECUTIVE,
)
from .exceptions import ConstraintViolation


def check_one_shift_per_day(
    person_id: int,
    target_date: date,
    assignments: list[ShiftAssignment],
    exclude_assignment_id: Optional[int] = None,
) -> tuple[bool, str]:
    """Check person has at most 1 shift on target_date."""
    for assignment in assignments:
        # Only skip if exclude_assignment_id is explicitly set and matches
        if exclude_assignment_id is not None and assignment.id == exclude_assignment_id:
            continue
        if (
            assignment.person_id == person_id
            and assignment.schedule_date == target_date
        ):
            return (
                False,
                f"Person already assigned to {assignment.shift_type.name} shift on {target_date}",
            )
    return True, ""


def check_rest_hours(
    person_id: int,
    target_date: date,
    proposed_shift: ShiftType,
    assignments: list[ShiftAssignment],
    shift_defs: dict = None,
) -> tuple[bool, str]:
    """
    Check 12-hour rest between shifts.
    - No 1st shift after 2nd shift previous day (8h rest)
    - No 2nd shift before 1st shift next day (8h rest)
    - No 1st shift after 3rd shift previous day (8h rest)
    - No 3rd shift before 1st shift next day (8h rest)
    """
    if shift_defs is None:
        shift_defs = SHIFT_DEFINITIONS

    proposed_def = shift_defs.get(proposed_shift)
    if not proposed_def:
        return True, ""

    proposed_start_hour = proposed_def["start_hour"]

    # Check previous day
    prev_date = target_date - timedelta(days=1)
    for assignment in assignments:
        if assignment.person_id != person_id or assignment.schedule_date != prev_date:
            continue

        prev_def = shift_defs.get(assignment.shift_type)
        if not prev_def:
            continue

        prev_end_hour = prev_def["end_hour"]

        # Calculate rest hours between previous shift end and proposed shift start
        if assignment.shift_type == ShiftType.THIRD:
            # 3rd shift: 22:00 (prev_date) to 06:00 (target_date)
            # Ends at 06:00 on target_date
            # Rest = proposed_start_hour - 6 (if >= 6) or proposed_start_hour + 18 (if < 6)
            if proposed_start_hour >= 6:
                rest_hours = proposed_start_hour - 6
            else:
                rest_hours = proposed_start_hour + 18
        else:
            # Normal shift: ends on same day at prev_end_hour
            # Rest = (proposed_start_hour + 24) - prev_end_hour
            rest_hours = proposed_start_hour + 24 - prev_end_hour

        if rest_hours < 12:
            return False, (
                f"Insufficient rest: {rest_hours}h between "
                f"{assignment.shift_type.name} shift on {prev_date} "
                f"and {proposed_shift.name} shift on {target_date}"
            )

    # Check next day
    next_date = target_date + timedelta(days=1)
    for assignment in assignments:
        if assignment.person_id != person_id or assignment.schedule_date != next_date:
            continue

        next_def = shift_defs.get(assignment.shift_type)
        if not next_def:
            continue

        next_start_hour = next_def["start_hour"]

        # Calculate rest hours between proposed shift end and next shift start
        if proposed_shift == ShiftType.THIRD:
            # 3rd shift: 22:00 (target_date) to 06:00 (next_date)
            # Ends at 06:00 on next_date
            # Rest = next_start_hour - 6 (if >= 6) or next_start_hour + 18 (if < 6)
            if next_start_hour >= 6:
                rest_hours = next_start_hour - 6
            else:
                rest_hours = next_start_hour + 18
        else:
            proposed_end_hour = proposed_def["end_hour"]
            rest_hours = next_start_hour + 24 - proposed_end_hour

        if rest_hours < 12:
            return False, (
                f"Insufficient rest: {rest_hours}h between "
                f"{proposed_shift.name} shift on {target_date} "
                f"and {assignment.shift_type.name} shift on {next_date}"
            )

    return True, ""


def check_max_consecutive(
    person_id: int,
    target_date: date,
    proposed_shift: ShiftType,
    assignments: list[ShiftAssignment],
    max_consecutive: dict = None,
) -> tuple[bool, str]:
    """
    Check max consecutive working days constraint.
    Counts consecutive days with ANY shift assignment.
    """
    if max_consecutive is None:
        max_consecutive = MAX_CONSECUTIVE

    max_allowed = max_consecutive.get(proposed_shift, 5)

    # Count consecutive days backward
    consecutive = 0
    current = target_date - timedelta(days=1)

    for _ in range(max_allowed):
        has_shift = any(
            a.person_id == person_id and a.schedule_date == current for a in assignments
        )
        if has_shift:
            consecutive += 1
            current -= timedelta(days=1)
        else:
            break

    # Count consecutive days forward (excluding proposed date)
    current = target_date + timedelta(days=1)
    for _ in range(max_allowed - consecutive):
        has_shift = any(
            a.person_id == person_id and a.schedule_date == current for a in assignments
        )
        if has_shift:
            consecutive += 1
            current += timedelta(days=1)
        else:
            break

    # Add proposed shift
    consecutive += 1

    if consecutive > max_allowed:
        return False, (
            f"Would exceed max {max_allowed} consecutive shifts "
            f"({consecutive} consecutive including this assignment)"
        )

    return True, ""


def check_availability(
    person_id: int,
    target_date: date,
    exceptions: list[AvailabilityException],
) -> tuple[bool, str]:
    """Check if person has availability exception on target date."""
    for exc in exceptions:
        if exc.person_id == person_id and exc.covers_date(target_date):
            return (
                False,
                f"Person unavailable: {exc.reason} ({exc.start_date} to {exc.end_date})",
            )
    return True, ""


def check_active_status(person: Person) -> tuple[bool, str]:
    """Check if person is active."""
    if not person.active:
        return False, "Person is inactive"
    return True, ""


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
    """
    Validate all constraints for a proposed assignment.
    Returns (is_valid, error_message).
    """
    # Check active status
    valid, error = check_active_status(person)
    if not valid:
        return False, error

    # Check availability
    valid, error = check_availability(person.id, target_date, exceptions)
    if not valid:
        return False, error

    # Check one shift per day
    valid, error = check_one_shift_per_day(
        person.id, target_date, assignments, exclude_assignment_id
    )
    if not valid:
        return False, error

    # Check rest hours
    valid, error = check_rest_hours(
        person.id, target_date, proposed_shift, assignments, shift_defs
    )
    if not valid:
        return False, error

    # Check max consecutive
    valid, error = check_max_consecutive(
        person.id, target_date, proposed_shift, assignments, max_consecutive
    )
    if not valid:
        return False, error

    return True, ""


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
    violations = []

    valid, error = check_active_status(person)
    if not valid:
        violations.append(error)

    valid, error = check_availability(person.id, target_date, exceptions)
    if not valid:
        violations.append(error)

    valid, error = check_one_shift_per_day(
        person.id, target_date, assignments, exclude_assignment_id
    )
    if not valid:
        violations.append(error)

    valid, error = check_rest_hours(
        person.id, target_date, proposed_shift, assignments, shift_defs
    )
    if not valid:
        violations.append(error)

    valid, error = check_max_consecutive(
        person.id, target_date, proposed_shift, assignments, max_consecutive
    )
    if not valid:
        violations.append(error)

    return violations
