"""
Shift Scheduler Core Logic
Handles rotation scheme, constraint validation, and schedule generation.
"""

from datetime import date, timedelta
from typing import Optional
from dataclasses import dataclass
from enum import IntEnum

from db import (
    get_teams, get_team, get_people, get_person, is_person_available,
    get_shift_assignments_for_date, get_shift_assignments, set_shift_assignment,
    clear_shift_assignments, get_availability_exceptions
)


class Shift(IntEnum):
    FIRST = 1   # 6:00 - 14:00
    SECOND = 2  # 14:00 - 22:00


@dataclass
class RotationState:
    """Represents where a team is in the rotation cycle."""
    day_in_cycle: int  # 0-5 (6-day cycle)
    # Day 0,1 -> 1st shift
    # Day 2,3 -> 2nd shift
    # Day 4,5 -> day off


def get_rotation_state(reference_date: date, cycle_start: date) -> RotationState:
    """Calculate rotation state for a given date relative to cycle start."""
    days_diff = (reference_date - cycle_start).days
    day_in_cycle = days_diff % 6
    return RotationState(day_in_cycle=day_in_cycle)


def get_team_shift_for_date(team_id: int, check_date: date, cycle_start: date) -> Optional[Shift]:
    """
    Determine which shift a team should work on a given date based on rotation.
    Returns None if the team is off that day.
    """
    # Get team's initial shift offset from database
    team = get_team(team_id)
    if not team:
        return None
    
    # Use the team's configured initial shift offset (default 0 = 1st shift start)
    # 0 = starts on 1st shift (days 0,1)
    # 2 = starts on 2nd shift (days 2,3)  
    # 4 = starts on off days (days 4,5)
    offset = team["initial_shift_offset"] if "initial_shift_offset" in team.keys() else 0
    
    state = get_rotation_state(check_date, cycle_start)
    adjusted_day = (state.day_in_cycle + offset) % 6
    
    if adjusted_day in (0, 1):
        return Shift.FIRST
    elif adjusted_day in (2, 3):
        return Shift.SECOND
    else:
        return None  # Day off


def get_team_schedule_for_period(team_id: int, start_date: date, end_date: date, cycle_start: date) -> list[tuple[date, Optional[Shift]]]:
    """Get the full schedule for a team over a date range."""
    schedule = []
    current = start_date
    while current <= end_date:
        shift = get_team_shift_for_date(team_id, current, cycle_start)
        schedule.append((current, shift))
        current += timedelta(days=1)
    return schedule


def get_shift_for_date_all_teams(check_date: date, cycle_start: date) -> dict[int, Optional[Shift]]:
    """Get shifts for all teams on a specific date."""
    teams = get_teams()
    return {
        t["id"]: get_team_shift_for_date(t["id"], check_date, cycle_start)
        for t in teams
    }


def validate_shift_constraints(
    person_id: int,
    check_date: date,
    proposed_shift: Shift,
    cycle_start: date
) -> tuple[bool, str]:
    """
    Validate all constraints for assigning a person to a shift.
    Returns (is_valid, error_message).
    """
    person = get_person(person_id)
    if not person:
        return False, "Person not found"
    
    if not person["active"]:
        return False, "Person is inactive"
    
    # Check availability exceptions
    if not is_person_available(person_id, check_date):
        return False, "Person has availability exception (unavailable)"
    
    # Check: 1st shift cannot follow 2nd shift on previous day
    if proposed_shift == Shift.FIRST:
        prev_date = check_date - timedelta(days=1)
        prev_assignments = get_shift_assignments_for_date(prev_date)
        for assignment in prev_assignments:
            if assignment["person_id"] == person_id and assignment["shift"] == Shift.SECOND:
                return False, f"Cannot work 1st shift after 2nd shift on previous day ({prev_date})"
    
    # Check: 2nd shift cannot precede 1st shift on next day
    if proposed_shift == Shift.SECOND:
        next_date = check_date + timedelta(days=1)
        next_assignments = get_shift_assignments_for_date(next_date)
        for assignment in next_assignments:
            if assignment["person_id"] == person_id and assignment["shift"] == Shift.FIRST:
                return False, f"Cannot work 2nd shift before 1st shift on next day ({next_date})"
    
    # Check: max 5 consecutive working days
    if not _check_max_consecutive_days(person_id, check_date, proposed_shift):
        return False, "Would exceed 5 consecutive working days limit"
    
    return True, ""


def _check_max_consecutive_days(person_id: int, check_date: date, proposed_shift: Shift) -> bool:
    """Check if adding this shift would exceed 5 consecutive working days."""
    # Look back up to 5 days to count consecutive working days
    consecutive = 0
    current = check_date - timedelta(days=1)
    
    for _ in range(5):
        assignments = get_shift_assignments_for_date(current)
        has_shift = any(a["person_id"] == person_id for a in assignments)
        if has_shift:
            consecutive += 1
            current -= timedelta(days=1)
        else:
            break
    
    # Look forward up to 5 days (excluding the proposed date)
    current = check_date + timedelta(days=1)
    for _ in range(5 - consecutive):
        assignments = get_shift_assignments_for_date(current)
        has_shift = any(a["person_id"] == person_id for a in assignments)
        if has_shift:
            consecutive += 1
            current += timedelta(days=1)
        else:
            break
    
    # Add the proposed shift
    consecutive += 1
    
    return consecutive <= 5


def find_available_substitutes(
    team_id: int,
    check_date: date,
    shift: Shift,
    exclude_person_ids: list[int],
    cycle_start: date
) -> list[dict]:
    """
    Find available people from the resting team to substitute.
    Returns list of dicts with person info and constraint check results.
    """
    # Determine which team is resting on this date
    team_shifts = get_shift_for_date_all_teams(check_date, cycle_start)
    resting_team_id = None
    for tid, s in team_shifts.items():
        if s is None:
            resting_team_id = tid
            break
    
    if resting_team_id is None:
        return []
    
    # Get all active people from resting team
    resting_people = get_people(resting_team_id, active_only=True)
    
    substitutes = []
    for person in resting_people:
        if person["id"] in exclude_person_ids:
            continue
        
        valid, error = validate_shift_constraints(person["id"], check_date, shift, cycle_start)
        substitutes.append({
            "person_id": person["id"],
            "name": person["name"],
            "team_id": resting_team_id,
            "role": person["role"],
            "valid": valid,
            "error": error
        })
    
    return substitutes


def generate_schedule(
    start_date: date,
    end_date: date,
    cycle_start: date,
    use_substitutes: bool = True
) -> dict:
    """
    Generate a complete schedule for the date range.
    Returns dict with assignments, conflicts, and substitutes needed.
    """
    clear_shift_assignments(start_date, end_date)
    
    teams = get_teams()
    team_ids = [t["id"] for t in teams]
    
    # Get all active people by team
    team_people = {}
    for tid in team_ids:
        team_people[tid] = get_people(tid, active_only=True)
    
    results = {
        "assignments": [],
        "conflicts": [],
        "substitutes_used": [],
        "unfilled_shifts": []
    }
    
    current = start_date
    while current <= end_date:
        team_shifts = get_shift_for_date_all_teams(current, cycle_start)
        
        for team_id in team_ids:
            shift = team_shifts.get(team_id)
            if shift is None:
                continue  # Team is off
            
            # Get default squad for this team
            squad = team_people.get(team_id, [])
            
            # Filter available people
            available = [p for p in squad if is_person_available(p["id"], current)]
            
            if not available:
                # No one available from default squad - need substitutes
                results["conflicts"].append({
                    "date": current.isoformat(),
                    "team_id": team_id,
                    "shift": shift,
                    "reason": "No available squad members"
                })
                
                if use_substitutes:
                    substitutes = find_available_substitutes(
                        team_id, current, shift, [], cycle_start
                    )
                    valid_subs = [s for s in substitutes if s["valid"]]
                    if valid_subs:
                        # Use first valid substitute
                        sub = valid_subs[0]
                        set_shift_assignment(
                            current, team_id, shift, sub["person_id"],
                            is_substitute=1, notes=f"Substitute from team {sub['team_id']}"
                        )
                        results["substitutes_used"].append({
                            "date": current.isoformat(),
                            "team_id": team_id,
                            "shift": shift,
                            "substitute_id": sub["person_id"],
                            "substitute_name": sub["name"],
                            "from_team": sub["team_id"]
                        })
                    else:
                        results["unfilled_shifts"].append({
                            "date": current.isoformat(),
                            "team_id": team_id,
                            "shift": shift
                        })
                continue
            
            # Assign first available person (could be enhanced with fairness)
            assigned = available[0]
            valid, error = validate_shift_constraints(assigned["id"], current, shift, cycle_start)
            
            if valid:
                set_shift_assignment(current, team_id, shift, assigned["id"])
                results["assignments"].append({
                    "date": current.isoformat(),
                    "team_id": team_id,
                    "shift": shift,
                    "person_id": assigned["id"],
                    "person_name": assigned["name"]
                })
            else:
                results["conflicts"].append({
                    "date": current.isoformat(),
                    "team_id": team_id,
                    "shift": shift,
                    "person_id": assigned["id"],
                    "person_name": assigned["name"],
                    "reason": error
                })
                
                # Try other available squad members
                assigned_alternative = False
                for alt in available[1:]:
                    valid_alt, _ = validate_shift_constraints(alt["id"], current, shift, cycle_start)
                    if valid_alt:
                        set_shift_assignment(current, team_id, shift, alt["id"])
                        results["assignments"].append({
                            "date": current.isoformat(),
                            "team_id": team_id,
                            "shift": shift,
                            "person_id": alt["id"],
                            "person_name": alt["name"]
                        })
                        assigned_alternative = True
                        break
                
                if not assigned_alternative and use_substitutes:
                    substitutes = find_available_substitutes(
                        team_id, current, shift, [p["id"] for p in available], cycle_start
                    )
                    valid_subs = [s for s in substitutes if s["valid"]]
                    if valid_subs:
                        sub = valid_subs[0]
                        set_shift_assignment(
                            current, team_id, shift, sub["person_id"],
                            is_substitute=1, notes=f"Substitute from team {sub['team_id']}"
                        )
                        results["substitutes_used"].append({
                            "date": current.isoformat(),
                            "team_id": team_id,
                            "shift": shift,
                            "substitute_id": sub["person_id"],
                            "substitute_name": sub["name"],
                            "from_team": sub["team_id"]
                        })
                    else:
                        results["unfilled_shifts"].append({
                            "date": current.isoformat(),
                            "team_id": team_id,
                            "shift": shift
                        })
        
        current += timedelta(days=1)
    
    return results


def get_schedule_grid(start_date: date, end_date: date, cycle_start: date) -> list[dict]:
    """Get a grid view of the schedule for display."""
    assignments = get_shift_assignments(start_date, end_date)
    
    # Build lookup
    assignment_map = {}
    for a in assignments:
        key = (a["schedule_date"], a["team_id"], a["shift"])
        assignment_map[key] = a
    
    grid = []
    current = start_date
    while current <= end_date:
        date_str = current.isoformat()
        team_shifts = get_shift_for_date_all_teams(current, cycle_start)
        
        row = {"date": date_str, "day_name": current.strftime("%A"), "teams": {}}
        
        for team_id in (1, 2, 3):
            shift = team_shifts.get(team_id)
            if shift is None:
                row["teams"][team_id] = {"shift": "OFF", "person": None, "is_sub": False}
            else:
                key = (date_str, team_id, shift)
                assignment = assignment_map.get(key)
                if assignment:
                    row["teams"][team_id] = {
                        "shift": "1st" if shift == 1 else "2nd",
                        "person": assignment["person_name"],
                        "person_id": assignment["person_id"],
                        "is_sub": bool(assignment["is_substitute"]),
                        "notes": assignment["notes"]
                    }
                else:
                    row["teams"][team_id] = {
                        "shift": "1st" if shift == 1 else "2nd",
                        "person": "UNASSIGNED",
                        "person_id": None,
                        "is_sub": False,
                        "notes": ""
                    }
        
        grid.append(row)
        current += timedelta(days=1)
    
    return grid


def get_person_schedule(person_id: int, start_date: date, end_date: date) -> list[dict]:
    """Get a person's schedule for a date range."""
    assignments = get_shift_assignments(start_date, end_date)
    person_assignments = [a for a in assignments if a["person_id"] == person_id]
    
    schedule = []
    for a in person_assignments:
        schedule.append({
            "date": a["schedule_date"],
            "team": a["team_name"],
            "shift": "1st" if a["shift"] == 1 else "2nd",
            "is_substitute": bool(a["is_substitute"]),
            "notes": a["notes"]
        })
    
    return sorted(schedule, key=lambda x: x["date"])