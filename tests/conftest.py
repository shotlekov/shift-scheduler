"""
Pytest configuration and fixtures for shiftcore tests.
"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import date, timedelta

from shiftcore import (
    RotationGroup,
    Team,
    Person,
    AvailabilityException,
    ShiftAssignment,
    ShiftSwap,
    ShiftType,
    SQLiteRepository,
    FairnessEngine,
)
from shiftcore.models import DEFAULT_PATTERNS, SHIFT_DEFINITIONS, MAX_CONSECUTIVE


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        repo = SQLiteRepository(db_path)
        yield repo


@pytest.fixture
def rotation_group_2shift():
    """Create a 2-shift rotation group."""
    return RotationGroup(
        name="Test 2-Shift",
        shift_model="2-shift",
        pattern=DEFAULT_PATTERNS["2-shift"],
        cycle_start_date=date(2026, 1, 1),
        active=True,
    )


@pytest.fixture
def rotation_group_3shift():
    """Create a 3-shift rotation group."""
    return RotationGroup(
        name="Test 3-Shift",
        shift_model="3-shift",
        pattern=DEFAULT_PATTERNS["3-shift"],
        cycle_start_date=date(2026, 1, 1),
        active=True,
    )


@pytest.fixture
def teams_2shift(rotation_group_2shift):
    """Create 3 teams for 2-shift rotation with offsets 0, 2, 4."""
    return [
        Team(id=1, name="Team Alpha", color="#ef4444", rotation_group_id=1, offset=0),
        Team(id=2, name="Team Bravo", color="#3b82f6", rotation_group_id=1, offset=2),
        Team(id=3, name="Team Charlie", color="#22c55e", rotation_group_id=1, offset=4),
    ]


@pytest.fixture
def teams_3shift(rotation_group_3shift):
    """Create 5 teams for 3-shift rotation with offsets 0, 2, 4, 6, 8."""
    return [
        Team(id=1, name="Team Alpha", color="#ef4444", rotation_group_id=1, offset=0),
        Team(id=2, name="Team Bravo", color="#3b82f6", rotation_group_id=1, offset=2),
        Team(id=3, name="Team Charlie", color="#22c55e", rotation_group_id=1, offset=4),
        Team(id=4, name="Team Delta", color="#a855f7", rotation_group_id=1, offset=6),
        Team(id=5, name="Team Echo", color="#f59e0b", rotation_group_id=1, offset=8),
    ]


@pytest.fixture
def persons_2shift(teams_2shift):
    """Create 2 persons per team (6 total) for 2-shift rotation."""
    persons = []
    for i, team in enumerate(teams_2shift):
        for j in range(2):
            persons.append(
                Person(
                    id=i * 2 + j + 1,
                    name=f"Person {i * 2 + j + 1}",
                    team_id=team.id if team.id else i + 1,
                    role="operator",
                    active=True,
                    telegram_chat_id=f"chat_{i * 2 + j + 1}",
                    email=f"person{i * 2 + j + 1}@example.com",
                )
            )
    return persons


@pytest.fixture
def sample_assignments():
    """Create sample shift assignments for testing."""
    return [
        ShiftAssignment(
            id=1,
            schedule_date=date(2026, 1, 1),
            shift_type=ShiftType.FIRST,
            person_id=1,
            team_id=1,
        ),
        ShiftAssignment(
            id=2,
            schedule_date=date(2026, 1, 1),
            shift_type=ShiftType.SECOND,
            person_id=3,
            team_id=2,
        ),
        ShiftAssignment(
            id=3,
            schedule_date=date(2026, 1, 2),
            shift_type=ShiftType.FIRST,
            person_id=1,
            team_id=1,
        ),
    ]


@pytest.fixture
def sample_exceptions():
    """Create sample availability exceptions."""
    return [
        AvailabilityException(
            person_id=1,
            start_date=date(2026, 1, 3),
            end_date=date(2026, 1, 5),
            reason="vacation",
        ),
    ]


@pytest.fixture
def fairness_engine():
    """Create a fairness engine with 28-day window."""
    return FairnessEngine(window_days=28)


@pytest.fixture
def shift_defs():
    """Return shift definitions."""
    return SHIFT_DEFINITIONS


@pytest.fixture
def max_consecutive():
    """Return max consecutive shifts config."""
    return MAX_CONSECUTIVE
