# Implementation Plan: Shift Scheduler Redesign

**Branch**: `001-shift-scheduler-redesign` | **Date**: 2026-10-02 | **Spec**: `.specify/specs/001-shift-scheduler-redesign/spec.md`

## Summary

Redesign the shift scheduler from a hardcoded 3-team Tkinter app into a modular system with:
- **shiftcore** package: pure Python scheduling engine (rotation patterns, constraints, fairness, substitution, notifications)
- **Desktop UI**: Tkinter app consuming shiftcore
- **Data model**: RotationGroup, Team, Person, AvailabilityException, ShiftAssignment, ShiftSwap, PersonShiftCounter, NotificationQueue
- **Constraints**: 1 shift/day, 12h rest, max consecutive (5 for 1st/2nd, 3 for 3rd), availability exceptions
- **Fairness**: Rolling 28-day window, min-shift-count + oldest-last-assignment tiebreak
- **Notifications**: Telegram (DM, team group, all-teams group) + Email (person only), queued with retry

## Technical Context

**Language/Version**: Python 3.10+ (3.11 recommended)

**Primary Dependencies**:
- `shiftcore`: stdlib only (datetime, sqlite3, json, abc, dataclasses, enum)
- Desktop UI: `tkinter` (stdlib), `tkcalendar` (optional, for date pickers)
- Notifications: `python-telegram-bot` (async), `aiosmtplib` (async email)
- Packaging: `pyinstaller`, `pytest`, `pytest-asyncio`

**Storage**: SQLite (single file `data/shift_scheduler.db`), WAL mode

**Testing**: `pytest` + `pytest-asyncio` for async notification tests; ≥80% coverage on shiftcore

**Target Platform**: Linux (primary), Windows (via PyInstaller), future WebUI (FastAPI + React)

**Project Type**: Desktop app with reusable core library

**Performance Goals**:
- Schedule generation: <2s for 14 days × 3 teams × 20 people
- Notification send: <500ms per message (async, non-blocking)
- DB operations: <10ms typical

**Constraints**:
- Zero UI deps in shiftcore
- Single rotation group at a time
- No authentication in MVP
- Local timezone only

**Scale/Scope**: ≤20 teams, ≤100 persons, ≤365 days schedule range

## Constitution Check

- ✅ Single responsibility: shiftcore (logic) vs UI (presentation)
- ✅ Testability: Each user story independently testable via shiftcore API
- ✅ No premature optimization: Simple greedy fairness, SQLite
- ✅ Explicit constraints: All 12 hard constraints enumerated in spec
- ✅ Observability: NotificationQueue with status/retries

## Project Structure

### Documentation
```
.specify/specs/001-shift-scheduler-redesign/
├── spec.md              # This spec
├── plan.md              # This plan
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (shiftcore public API)
└── tasks.md             # Phase 2 output
```

### Source Code (Repository Root)
```
shiftcore/                    # Core package (no UI deps)
├── __init__.py
├── models.py                 # Dataclasses/Pydantic models
├── rotation.py               # RotationGroup, pattern engine, team shift calc
├── constraints.py            # Constraint validators (12h, consecutive, 1/day)
├── fairness.py               # ShiftCounter, balancing algorithm
├── scheduler.py              # Main generate_schedule() + substitution
├── swaps.py                  # Swap validation
├── notifications.py          # NotificationQueue, Telegram, Email providers
├── storage.py                # SQLite repository layer
└── exceptions.py             # Custom exceptions

shift_scheduler/              # Desktop app (existing, to be refactored)
├── src/
│   ├── app.py                # Main Tkinter app (refactored to use shiftcore)
│   ├── ui/                   # UI components (tabs, dialogs)
│   │   ├── __init__.py
│   │   ├── schedule_tab.py
│   │   ├── teams_tab.py
│   │   ├── exceptions_tab.py
│   │   ├── swaps_tab.py
│   │   └── notifications_tab.py
│   └── utils.py
├── db.py                     # Legacy - migrate to shiftcore.storage
├── scheduler.py              # Legacy - migrate to shiftcore.scheduler
└── start-app.sh

tests/
├── unit/
│   ├── test_rotation.py
│   ├── test_constraints.py
│   ├── test_fairness.py
│   ├── test_scheduler.py
│   ├── test_swaps.py
│   └── test_notifications.py
├── integration/
│   ├── test_full_schedule_generation.py
│   └── test_notification_delivery.py
└── contract/
    └── test_shiftcore_api.py

data/                         # SQLite DB (gitignored)
.shiftcore/                   # shiftcore package config (pyproject.toml)
```

**Structure Decision**: Monorepo with `shiftcore/` as installable package, `shift_scheduler/` as desktop consumer. Tests at root for pytest discovery.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Separate `shiftcore` package | Required for WebUI reuse; architectural mandate | Keeping logic in app.py prevents WebUI migration |
| NotificationQueue with retry | Telegram/Email unreliable; must not block UI | Fire-and-forget loses messages silently |
| Rolling 28-day fairness window | Explicit user requirement for balance | Simple round-robin doesn't guarantee balance over windows |
| Swap validation with full constraints | Unvalidated swaps break 12h rest / consecutive limits | Post-swap check only catches after damage done |

---

## Phase 0: Research (Optional - Deferred)

No external research needed; all requirements clarified in spec.

## Phase 1: Data Model & Contracts

### Deliverables
1. **data-model.md** - Entity definitions, relationships, SQLite schema
2. **contracts/** - shiftcore public API (interfaces, function signatures)
3. **quickstart.md** - How to run tests, generate schedule, send test notification

### Data Model (SQLite Schema)

```sql
-- Rotation group (single active)
CREATE TABLE rotation_groups (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    shift_model TEXT NOT NULL CHECK (shift_model IN ('2-shift', '3-shift')),
    pattern TEXT NOT NULL,           -- JSON array: [1,1,2,2,0,0]
    cycle_start_date TEXT NOT NULL,  -- ISO date
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Teams
CREATE TABLE teams (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    color TEXT DEFAULT '#2563eb',
    rotation_group_id INTEGER NOT NULL REFERENCES rotation_groups(id),
    offset INTEGER NOT NULL DEFAULT 0,  -- 0..pattern_len-1
    created_at TEXT DEFAULT (datetime('now'))
);

-- Persons
CREATE TABLE persons (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    role TEXT DEFAULT 'operator',
    active INTEGER DEFAULT 1,
    telegram_chat_id TEXT,
    email TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(name, team_id)
);

-- Availability exceptions
CREATE TABLE availability_exceptions (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    reason TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

-- Shift assignments
CREATE TABLE shift_assignments (
    id INTEGER PRIMARY KEY,
    schedule_date TEXT NOT NULL,
    shift_type INTEGER NOT NULL CHECK (shift_type IN (1,2,3)),
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    is_substitute INTEGER DEFAULT 0,
    substitute_for_id INTEGER REFERENCES persons(id) ON DELETE SET NULL,
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(schedule_date, shift_type, person_id)
);

-- Shift swaps
CREATE TABLE shift_swaps (
    id INTEGER PRIMARY KEY,
    schedule_date TEXT NOT NULL,
    person_a_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    person_b_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    shift_a INTEGER NOT NULL CHECK (shift_a IN (1,2,3)),
    shift_b INTEGER NOT NULL CHECK (shift_b IN (1,2,3)),
    approved INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Fairness counters (rolling 28-day windows)
CREATE TABLE person_shift_counters (
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    period_start TEXT NOT NULL,  -- ISO date, window start
    shift_count INTEGER DEFAULT 0,
    last_assignment_date TEXT,
    PRIMARY KEY (person_id, period_start)
);

-- Notification queue
CREATE TABLE notification_queue (
    id INTEGER PRIMARY KEY,
    target_type TEXT NOT NULL CHECK (target_type IN ('person_dm','team_group','all_teams_group','email')),
    target_id TEXT NOT NULL,     -- chat_id, email, or 'all'
    message TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','sent','failed')),
    retries INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    sent_at TEXT
);

-- Indexes
CREATE INDEX idx_assignments_date ON shift_assignments(schedule_date);
CREATE INDEX idx_assignments_person_date ON shift_assignments(person_id, schedule_date);
CREATE INDEX idx_exceptions_person_date ON availability_exceptions(person_id, start_date, end_date);
CREATE INDEX idx_swaps_date ON shift_swaps(schedule_date);
CREATE INDEX idx_notifications_status ON notification_queue(status);
```

### shiftcore Public API (Contracts)

```python
# shiftcore/rotation.py
class RotationGroup:
    id: int
    name: str
    shift_model: Literal["2-shift", "3-shift"]
    pattern: list[int]  # e.g., [1,1,2,2,0,0]
    cycle_start: date
    active: bool

def get_team_shift(rotation: RotationGroup, team_offset: int, target_date: date) -> Optional[int]:
    """Return shift_type (1,2,3) or None (off) for team at offset on target_date."""

def get_all_team_shifts(rotation: RotationGroup, team_offsets: list[int], target_date: date) -> dict[int, Optional[int]]:
    """Return {team_offset: shift_type_or_None} for all teams on target_date."""

# shiftcore/constraints.py
def check_one_shift_per_day(person_id: int, target_date: date, assignments: list[ShiftAssignment]) -> tuple[bool, str]:
def check_rest_hours(person_id: int, target_date: date, proposed_shift: int, assignments: list[ShiftAssignment], shift_defs: dict[int, tuple[time,time]]) -> tuple[bool, str]:
def check_max_consecutive(person_id: int, target_date: date, proposed_shift: int, assignments: list[ShiftAssignment], shift_type: int, max_consecutive: dict[int, int]) -> tuple[bool, str]:
def validate_all_constraints(person_id: int, target_date: date, proposed_shift: int, assignments: list[ShiftAssignment], exceptions: list[AvailabilityException], shift_defs: dict, max_consecutive: dict) -> tuple[bool, str]:

# shiftcore/fairness.py
class FairnessEngine:
    def __init__(self, window_days: int = 28):
    def get_shift_counts(self, person_ids: list[int], window_start: date, window_end: date) -> dict[int, int]:
    def get_last_assignment(self, person_id: int, window_end: date) -> Optional[date]:
    def select_candidate(self, eligible: list[int], window_start: date, window_end: date) -> int:
    def record_assignment(self, person_id: int, assignment_date: date):

# shiftcore/scheduler.py
def generate_schedule(
    rotation: RotationGroup,
    teams: list[Team],
    persons: list[Person],
    exceptions: list[AvailabilityException],
    existing_assignments: list[ShiftAssignment],
    start_date: date,
    end_date: date,
    shift_defs: dict[int, tuple[time,time]],
    max_consecutive: dict[int, int],
    fairness_engine: FairnessEngine,
) -> ScheduleResult:
    """Returns ScheduleResult(assignments, unfilled, substitutions, fairness_report)"""

def find_substitute(
    rotation: RotationGroup,
    teams: list[Team],
    persons: list[Person],
    exceptions: list[AvailabilityException],
    assignments: list[ShiftAssignment],
    target_date: date,
    shift_type: int,
    exclude_person_ids: list[int],
    shift_defs: dict,
    max_consecutive: dict,
    fairness_engine: FairnessEngine,
) -> Optional[Person]:

# shiftcore/swaps.py
def validate_swap(
    person_a: Person, person_b: Person,
    target_date: date, shift_a: int, shift_b: int,
    assignments: list[ShiftAssignment],
    exceptions: list[AvailabilityException],
    shift_defs: dict,
    max_consecutive: dict,
) -> tuple[bool, str]:

# shiftcore/notifications.py
class NotificationService:
    def __init__(self, telegram_token: str, smtp_config: SMTPConfig):
    def queue_notification(self, target_type: str, target_id: str, message: str):
    async def process_queue(self):
    async def send_telegram(self, chat_id: str, message: str):
    async def send_email(self, to_email: str, subject: str, body: str):

# shiftcore/storage.py
class SQLiteRepository:
    def __init__(self, db_path: Path):
    # CRUD for all entities
    def get_rotation_group(self) -> Optional[RotationGroup]:
    def get_teams(self) -> list[Team]:
    def get_persons(self, team_id: Optional[int] = None) -> list[Person]:
    def get_exceptions(self, person_id: Optional[int] = None) -> list[AvailabilityException]:
    def get_assignments(self, start: date, end: date) -> list[ShiftAssignment]:
    def get_swaps(self, start: date, end: date) -> list[ShiftSwap]:
    def get_shift_counters(self, person_ids: list[int], period_start: date) -> dict[int, PersonShiftCounter]:
    def save_assignments(self, assignments: list[ShiftAssignment]):
    def save_swap(self, swap: ShiftSwap):
    def save_shift_counters(self, counters: list[PersonShiftCounter]):
    def queue_notification(self, target_type: str, target_id: str, message: str):
    def get_pending_notifications(self, limit: int = 100) -> list[NotificationQueue]:
    def mark_notification_sent(self, notification_id: int):
    def mark_notification_failed(self, notification_id: int):
```

---

## Phase 2: Task Generation

Tasks will be generated from this plan and the spec, organized by user story (P1 → P2).

---

## Phase 3: Implementation Order (MVP First)

1. **Setup**: Create `shiftcore/` package structure, pyproject.toml, SQLite schema migration
2. **Foundational**: Models, rotation engine, constraint validators, fairness engine, storage layer
3. **US1 (P1)**: Rotation group + team management API + UI
4. **US2 (P1)**: Availability exceptions API + UI
5. **US3 (P1)**: Schedule generation with all constraints
6. **US4 (P1)**: Fairness balancing integrated into scheduler
7. **US5 (P1)**: Substitution engine
8. **US6 (P2)**: Shift swaps with validation
9. **US7 (P2)**: Notification service (Telegram + Email) + queue processor
10. **US8 (P2)**: UI schedule grid + CSV export
11. **US9 (P1)**: shiftcore package separation verified
12. **Polish**: Theme, date pickers, error handling, packaging, tests

---

## Parallel Opportunities

- All `shiftcore` modules can be developed in parallel after foundational models
- UI tabs can be built in parallel after shiftcore API stable
- Unit tests for each module can be written in parallel
- Notification providers (Telegram/Email) independent

---

## Notes

- Migration from current `db.py`/`scheduler.py` to `shiftcore` is breaking; use new schema
- Existing data: export/import script needed for current users
- PyInstaller spec file needed for Windows build
- Telegram bot token and SMTP config via environment variables