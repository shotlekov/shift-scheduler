# Quickstart: Shift Scheduler Redesign

**Spec**: `.specify/specs/001-shift-scheduler-redesign/spec.md`

## Prerequisites

- Python 3.10+
- Git
- (Optional) Telegram bot token for notifications
- (Optional) SMTP credentials for email notifications

## Installation

### Development Setup

```bash
# Clone and enter
cd /home/meto/workspace/shift-scheduler

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install shiftcore in development mode
pip install -e ./shiftcore

# Install desktop app dependencies
pip install tkcalendar python-telegram-bot aiosmtplib

# Run tests
pytest tests/ -v

# Run desktop app
python -m shift_scheduler.src.app
```

### Production Build (Linux)

```bash
# Build standalone binary
pip install pyinstaller
pyinstaller --onefile --windowed --name shift-scheduler \
  --add-data "shiftcore:shiftcore" \
  --add-data "data:data" \
  shift_scheduler/src/app.py

# Output: dist/shift-scheduler
```

### Production Build (Windows)

```powershell
# On Windows or via cross-compilation
pip install pyinstaller
pyinstaller --onefile --windowed --name shift-scheduler.exe ^
  --add-data "shiftcore;shiftcore" ^
  --add-data "data;data" ^
  shift_scheduler/src/app.py

# Output: dist/shift-scheduler.exe
```

## Configuration

### Environment Variables

Create `.env` in project root:

```bash
# Telegram (optional)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_TEAM_GROUP_CHAT_ID=-1001234567890
TELEGRAM_ALL_TEAMS_GROUP_CHAT_ID=-1001234567891

# Email/SMTP (optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=Shift Scheduler <noreply@yourdomain.com>
```

### Database

SQLite database auto-created at `data/shift_scheduler.db` on first run.

## Usage Guide

### 1. Initial Setup

1. Launch app: `python -m shift_scheduler.src.app`
2. **Rotation Group** tab (or dialog on first run):
   - Name: "Main Rotation"
   - Shift Model: "2-shift" (6-day) or "3-shift" (10-day)
   - Cycle Start Date: First day of pattern (e.g., 2026-01-01)
   - Click "Create"
3. **Teams & People** tab:
   - Click "Add Team" → enter name, color → auto-assigned offset
   - Repeat for 3 teams (2-shift) or 5 teams (3-shift)
   - Select team → "Add Person" → name, role, telegram_chat_id, email
   - Repeat for all operators

### 2. Manage Availability

1. **Availability** tab:
   - Select person
   - Enter start/end date, reason (sick/vacation/other)
   - Click "Add Exception"
   - Exceptions show in list; delete to remove

### 3. Generate Schedule

1. **Schedule View** tab:
   - Set Start Date, End Date (e.g., 2 weeks)
   - Cycle Start auto-filled from rotation group
   - Click "Generate Schedule"
   - Wait for background generation
   - Review results: assignments, conflicts, substitutes, unfilled
2. Grid shows: Date, Day, Team1, Team2, Team3... with shift + person
   - Substitutes marked with (S)
   - Click row for person detail panel

### 4. Shift Swaps

1. **Shift Swaps** tab:
   - Select date
   - Select Person A + their shift
   - Select Person B + their shift
   - Click "Add Swap"
   - System validates constraints; rejects if violation
   - Approved swaps show in list

### 5. Export & Notifications

- **Export CSV**: Click "Export CSV" in Schedule View → saves grid data
- **Notifications**: Automatic on:
  - New assignment → person DM + team group + all-teams group (Telegram)
  - Substitution → original + substitute + team + all-teams (Telegram)
  - Swap approved → both persons DM + email + team group (Telegram)
  - Schedule regenerated → team group + all-teams group summary (Telegram)
- **Notifications tab**: View queue, retry failed, send test messages

## Running Tests

```bash
# All tests
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# With coverage
pytest tests/ --cov=shiftcore --cov-report=html

# Specific module
pytest tests/unit/test_constraints.py -v
```

## API Usage (shiftcore)

```python
from shiftcore import (
    SQLiteRepository,
    RotationGroup, Team, Person,
    generate_schedule,
    FairnessEngine,
    NotificationService,
)
from datetime import date

# Initialize
repo = SQLiteRepository(Path("data/shift_scheduler.db"))

# Load data
rotation = repo.get_rotation_group()
teams = repo.get_teams()
persons = repo.get_persons()
exceptions = repo.get_exceptions()

# Generate schedule
fairness = FairnessEngine(window_days=28)
result = generate_schedule(
    rotation=rotation,
    teams=teams,
    persons=persons,
    exceptions=exceptions,
    existing_assignments=[],
    start_date=date(2026, 1, 1),
    end_date=date(2026, 1, 14),
    shift_defs={1: (6,14), 2: (14,22), 3: (22,6)},
    max_consecutive={1: 5, 2: 5, 3: 3},
    fairness_engine=fairness,
)

# Access results
for assignment in result.assignments:
    print(f"{assignment.schedule_date}: {assignment.person_name} → {assignment.shift_type}")

# Send notifications
notifier = NotificationService(
    telegram_token="BOT_TOKEN",
    smtp_config=SMTPConfig(...)
)
notifier.queue_notification("person_dm", "123456789", "Your shift tomorrow: 1st")
await notifier.process_queue()
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "No rotation group found" | Create one in Rotation Group dialog on first run |
| "Team offset collision" | Offsets must be unique; edit team to fix |
| "No eligible substitute" | Check off-team members' availability + constraints |
| "Swap rejected" | Error message shows which constraint failed |
| "Telegram not sending" | Check TELEGRAM_BOT_TOKEN, chat IDs; view Notifications tab |
| "Email not sending" | Check SMTP credentials; try test email in Notifications tab |
| "Schedule generation slow" | Reduce date range; check for constraint conflicts |
| "Fairness variance > 1" | Normal for small teams/short windows; increases with more people |

## Development Workflow

```bash
# 1. Make changes to shiftcore/
# 2. Run unit tests for changed module
pytest tests/unit/test_<module>.py -v

# 3. Run integration tests
pytest tests/integration/ -v

# 4. Test desktop app manually
python -m shift_scheduler.src.app

# 5. Build and test binary
./scripts/build_linux.sh
./dist/shift-scheduler
```

## Project Structure

```
shift-scheduler/
├── shiftcore/                 # Core package (reusable)
│   ├── models.py
│   ├── rotation.py
│   ├── constraints.py
│   ├── fairness.py
│   ├── scheduler.py
│   ├── swaps.py
│   ├── notifications.py
│   ├── storage.py
│   └── exceptions.py
├── shift_scheduler/           # Desktop app
│   └── src/
│       ├── app.py
│       └── ui/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── contract/
├── data/                      # SQLite DB (gitignored)
├── scripts/
│   ├── migrate_legacy.py
│   ├── build_linux.sh
│   └── build_windows.ps1
├── .specify/specs/001-shift-scheduler-redesign/
│   ├── spec.md
│   ├── plan.md
│   ├── data-model.md
│   ├── tasks.md
│   └── quickstart.md
└── venv/                      # Virtual env (gitignored)
```

## Key Commands Reference

```bash
# Install shiftcore in dev mode
pip install -e ./shiftcore

# Run all tests with coverage
pytest tests/ --cov=shiftcore --cov-report=term-missing

# Generate schedule via CLI (for testing)
python -c "
from shiftcore import SQLiteRepository, generate_schedule, FairnessEngine
from datetime import date
repo = SQLiteRepository(Path('data/shift_scheduler.db'))
rotation = repo.get_rotation_group()
teams = repo.get_teams()
persons = repo.get_persons()
exceptions = repo.get_exceptions()
result = generate_schedule(rotation, teams, persons, exceptions, [], date(2026,1,1), date(2026,1,14), {1:(6,14),2:(14,22)}, {1:5,2:5}, FairnessEngine())
print(f'Assignments: {len(result.assignments)}')
print(f'Unfilled: {len(result.unfilled)}')
"

# Check database
sqlite3 data/shift_scheduler.db ".schema"
sqlite3 data/shift_scheduler.db "SELECT * FROM rotation_groups;"
```