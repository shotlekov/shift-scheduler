"""
Rotation engine for calculating team shifts based on patterns.
"""

from datetime import date, timedelta
from typing import Optional
from .models import RotationGroup, Team, ShiftType, DEFAULT_PATTERNS


class RotationEngine:
    """Engine for computing team shifts from rotation patterns."""

    def __init__(self, rotation_group: RotationGroup):
        self.rotation = rotation_group
        if not self.rotation.pattern:
            self.rotation.pattern = DEFAULT_PATTERNS.get(self.rotation.shift_model, [])

    def get_team_shift(self, team_offset: int, target_date: date) -> ShiftType:
        """Get shift type for a team at given offset on target date."""
        return self.rotation.get_shift_for_offset(team_offset, target_date)

    def get_all_team_shifts(
        self, team_offsets: list[int], target_date: date
    ) -> dict[int, ShiftType]:
        """Get shifts for all teams on a specific date."""
        return {
            offset: self.get_team_shift(offset, target_date) for offset in team_offsets
        }

    def get_team_schedule_for_period(
        self, team_offset: int, start_date: date, end_date: date
    ) -> list[tuple[date, ShiftType]]:
        """Get full schedule for a team over a date range."""
        schedule = []
        current = start_date
        while current <= end_date:
            shift = self.get_team_shift(team_offset, current)
            schedule.append((current, shift))
            current += timedelta(days=1)
        return schedule

    def get_rotation_schedule_for_period(
        self, team_offsets: list[int], start_date: date, end_date: date
    ) -> dict[int, list[tuple[date, ShiftType]]]:
        """Get full schedule for all teams over a date range."""
        return {
            offset: self.get_team_schedule_for_period(offset, start_date, end_date)
            for offset in team_offsets
        }

    def get_off_teams(self, team_offsets: list[int], target_date: date) -> list[int]:
        """Get list of team offsets that are OFF on target date."""
        shifts = self.get_all_team_shifts(team_offsets, target_date)
        return [offset for offset, shift in shifts.items() if shift == ShiftType.OFF]

    def get_on_shift_teams(
        self, team_offsets: list[int], target_date: date, shift_type: ShiftType
    ) -> list[int]:
        """Get list of team offsets working a specific shift on target date."""
        shifts = self.get_all_team_shifts(team_offsets, target_date)
        return [offset for offset, shift in shifts.items() if shift == shift_type]

    def validate_pattern(self) -> tuple[bool, str]:
        """Validate rotation pattern is well-formed."""
        if not self.rotation.pattern:
            return False, "Pattern is empty"

        valid_shifts = {0, 1, 2, 3}
        for i, shift in enumerate(self.rotation.pattern):
            if shift not in valid_shifts:
                return False, f"Invalid shift value {shift} at position {i}"

        # Check pattern has at least one of each shift type for the model
        if self.rotation.shift_model == "2-shift":
            if 1 not in self.rotation.pattern or 2 not in self.rotation.pattern:
                return False, "2-shift pattern must contain both shift 1 and 2"
        elif self.rotation.shift_model == "3-shift":
            if (
                1 not in self.rotation.pattern
                or 2 not in self.rotation.pattern
                or 3 not in self.rotation.pattern
            ):
                return False, "3-shift pattern must contain shifts 1, 2, and 3"

        return True, ""


def get_team_shift(
    rotation: RotationGroup, team_offset: int, target_date: date
) -> ShiftType:
    """Convenience function to get team shift."""
    engine = RotationEngine(rotation)
    return engine.get_team_shift(team_offset, target_date)


def get_all_team_shifts(
    rotation: RotationGroup, team_offsets: list[int], target_date: date
) -> dict[int, ShiftType]:
    """Convenience function to get all team shifts."""
    engine = RotationEngine(rotation)
    return engine.get_all_team_shifts(team_offsets, target_date)


def create_default_rotation_group(
    name: str, shift_model: str, cycle_start: date
) -> RotationGroup:
    """Create a rotation group with default pattern for the shift model."""
    pattern = DEFAULT_PATTERNS.get(shift_model, [])
    if not pattern:
        raise ValueError(f"Unknown shift model: {shift_model}")

    return RotationGroup(
        name=name,
        shift_model=shift_model,
        pattern=pattern,
        cycle_start_date=cycle_start,
        active=True,
    )


def calculate_team_offsets(pattern_length: int, team_count: int) -> list[int]:
    """Calculate evenly distributed offsets for teams."""
    if team_count <= 0:
        return []
    if team_count == 1:
        return [0]

    step = pattern_length // team_count
    if step == 0:
        step = 1

    return [(i * step) % pattern_length for i in range(team_count)]
