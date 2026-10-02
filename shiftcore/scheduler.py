"""
Main scheduler: generates schedules with constraints, fairness, and substitution.
"""

from datetime import date, timedelta
from typing import Optional
from .models import (
    RotationGroup,
    Team,
    Person,
    AvailabilityException,
    ShiftAssignment,
    ShiftType,
    ScheduleResult,
    SHIFT_DEFINITIONS,
    MAX_CONSECUTIVE,
)
from .rotation import RotationEngine
from .constraints import validate_all_constraints, get_violations
from .fairness import FairnessEngine
from .exceptions import NoEligibleSubstitute


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
    if shift_defs is None:
        shift_defs = SHIFT_DEFINITIONS
    if max_consecutive is None:
        max_consecutive = MAX_CONSECUTIVE
    if fairness_engine is None:
        fairness_engine = FairnessEngine()

    engine = RotationEngine(rotation)
    team_offsets = [t.offset for t in teams]

    # Get teams that are OFF on this date
    off_team_offsets = engine.get_off_teams(team_offsets, target_date)
    if not off_team_offsets:
        return None

    # Get persons from off-teams
    off_team_ids = [t.id for t in teams if t.offset in off_team_offsets]
    off_team_persons = [p for p in persons if p.team_id in off_team_ids and p.active]

    # Filter out excluded persons
    candidates = [p for p in off_team_persons if p.id not in exclude_person_ids]
    if not candidates:
        return None

    # Check constraints for each candidate
    eligible = []
    for person in candidates:
        valid, error = validate_all_constraints(
            person=person,
            target_date=target_date,
            proposed_shift=shift_type,
            assignments=assignments,
            exceptions=exceptions,
            shift_defs=shift_defs,
            max_consecutive=max_consecutive,
        )
        if valid:
            eligible.append(person)

    if not eligible:
        return None

    # Select best candidate by fairness
    eligible_ids = [p.id for p in eligible]
    best_id = fairness_engine.select_candidate(eligible_ids, target_date, assignments)

    if best_id is None:
        return eligible[0]  # fallback

    return next(p for p in eligible if p.id == best_id)


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
    if shift_defs is None:
        shift_defs = SHIFT_DEFINITIONS
    if max_consecutive is None:
        max_consecutive = MAX_CONSECUTIVE
    if fairness_engine is None:
        fairness_engine = FairnessEngine()

    engine = RotationEngine(rotation)
    team_offsets = [t.offset for t in teams]
    team_by_offset = {t.offset: t for t in teams}
    person_by_id = {p.id: p for p in persons}

    # Initialize fairness counters from existing assignments
    counters = {}
    for assignment in existing_assignments:
        fairness_engine.record_assignment(
            assignment.person_id, assignment.schedule_date, counters
        )

    result = ScheduleResult()
    all_assignments = list(existing_assignments)  # working copy

    current = start_date
    while current <= end_date:
        # Get shifts for all teams on this date
        team_shifts = engine.get_all_team_shifts(team_offsets, current)

        for offset, shift_type in team_shifts.items():
            if shift_type == ShiftType.OFF:
                continue

            team = team_by_offset[offset]

            # Get active persons from this team
            team_persons = [p for p in persons if p.team_id == team.id and p.active]

            # Filter available (no exceptions)
            available = [
                p
                for p in team_persons
                if not any(
                    e.covers_date(current) for e in exceptions if e.person_id == p.id
                )
            ]

            if not available:
                # No one available from default team - need substitute
                result.conflicts.append(
                    {
                        "date": current.isoformat(),
                        "team_id": team.id,
                        "team_name": team.name,
                        "shift": shift_type.name,
                        "reason": "No available team members",
                    }
                )

                # Try substitution
                exclude_ids = [p.id for p in team_persons]
                substitute = find_substitute(
                    rotation,
                    teams,
                    persons,
                    exceptions,
                    all_assignments,
                    current,
                    shift_type,
                    exclude_ids,
                    shift_defs,
                    max_consecutive,
                    fairness_engine,
                )

                if substitute:
                    assignment = ShiftAssignment(
                        schedule_date=current,
                        shift_type=shift_type,
                        person_id=substitute.id,
                        team_id=team.id,
                        is_substitute=True,
                        substitute_for_id=None,  # No specific person to substitute for
                        notes=f"Substitute from team {substitute.team_id}",
                    )
                    all_assignments.append(assignment)
                    result.assignments.append(assignment)
                    result.substitutions.append(
                        {
                            "date": current.isoformat(),
                            "team_id": team.id,
                            "team_name": team.name,
                            "shift": shift_type.name,
                            "substitute_id": substitute.id,
                            "substitute_name": substitute.name,
                            "from_team_id": substitute.team_id,
                        }
                    )
                    fairness_engine.record_assignment(substitute.id, current, counters)
                else:
                    result.unfilled_shifts.append(
                        {
                            "date": current.isoformat(),
                            "team_id": team.id,
                            "team_name": team.name,
                            "shift": shift_type.name,
                        }
                    )
                continue

            # Check constraints for each available person
            eligible = []
            for person in available:
                valid, error = validate_all_constraints(
                    person=person,
                    target_date=current,
                    proposed_shift=shift_type,
                    assignments=all_assignments,
                    exceptions=exceptions,
                    shift_defs=shift_defs,
                    max_consecutive=max_consecutive,
                )
                if valid:
                    eligible.append(person)
                else:
                    result.conflicts.append(
                        {
                            "date": current.isoformat(),
                            "team_id": team.id,
                            "team_name": team.name,
                            "shift": shift_type.name,
                            "person_id": person.id,
                            "person_name": person.name,
                            "reason": error,
                        }
                    )

            if not eligible:
                # No eligible from team - try substitution
                exclude_ids = [p.id for p in available]
                substitute = find_substitute(
                    rotation,
                    teams,
                    persons,
                    exceptions,
                    all_assignments,
                    current,
                    shift_type,
                    exclude_ids,
                    shift_defs,
                    max_consecutive,
                    fairness_engine,
                )

                if substitute:
                    assignment = ShiftAssignment(
                        schedule_date=current,
                        shift_type=shift_type,
                        person_id=substitute.id,
                        team_id=team.id,
                        is_substitute=True,
                        substitute_for_id=None,
                        notes=f"Substitute from team {substitute.team_id}",
                    )
                    all_assignments.append(assignment)
                    result.assignments.append(assignment)
                    result.substitutions.append(
                        {
                            "date": current.isoformat(),
                            "team_id": team.id,
                            "team_name": team.name,
                            "shift": shift_type.name,
                            "substitute_id": substitute.id,
                            "substitute_name": substitute.name,
                            "from_team_id": substitute.team_id,
                        }
                    )
                    fairness_engine.record_assignment(substitute.id, current, counters)
                else:
                    result.unfilled_shifts.append(
                        {
                            "date": current.isoformat(),
                            "team_id": team.id,
                            "team_name": team.name,
                            "shift": shift_type.name,
                        }
                    )
                continue

            # Select best candidate by fairness
            eligible_ids = [p.id for p in eligible]
            best_id = fairness_engine.select_candidate(
                eligible_ids, current, all_assignments, counters
            )

            if best_id is None:
                best_person = eligible[0]
            else:
                best_person = next(p for p in eligible if p.id == best_id)

            # Assign
            assignment = ShiftAssignment(
                schedule_date=current,
                shift_type=shift_type,
                person_id=best_person.id,
                team_id=team.id,
                is_substitute=False,
            )
            all_assignments.append(assignment)
            result.assignments.append(assignment)
            fairness_engine.record_assignment(best_person.id, current, counters)

        current += timedelta(days=1)

    # Generate fairness report
    all_person_ids = [p.id for p in persons if p.active]
    result.fairness_report = fairness_engine.get_fairness_report(
        all_person_ids, end_date, all_assignments, counters
    )

    return result
