"""
Shift swap validation.
"""

from datetime import date
from typing import Optional
from .models import (
    Person,
    ShiftAssignment,
    ShiftSwap,
    AvailabilityException,
    ShiftType,
    SHIFT_DEFINITIONS,
    MAX_CONSECUTIVE,
)
from .constraints import validate_all_constraints


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
    if shift_defs is None:
        shift_defs = SHIFT_DEFINITIONS
    if max_consecutive is None:
        max_consecutive = MAX_CONSECUTIVE

    # Check both persons are active
    if not person_a.active:
        return False, f"Person A ({person_a.name}) is inactive"
    if not person_b.active:
        return False, f"Person B ({person_b.name}) is inactive"

    # Check availability for both
    for exc in exceptions:
        if exc.person_id == person_a.id and exc.covers_date(target_date):
            return False, f"Person A ({person_a.name}) unavailable: {exc.reason}"
        if exc.person_id == person_b.id and exc.covers_date(target_date):
            return False, f"Person B ({person_b.name}) unavailable: {exc.reason}"

    # Create simulated assignments after swap
    # Remove existing assignments for these persons on target_date
    simulated_assignments = [
        a
        for a in assignments
        if not (
            a.person_id in (person_a.id, person_b.id) and a.schedule_date == target_date
        )
    ]

    # Add swapped assignments with temporary IDs for exclusion
    # Use negative IDs to avoid collision with real assignment IDs
    person_a_assignment = ShiftAssignment(
        id=-1,  # Temporary ID for exclusion
        schedule_date=target_date,
        shift_type=shift_b,  # person_a gets shift_b
        person_id=person_a.id,
        team_id=person_a.team_id,
    )
    person_b_assignment = ShiftAssignment(
        id=-2,  # Temporary ID for exclusion
        schedule_date=target_date,
        shift_type=shift_a,  # person_b gets shift_a
        person_id=person_b.id,
        team_id=person_b.team_id,
    )
    simulated_assignments.append(person_a_assignment)
    simulated_assignments.append(person_b_assignment)

    # Validate constraints for person_a with shift_b
    # Exclude the simulated assignment for person_a from one-shift-per-day check
    valid, error = validate_all_constraints(
        person=person_a,
        target_date=target_date,
        proposed_shift=shift_b,
        assignments=simulated_assignments,
        exceptions=exceptions,
        shift_defs=shift_defs,
        max_consecutive=max_consecutive,
        exclude_assignment_id=-1,  # Exclude person_a's simulated assignment
    )
    if not valid:
        return False, f"Person A ({person_a.name}): {error}"

    # Validate constraints for person_b with shift_a
    # Exclude the simulated assignment for person_b from one-shift-per-day check
    valid, error = validate_all_constraints(
        person=person_b,
        target_date=target_date,
        proposed_shift=shift_a,
        assignments=simulated_assignments,
        exceptions=exceptions,
        shift_defs=shift_defs,
        max_consecutive=max_consecutive,
        exclude_assignment_id=-2,  # Exclude person_b's simulated assignment
    )
    if not valid:
        return False, f"Person B ({person_b.name}): {error}"

    return True, ""


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
    from .constraints import get_violations

    if shift_defs is None:
        shift_defs = SHIFT_DEFINITIONS
    if max_consecutive is None:
        max_consecutive = MAX_CONSECUTIVE

    # Create simulated assignments with temporary IDs for exclusion
    simulated_assignments = [
        a
        for a in assignments
        if not (
            a.person_id in (person_a.id, person_b.id) and a.schedule_date == target_date
        )
    ]
    simulated_assignments.append(
        ShiftAssignment(
            id=-1,
            schedule_date=target_date,
            shift_type=shift_b,
            person_id=person_a.id,
            team_id=person_a.team_id,
        )
    )
    simulated_assignments.append(
        ShiftAssignment(
            id=-2,
            schedule_date=target_date,
            shift_type=shift_a,
            person_id=person_b.id,
            team_id=person_b.team_id,
        )
    )

    violations_a = get_violations(
        person_a,
        target_date,
        shift_b,
        simulated_assignments,
        exceptions,
        shift_defs,
        max_consecutive,
        exclude_assignment_id=-1,
    )
    violations_b = get_violations(
        person_b,
        target_date,
        shift_a,
        simulated_assignments,
        exceptions,
        shift_defs,
        max_consecutive,
        exclude_assignment_id=-2,
    )

    return {
        "person_a": violations_a,
        "person_b": violations_b,
    }
