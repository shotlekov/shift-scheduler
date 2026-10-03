# Shift Scheduler - Architecture

## System Overview

Shift Scheduler follows a clean architecture with a clear separation between the core business logic (`shiftcore`) and the presentation layer (Tkinter desktop UI).

```
┌─────────────────────────────────────────────────────────────┐
│                    Presentation Layer                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  src/app.py (Tkinter GUI)                           │   │
│  │  - Schedule View tab                                │   │
│  │  - Teams & People tab                               │   │
│  │  - Availability tab                                 │   │
│  │  - Shift Swaps tab                                  │   │
│  │  - Notifications tab                                │   │
│  └─────────────────────────────────────────────────────┘   │
│                              │                              │
│                              ▼                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  src/shiftcore_adapter.py (Adapter Layer)           │   │
│  │  - Maps legacy UI calls to shiftcore API            │   │
│  │  - Provides backward compatibility                  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Core Library (shiftcore)                │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │  models.py  │ │ rotation.py │ │constraints.py│           │
│  │  - Data     │ │  - Pattern  │ │  - 1 shift/ │           │
│  │    classes  │ │    engine   │ │    day      │           │
│  └─────────────┘ └─────────────┘ │  - 12h rest │           │
│  ┌─────────────┐ ┌─────────────┐ │  - Max consec│           │
│  │ fairness.py │ │scheduler.py │ │  - Avail.   │           │
│  │  - 28-day   │ │  - Generate │ └─────────────┘           │
│  │    window   │ │    schedule │ ┌─────────────┐           │
│  └─────────────┘ │  - Substitute│ │   swaps.py  │           │
│  ┌─────────────┐ └─────────────┘ │  - Validate │           │
│  │notifications│ ┌─────────────┐ │    swaps    │           │
│  │  - Telegram │ │ storage.py  │ └─────────────┘           │
│  │  - Email    │ │  - SQLite   │ ┌─────────────┐           │
│  └─────────────┘ │    repo     │ │exceptions.py│           │
│                  └─────────────┘ │  - Custom   │           │
│                                 │    errors   │           │
│                                 └─────────────┘           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Data Layer                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  SQLite Database (data/shift_scheduler.db)          │   │
│  │  - rotation_groups                                  │   │
│  │  - teams                                            │   │
│  │  - persons                                          │   │
│  │  - availability_exceptions                          │   │
│  │  - shift_assignments                                │   │
│  │  - shift_swaps                                      │   │
│  │  - person_shift_counters (fairness)                 │   │
│  │  - notification_queue                               │   │
│  │  - schedule_metadata                                │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Models (`shiftcore/models.py`)

Pure Python dataclasses with no external dependencies:

- **ShiftType** (IntEnum): OFF=0, FIRST=1, SECOND=2, THIRD=3
- **RotationGroup**: name, shift_model, pattern[], cycle_start_date
  - **Factory**: `create_default(name, shift_model, cycle_start)` — creates with SHIFT_MODELS defaults
  - **Helpers**: `get_team_count()`, `get_shifts()`, `get_max_consecutive()`
- **Team**: name, color, rotation_group_id, offset
- **Person**: name, team_id, role, active, telegram_chat_id, email
- **AvailabilityException**: person_id, start_date, end_date, reason
- **ShiftAssignment**: schedule_date, shift_type, person_id, team_id, is_substitute
- **ShiftSwap**: schedule_date, person_a_id, person_b_id, shift_a, shift_b
- **PersonShiftCounter**: Fairness tracking (rolling 28-day window)
- **NotificationQueue**: Queued notifications for delivery
- **ScheduleResult**: Result container for schedule generation

Constants:
- **SHIFT_DEFINITIONS**: Hours for each shift type
- **MAX_CONSECUTIVE**: Max consecutive shifts per type (defaults, overridden by shift model)
- **DEFAULT_PATTERNS**: Legacy 2-shift and 3-shift rotation patterns
- **SHIFT_MODELS**: Centralized shift model configurations (patterns, team counts, shifts, max_consecutive)
- **TEAM_COLORS**: Default color palette for auto-assigned teams

### 2. Rotation Engine (`shiftcore/rotation.py`)

Calculates team shifts based on rotation patterns:

- **RotationEngine**: Main class for computing shifts
- **get_team_shift()**: Get shift for a team offset on a date
- **get_all_team_shifts()**: Get shifts for all teams on a date
- **get_off_teams()**: Teams that are OFF on a date (for substitution)
- **get_on_shift_teams()**: Teams working a specific shift
- **validate_pattern()**: Validates pattern correctness using SHIFT_MODELS
- **create_default_rotation_group()**: Factory for standard patterns (delegates to RotationGroup.create_default)
- **calculate_team_offsets()**: Evenly distributes team offsets

### 3. Constraints (`shiftcore/constraints.py`)

Four hard constraint validators:

1. **check_one_shift_per_day()**: Max 1 shift per person per day
2. **check_rest_hours()**: Minimum 12 hours between shifts
   - Handles 3rd shift crossing midnight correctly
3. **check_max_consecutive()**: Max consecutive working days
   - 5 for 1st/2nd shift, 3 for 3rd shift
4. **check_availability()**: Respects availability exceptions
5. **check_active_status()**: Only active persons can be scheduled

**validate_all_constraints()**: Runs all validators in sequence
**get_violations()**: Returns detailed list of all violations

### 4. Fairness Engine (`shiftcore/fairness.py`)

Balances shift distribution across operators:

- **Rolling 28-day window** aligned to reference date
- **Primary criterion**: Fewest shifts in window
- **Tiebreaker**: Longest time since last assignment
- **FairnessEngine.select_candidate()**: Chooses best eligible person
- **FairnessEngine.record_assignment()**: Updates counters
- **FairnessEngine.get_fairness_report()**: Generates balance report

### 5. Scheduler (`shiftcore/scheduler.py`)

Main schedule generation with substitution:

- **generate_schedule()**: Generates complete schedule for date range
  - Iterates day by day, team by team
  - Assigns from default team first
  - Falls back to substitution from OFF teams
  - Tracks conflicts, substitutions, unfilled shifts
  - Returns ScheduleResult with assignments and fairness report

- **find_substitute()**: Finds eligible substitute from OFF teams
  - Filters by constraints + fairness
  - Returns best candidate or None

### 6. Swaps (`shiftcore/swaps.py`)

Validates shift swaps between two persons:

- **validate_swap()**: Simulates swap and checks constraints for both
- **get_swap_violations()**: Detailed violations for both persons
- Uses temporary assignment IDs (-1, -2) for exclusion in validation

### 7. Notifications (`shiftcore/notifications.py`)

Async notification service with retry logic:

- **TelegramProvider**: Uses python-telegram-bot
- **EmailProvider**: Uses aiosmtplib with TLS
- **NotificationService**: Queue processor with exponential backoff
- **Message templates**: Assignment, substitution, swap, schedule regenerated

### 8. Storage (`shiftcore/storage.py`)

SQLite repository with full CRUD for all entities:

- **SQLiteRepository**: Main class with connection management
- **WAL mode** for better concurrency
- **Indexes** on frequently queried columns
- **Transaction support** for batch operations
- **Metadata table** for configuration (Telegram, SMTP, etc.)
- **Auto-team creation**: `create_teams_for_rotation_group()` — deletes existing teams and creates new ones with correct offsets/colors based on shift model
- **Member count queries**: `get_team_member_count()`, `get_all_team_member_counts()`
- **FK behavior**: `team_id` in persons uses `ON DELETE SET NULL` (was CASCADE)

## Data Flow

### Schedule Generation

```
User clicks "Generate Schedule"
         │
         ▼
src/app.py:_on_generate_schedule()
         │
         ▼
shiftcore_adapter.generate_schedule()
         │
         ▼
shiftcore.scheduler.generate_schedule()
         │
         ├── RotationEngine: Get team shifts for each day
         ├── Constraints: Validate each assignment
         ├── FairnessEngine: Select best candidate
         └── find_substitute(): If team unavailable
         │
         ▼
SQLiteRepository.save_assignments() (transaction)
         │
         ▼
Return ScheduleResult → UI populates grid
```

### Auto-Team Creation

```
User creates rotation group (or changes shift model)
         │
         ▼
src/app.py:_on_create_rotation_group()
         │
         ▼
shiftcore_adapter.create_teams_for_rotation_group()
         │
         ▼
SQLiteRepository.create_teams_for_rotation_group()
         │
         ├── Delete existing teams for rotation group
         ├── Calculate offsets via calculate_team_offsets()
         ├── Create teams with TEAM_COLORS
         └── Return created teams
         │
         ▼
UI refreshes teams list
```

### Shift Swap Validation

```
User clicks "Add Swap"
         │
         ▼
src/app.py:_on_add_swap()
         │
         ▼
shiftcore_adapter.add_shift_swap()
         │
         ▼
shiftcore.swaps.validate_swap()
         │
         ├── Create simulated assignments (with temp IDs -1, -2)
         ├── validate_all_constraints() for person A with shift B
         └── validate_all_constraints() for person B with shift A
         │
         ▼
If valid: SQLiteRepository.save_swap()
         │
         ▼
UI refreshes swaps list
```

## Design Principles

1. **Separation of Concerns**: Core logic has zero UI dependencies
2. **Testability**: All core modules have comprehensive unit tests (83 tests)
3. **Extensibility**: New shift models, constraints, notification channels can be added
4. **Data Integrity**: SQLite constraints, transactions, WAL mode
5. **Performance**: Indexed queries, efficient algorithms, background threading for UI
6. **Migration Ready**: Adapter pattern allows gradual UI migration

## Future: WebUI Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   React SPA     │────▶│   FastAPI       │────▶│   shiftcore     │
│   (Frontend)    │     │   (Backend)     │     │   (Library)     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   PostgreSQL    │
                       │   (or SQLite)   │
                       └─────────────────┘
```

The `shiftcore` package will be reused unchanged - only the presentation and storage layers change.