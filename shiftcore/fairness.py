"""
Fairness engine for balancing shift assignments across operators.
Uses rolling 28-day window with shift count + last assignment tiebreaker.
"""

from datetime import date, timedelta
from typing import Optional
from .models import Person, PersonShiftCounter, ShiftAssignment


class FairnessEngine:
    """Manages fairness balancing for shift assignments."""

    def __init__(self, window_days: int = 28):
        self.window_days = window_days

    def get_window_start(self, reference_date: date) -> date:
        """Calculate window start date for a reference date."""
        # Rolling window: reference_date - (days_since_epoch % window_days)
        # Simpler: use 28-day periods aligned to reference date
        days_offset = (reference_date.toordinal() - 1) % self.window_days
        return reference_date - timedelta(days=days_offset)

    def get_window_end(self, window_start: date) -> date:
        """Calculate window end date from start."""
        return window_start + timedelta(days=self.window_days - 1)

    def get_shift_counts(
        self,
        person_ids: list[int],
        window_start: date,
        window_end: date,
        assignments: list[ShiftAssignment],
    ) -> dict[int, int]:
        """Get shift counts for persons in the given window."""
        counts = {pid: 0 for pid in person_ids}

        for assignment in assignments:
            if (
                assignment.person_id in person_ids
                and window_start <= assignment.schedule_date <= window_end
            ):
                counts[assignment.person_id] += 1

        return counts

    def get_last_assignment(
        self,
        person_id: int,
        window_end: date,
        assignments: list[ShiftAssignment],
    ) -> Optional[date]:
        """Get most recent assignment date for person before window_end."""
        person_assignments = [
            a
            for a in assignments
            if a.person_id == person_id and a.schedule_date <= window_end
        ]
        if not person_assignments:
            return None
        return max(a.schedule_date for a in person_assignments)

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
        if not eligible_person_ids:
            return None

        window_start = self.get_window_start(reference_date)
        window_end = self.get_window_end(window_start)

        # Get shift counts
        if counters:
            shift_counts = {
                pid: counters.get(
                    pid, PersonShiftCounter(person_id=pid, period_start=window_start)
                ).shift_count
                for pid in eligible_person_ids
            }
        else:
            shift_counts = self.get_shift_counts(
                eligible_person_ids, window_start, window_end, assignments
            )

        # Get last assignment dates
        last_assignments = {
            pid: self.get_last_assignment(pid, window_end, assignments)
            for pid in eligible_person_ids
        }

        # Sort by: shift_count ASC, last_assignment_date ASC (None = oldest)
        def sort_key(pid: int):
            count = shift_counts.get(pid, 0)
            last_date = last_assignments.get(pid)
            # None dates sort as very old (use date.min)
            last_ordinal = last_date.toordinal() if last_date else 0
            return (count, last_ordinal)

        sorted_candidates = sorted(eligible_person_ids, key=sort_key)
        return sorted_candidates[0] if sorted_candidates else None

    def record_assignment(
        self,
        person_id: int,
        assignment_date: date,
        counters: dict[int, PersonShiftCounter],
    ) -> None:
        """Record an assignment in the fairness counters."""
        window_start = self.get_window_start(assignment_date)

        if person_id not in counters:
            counters[person_id] = PersonShiftCounter(
                person_id=person_id,
                period_start=window_start,
                shift_count=0,
                last_assignment_date=None,
            )

        counter = counters[person_id]
        # If window changed, reset counter
        if counter.period_start != window_start:
            counter.period_start = window_start
            counter.shift_count = 0

        counter.shift_count += 1
        counter.last_assignment_date = assignment_date

    def get_fairness_report(
        self,
        person_ids: list[int],
        reference_date: date,
        assignments: list[ShiftAssignment],
        counters: dict[int, PersonShiftCounter] = None,
    ) -> dict:
        """Generate fairness report for all persons."""
        window_start = self.get_window_start(reference_date)
        window_end = self.get_window_end(window_start)

        if counters:
            shift_counts = {
                pid: counters.get(
                    pid, PersonShiftCounter(person_id=pid, period_start=window_start)
                ).shift_count
                for pid in person_ids
            }
        else:
            shift_counts = self.get_shift_counts(
                person_ids, window_start, window_end, assignments
            )

        last_assignments = {
            pid: self.get_last_assignment(pid, window_end, assignments)
            for pid in person_ids
        }

        counts = list(shift_counts.values())
        min_count = min(counts) if counts else 0
        max_count = max(counts) if counts else 0

        return {
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "person_counts": shift_counts,
            "last_assignments": {
                pid: d.isoformat() if d else None for pid, d in last_assignments.items()
            },
            "min_shifts": min_count,
            "max_shifts": max_count,
            "variance": max_count - min_count,
            "is_balanced": (max_count - min_count) <= 1,
        }
