# Shift Scheduler - Developer Guide

## Table of Contents

1. [Development Setup](#development-setup)
2. [Project Structure](#project-structure)
3. [Running Tests](#running-tests)
4. [Code Style](#code-style)
5. [Adding Features](#adding-features)
6. [Database Migrations](#database-migrations)
7. [Debugging](#debugging)
8. [Contributing](#contributing)

---

## Development Setup

### Prerequisites

- Python 3.10+
- Git
- Optional: `python-telegram-bot>=20.0`, `aiosmtplib>=2.0` for notifications

### Installation

```bash
# Clone repository
git clone https://github.com/shotlekov/shift-scheduler.git
cd shift-scheduler

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Install optional notification dependencies
pip install python-telegram-bot aiosmtplib

# Install development dependencies
pip install pytest pytest-asyncio pytest-cov
```

### Running the Application

```bash
# From source
python src/app.py

# With debug logging
python -c "
import logging
logging.basicConfig(level=logging.DEBUG)
import src.app
"
```

### Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Specific module
python -m pytest tests/unit/test_constraints.py -v

# With coverage
python -m pytest tests/ --cov=shiftcore --cov-report=html

# Watch mode (requires pytest-watch)
ptw tests/
```

---

## Project Structure

```
shift-scheduler/
├── shiftcore/                 # Core library (pure Python, no UI deps)
│   ├── __init__.py           # Public API exports
│   ├── models.py             # Data models (dataclasses)
│   ├── rotation.py           # Rotation pattern engine
│   ├── constraints.py        # Constraint validators
│   ├── fairness.py           # Fairness balancing engine
│   ├── scheduler.py          # Schedule generation + substitution
│   ├── swaps.py              # Shift swap validation
│   ├── notifications.py      # Telegram/Email notification service
│   ├── storage.py            # SQLite repository
│   ├── exceptions.py         # Custom exceptions
│   └── pyproject.toml        # Package metadata
│
├── src/                       # Desktop UI
│   ├── app.py                # Main Tkinter application
│   └── shiftcore_adapter.py  # Legacy compatibility adapter
│
├── tests/                     # Test suite (83 tests)
│   ├── conftest.py           # Pytest fixtures
│   └── unit/                 # Unit tests by module
│       ├── test_constraints.py
│       ├── test_fairness.py
│       ├── test_rotation.py
│       ├── test_scheduler.py
│       ├── test_storage.py
│       └── test_swaps.py
│
├── data/                      # SQLite database (gitignored)
│   └── shift_scheduler.db
│
├── docs/                      # Documentation
│   ├── README.md
│   ├── architecture.md
│   ├── api.md
│   ├── user-guide.md
│   ├── developer-guide.md
│   └── deployment.md
│
├── build.spec                 # PyInstaller configuration
├── build.sh                   # Build script
├── requirements.txt           # Python dependencies
└── .gitignore
```

---

## Running Tests

### Test Organization

```
tests/
├── conftest.py                    # Shared fixtures
└── unit/
    ├── test_constraints.py        # 19 tests - all 4 validators
    ├── test_fairness.py           # 12 tests - fairness engine
    ├── test_rotation.py           # 24 tests - rotation engine
    ├── test_scheduler.py          # 11 tests - schedule generation
    ├── test_storage.py            # 11 tests - SQLite repository
    └── test_swaps.py              # 6 tests - swap validation
```

### Test Fixtures (conftest.py)

Key fixtures available in all tests:
- `temp_db` — Temporary SQLiteRepository
- `rotation_group_2shift` / `rotation_group_3shift` — Pre-configured rotation groups
- `teams_2shift` / `teams_3shift` — Teams with correct offsets
- `persons_2shift` — 2 persons per team (6 total)
- `sample_assignments` — Pre-made assignments for constraint testing
- `sample_exceptions` — Availability exceptions
- `fairness_engine` — FairnessEngine with 28-day window
- `shift_defs` / `max_consecutive` — Constants

### Writing New Tests

```python
# tests/unit/test_new_feature.py
import pytest
from datetime import date
from shiftcore import NewFeature, SomeModel

def test_new_feature_basic(temp_db, rotation_group_2shift, teams_2shift):
    """Test basic functionality."""
    feature = NewFeature()
    result = feature.do_something(teams_2shift[0])
    assert result is not None

@pytest.mark.parametrize("input,expected", [
    ("case1", "result1"),
    ("case2", "result2"),
])
def test_new_feature_parametrized(input, expected):
    """Parametrized test for multiple cases."""
    assert NewFeature().process(input) == expected
```

### Test Commands

```bash
# Run all tests with verbose output
python -m pytest tests/ -v

# Run with coverage report
python -m pytest tests/ --cov=shiftcore --cov-report=term-missing

# Run only failed tests from last run
python -m pytest tests/ --lf

# Run tests matching pattern
python -m pytest tests/ -k "constraint" -v

# Parallel execution (requires pytest-xdist)
python -m pytest tests/ -n auto
```

---

## Code Style

### Python Style Guide

- **Formatter**: Black (line length 100)
- **Linter**: Ruff (fast, replaces flake8/isort)
- **Type Checking**: mypy (optional, for core modules)

### Configuration

```toml
# pyproject.toml
[tool.black]
line-length = 100
target-version = ['py310']

[tool.ruff]
line-length = 100
target-version = "py310"
select = ["E", "F", "I", "UP", "B", "C4", "SIM", "T20"]
ignore = ["E501"]  # Black handles line length
```

### Running Formatters

```bash
# Format code
black shiftcore/ src/ tests/

# Lint
ruff check shiftcore/ src/ tests/

# Auto-fix lint issues
ruff check --fix shiftcore/ src/ tests/
```

### Type Hints

- Use type hints for all public functions
- Prefer `Optional[X]` over `X | None` for compatibility
- Use `list[X]` not `List[X]` (Python 3.9+)

```python
from datetime import date
from typing import Optional
from shiftcore.models import Team, Person

def get_team_schedule(
    team: Team,
    start_date: date,
    end_date: date,
    person_id: Optional[int] = None,
) -> list[tuple[date, str]]:
    ...
```

---

## Adding Features

### Adding a New Constraint

1. **Add validator** in `shiftcore/constraints.py`:

```python
def check_new_constraint(
    person_id: int,
    target_date: date,
    proposed_shift: ShiftType,
    assignments: list[ShiftAssignment],
    # ... other params
) -> tuple[bool, str]:
    """Check new constraint. Returns (is_valid, error_message)."""
    # Implementation
    return True, ""
```

2. **Integrate** in `validate_all_constraints()`:

```python
def validate_all_constraints(...):
    # ... existing checks ...
    
    # Add new constraint
    valid, error = check_new_constraint(...)
    if not valid:
        return False, error
    
    return True, ""
```

3. **Add tests** in `tests/unit/test_constraints.py`:

```python
class TestNewConstraint:
    def test_valid_case(self, ...):
        valid, error = check_new_constraint(...)
        assert valid
    
    def test_violation_case(self, ...):
        valid, error = check_new_constraint(...)
        assert not valid
        assert "expected error" in error
```

4. **Run tests**: `python -m pytest tests/unit/test_constraints.py -v`

### Adding a New Shift Model

1. **Update constants** in `shiftcore/models.py`:

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
    "4-shift": {  # New model
        "name": "4-Shift (Extended)",
        "pattern": [1, 1, 2, 2, 3, 3, 4, 4, 0, 0, 0, 0],
        "pattern_length": 12,
        "team_count": 6,
        "shifts": [ShiftType.FIRST, ShiftType.SECOND, ShiftType.THIRD, ShiftType.FOURTH],
        "max_consecutive": {
            ShiftType.FIRST: 5,
            ShiftType.SECOND: 5,
            ShiftType.THIRD: 3,
            ShiftType.FOURTH: 2,
        },
    },
}

# Add new shift type if needed
class ShiftType(IntEnum):
    OFF = 0
    FIRST = 1
    SECOND = 2
    THIRD = 3
    FOURTH = 4  # New

# Update SHIFT_DEFINITIONS
SHIFT_DEFINITIONS = {
    ShiftType.FIRST:  {"name": "1st", "start_hour": 6,  "end_hour": 14, "hours": 8},
    ShiftType.SECOND: {"name": "2nd", "start_hour": 14, "end_hour": 22, "hours": 8},
    ShiftType.THIRD:  {"name": "3rd", "start_hour": 22, "end_hour": 6,  "hours": 8},
    ShiftType.FOURTH: {"name": "4th", "start_hour": 2,  "end_hour": 10, "hours": 8},  # New
}

# Add to TEAM_COLORS if more teams needed
TEAM_COLORS = [
    "#ef4444",  # Red - Team 1
    "#3b82f6",  # Blue - Team 2
    "#22c55e",  # Green - Team 3
    "#f59e0b",  # Amber - Team 4
    "#a855f7",  # Purple - Team 5
    "#ec4899",  # Pink - Team 6 (new)
]
```

2. **Update validation** in `shiftcore/rotation.py` — automatically handled by SHIFT_MODELS validation

3. **Update UI** in `src/app.py`:
   - Add "4-shift" to shift_model_combo values
   - Update shift combo boxes in swaps tab

### Adding a Notification Channel

1. **Create provider** in `shiftcore/notifications.py`:

```python
class SlackProvider:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    async def send_message(self, channel: str, message: str) -> bool:
        # Implementation using aiohttp
        pass
```

2. **Integrate** in `NotificationService`:

```python
class NotificationService:
    def __init__(self, ..., slack_webhook: str = ""):
        self.slack = SlackProvider(slack_webhook) if slack_webhook else None
    
    async def _send_notification(self, notification: NotificationQueue) -> bool:
        if notification.target_type == "slack" and self.slack:
            return await self.slack.send_message(notification.target_id, notification.message)
        # ... existing providers ...
```

---

## Database Migrations

### Schema Versioning

The `SQLiteRepository._init_schema()` runs `SCHEMA` script which is idempotent (uses `CREATE TABLE IF NOT EXISTS`).

### Adding Columns

For non-breaking additions, use `ALTER TABLE` in a migration function:

```python
# In storage.py, add to _init_schema() or create _run_migrations()
def _run_migrations(self):
    conn = self._get_conn()
    try:
        # Check if column exists
        cur = conn.execute("PRAGMA table_info(persons)")
        columns = {row["name"] for row in cur.fetchall()}
        
        if "new_column" not in columns:
            conn.execute("ALTER TABLE persons ADD COLUMN new_column TEXT DEFAULT ''")
            conn.commit()
    finally:
        conn.close()
```

Call `_run_migrations()` in `__init__` after `_init_schema()`.

### Breaking Changes

For breaking schema changes:
1. Create new tables with new names
2. Migrate data in a one-time script
3. Update all queries
4. Drop old tables after verification

---

## Debugging

### Enable Debug Logging

```python
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### Common Debug Scenarios

**Schedule generation issues:**
```python
from shiftcore import generate_schedule, FairnessEngine
from datetime import date

# Debug with detailed output
fairness = FairnessEngine()
result = generate_schedule(..., fairness_engine=fairness)

print(f"Assignments: {len(result.assignments)}")
print(f"Conflicts: {result.conflicts}")
print(f"Substitutions: {result.substitutions}")
print(f"Unfilled: {result.unfilled_shifts}")
print(f"Fairness: {result.fairness_report}")
```

**Constraint violations:**
```python
from shiftcore import validate_all_constraints, get_violations

valid, error = validate_all_constraints(...)
if not valid:
    print(f"Error: {error}")

# Get all violations
violations = get_violations(...)
for v in violations:
    print(f"  - {v}")
```

**Database inspection:**
```bash
# Open database directly
sqlite3 data/shift_scheduler.db

# Useful queries
.tables
SELECT * FROM rotation_groups;
SELECT * FROM teams;
SELECT * FROM persons;
SELECT * FROM shift_assignments ORDER BY schedule_date;
SELECT * FROM availability_exceptions;
```

### UI Debugging

Run with console output:
```bash
python src/app.py 2>&1 | tee app.log
```

---

## Contributing

### Pull Request Process

1. **Fork** the repository
2. **Create branch**: `git checkout -b feature/my-feature`
3. **Make changes** with tests
4. **Run tests**: `python -m pytest tests/ -v`
5. **Format code**: `black shiftcore/ src/ tests/ && ruff check --fix shiftcore/ src/ tests/`
6. **Commit**: `git commit -m "feat: add my feature"`
7. **Push**: `git push origin feature/my-feature`
8. **Open PR** against `master`

### Commit Message Format

Use Conventional Commits:
- `feat:` — New feature
- `fix:` — Bug fix
- `docs:` — Documentation only
- `style:` — Formatting, no code change
- `refactor:` — Code restructuring
- `test:` — Adding tests
- `chore:` — Maintenance

Examples:
```
feat: add 4-shift rotation model support
fix: resolve rest hours calculation for 3rd shift
docs: update API reference for NotificationService
test: add parametrized tests for fairness engine
```

### Code Review Checklist

- [ ] All tests pass
- [ ] New code has tests
- [ ] Type hints added
- [ ] Documentation updated
- [ ] No breaking changes without migration
- [ ] Performance considered
- [ ] Security reviewed (no hardcoded secrets)

---

## Release Process

### Version Bumping

```bash
# Update version in shiftcore/pyproject.toml
# Update version in shiftcore/__init__.py
# Update CHANGELOG.md
```

### Building Release

```bash
# Linux
./build.sh

# Windows (on Windows or with Wine)
pyinstaller build.spec --clean --noconfirm

# Create GitHub release with dist/ artifacts
```

### Publishing to PyPI (for shiftcore package)

```bash
cd shiftcore
pip install build twine
python -m build
twine upload dist/*
```