# Data Model: Shift Scheduler Redesign

**Spec**: `.specify/specs/001-shift-scheduler-redesign/spec.md`
**Plan**: `.specify/specs/001-shift-scheduler-redesign/plan.md`

## Entity Relationship Diagram

```
RotationGroup (1) ─────< (N) Team
Team (1) ──────────────< (N) Person
Person (1) ────────────< (N) AvailabilityException
Person (1) ────────────< (N) ShiftAssignment
Person (1) ────────────< (N) PersonShiftCounter
ShiftAssignment (N) ──< (1) Team
ShiftAssignment (N) ──< (1) Person (substitute_for)
ShiftSwap (1) ────────< (2) Person (person_a, person_b)
NotificationQueue (1) ──< (N) [triggers from all above]
```

## Entities

### RotationGroup
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | INTEGER | PK, AUTOINCREMENT | Unique identifier |
| name | TEXT | NOT NULL | Display name |
| shift_model | TEXT | NOT NULL, CHECK('2-shift','3-shift') | '2-shift' or '3-shift' |
| pattern | TEXT | NOT NULL | JSON array of shift types (e.g., `[1,1,2,2,0,0]`) |
| cycle_start_date | TEXT | NOT NULL | ISO date (YYYY-MM-DD) |
| active | INTEGER | DEFAULT 1 | Only one active at a time |
| created_at | TEXT | DEFAULT datetime('now') | Audit |

**Pattern Examples**:
- 2-shift: `[1,1,2,2,0,0]` (6 days)
- 3-shift: `[1,1,2,2,0,0,3,3,0,0]` (10 days)

**Shift Type Encoding**: `1`=1st, `2`=2nd, `3`=3rd, `0`=off

### Team
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | INTEGER | PK, AUTOINCREMENT | Unique identifier |
| name | TEXT | NOT NULL | Display name |
| color | TEXT | DEFAULT '#2563eb' | Hex color for UI |
| rotation_group_id | INTEGER | NOT NULL, FK→RotationGroup.id | Parent rotation |
| offset | INTEGER | NOT NULL, DEFAULT 0 | Pattern index offset (0..len-1) |
| created_at | TEXT | DEFAULT datetime('now') | Audit |

**Offset Assignment**: Auto-assigned as `0, 2, 4...` (pattern_len / team_count) on creation; manually overridable.

### Person
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | INTEGER | PK, AUTOINCREMENT | Unique identifier |
| name | TEXT | NOT NULL | Display name |
| team_id | INTEGER | NOT NULL, FK→Team.id ON DELETE CASCADE | Team membership |
| role | TEXT | DEFAULT 'operator' | Role label |
| active | INTEGER | DEFAULT 1 | 1=active, 0=inactive |
| telegram_chat_id | TEXT | NULLABLE | Telegram DM chat ID |
| email | TEXT | NULLABLE | Email address |
| created_at | TEXT | DEFAULT datetime('now') | Audit |
| UNIQUE(name, team_id) | | | No duplicate names per team |

### AvailabilityException
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | INTEGER | PK, AUTOINCREMENT | Unique identifier |
| person_id | INTEGER | NOT NULL, FK→Person.id ON DELETE CASCADE | Affected person |
| start_date | TEXT | NOT NULL | ISO date (inclusive) |
| end_date | TEXT | NOT NULL | ISO date (inclusive) |
| reason | TEXT | DEFAULT '' | 'sick', 'vacation', 'other' |
| created_at | TEXT | DEFAULT datetime('now') | Audit |

**Availability Check**: Person unavailable on date D if `start_date <= D <= end_date`

### ShiftAssignment
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | INTEGER | PK, AUTOINCREMENT | Unique identifier |
| schedule_date | TEXT | NOT NULL | ISO date |
| shift_type | INTEGER | NOT NULL, CHECK(1,2,3) | 1=1st, 2=2nd, 3=3rd |
| person_id | INTEGER | NOT NULL, FK→Person.id ON DELETE CASCADE | Assigned person |
| team_id | INTEGER | NOT NULL, FK→Team.id ON DELETE CASCADE | Team context |
| is_substitute | INTEGER | DEFAULT 0 | 1=substitute assignment |
| substitute_for_id | INTEGER | FK→Person.id ON DELETE SET NULL | Original person if substitute |
| notes | TEXT | DEFAULT '' | Free text |
| created_at | TEXT | DEFAULT datetime('now') | Audit |
| UNIQUE(schedule_date, shift_type, person_id) | | | One shift per person per day |

### ShiftSwap
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | INTEGER | PK, AUTOINCREMENT | Unique identifier |
| schedule_date | TEXT | NOT NULL | ISO date |
| person_a_id | INTEGER | NOT NULL, FK→Person.id ON DELETE CASCADE | First person |
| person_b_id | INTEGER | NOT NULL, FK→Person.id ON DELETE CASCADE | Second person |
| shift_a | INTEGER | NOT NULL, CHECK(1,2,3) | Person A's shift |
| shift_b | INTEGER | NOT NULL, CHECK(1,2,3) | Person B's shift |
| approved | INTEGER | DEFAULT 1 | 1=approved, 0=pending/rejected |
| created_at | TEXT | DEFAULT datetime('now') | Audit |

### PersonShiftCounter
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| person_id | INTEGER | NOT NULL, FK→Person.id ON DELETE CASCADE | Person |
| period_start | TEXT | NOT NULL | ISO date (window start, 28-day rolling) |
| shift_count | INTEGER | DEFAULT 0 | Shifts in this window |
| last_assignment_date | TEXT | NULLABLE | Most recent assignment date |
| PRIMARY KEY (person_id, period_start) | | | One row per person per window |

**Window Calculation**: `period_start = assignment_date - (assignment_date.day % 28)` or similar rolling logic

### NotificationQueue
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | INTEGER | PK, AUTOINCREMENT | Unique identifier |
| target_type | TEXT | NOT NULL, CHECK('person_dm','team_group','all_teams_group','email') | Delivery target |
| target_id | TEXT | NOT NULL | Chat ID, email, or 'all' |
| message | TEXT | NOT NULL | Message content |
| status | TEXT | DEFAULT 'pending', CHECK('pending','sent','failed') | Delivery status |
| retries | INTEGER | DEFAULT 0 | Retry count |
| created_at | TEXT | DEFAULT datetime('now') | Queued timestamp |
| sent_at | TEXT | NULLABLE | Sent timestamp |

## Indexes

```sql
CREATE INDEX idx_assignments_date ON shift_assignments(schedule_date);
CREATE INDEX idx_assignments_person_date ON shift_assignments(person_id, schedule_date);
CREATE INDEX idx_assignments_team_date ON shift_assignments(team_id, schedule_date);
CREATE INDEX idx_exceptions_person_date ON availability_exceptions(person_id, start_date, end_date);
CREATE INDEX idx_swaps_date ON shift_swaps(schedule_date);
CREATE INDEX idx_notifications_status ON notification_queue(status);
CREATE INDEX idx_counters_person_period ON person_shift_counters(person_id, period_start);
```

## Shift Definitions (Configuration)

```python
SHIFT_DEFINITIONS = {
    1: {"name": "1st", "start": "06:00", "end": "14:00", "hours": 8},
    2: {"name": "2nd", "start": "14:00", "end": "22:00", "hours": 8},
    3: {"name": "3rd", "start": "22:00", "end": "06:00", "hours": 8},  # crosses midnight
}

MAX_CONSECUTIVE = {
    1: 5,  # 1st shift
    2: 5,  # 2nd shift
    3: 3,  # 3rd shift (night)
}
```

## Fairness Window

- **Window Size**: 28 days (rolling)
- **Metric**: Total shift count per person in window
- **Selection**: Min shift count → tiebreak: oldest last_assignment_date
- **Persistence**: `PersonShiftCounter` table updated on each assignment

## Notification Targets

| Target Type | Target ID | Recipients |
|-------------|-----------|------------|
| person_dm | Person.telegram_chat_id | Individual operator |
| team_group | Team.telegram_chat_id (config) | All team members |
| all_teams_group | Global chat ID (config) | All operators |
| email | Person.email | Individual operator |

## Migration from Legacy Schema

| Legacy Table | New Table(s) | Notes |
|--------------|--------------|-------|
| teams | teams + rotation_groups | Create default rotation_group, migrate teams |
| people | persons | Add telegram_chat_id, email columns |
| availability_exceptions | availability_exceptions | Direct mapping |
| shift_assignments | shift_assignments | Add shift_type (was shift), is_substitute, substitute_for_id |
| shift_swaps | shift_swaps | Add shift_a, shift_b (was shift_a, shift_b) |
| schedule_metadata | (removed) | Replace with rotation_groups.cycle_start_date |

## Constraints Summary (Enforced in Code)

1. **One shift per day**: `UNIQUE(schedule_date, shift_type, person_id)` + application check
2. **12h rest**: No 1st after 2nd prev day; no 2nd before 1st next day; no 1st after 3rd prev day
3. **Max consecutive**: 5 for shift 1/2, 3 for shift 3
4. **Availability**: Exceptions exclude person from eligibility
5. **Active only**: Only `active=1` persons eligible
6. **Team membership**: Assignment team_id must match person's team_id (except substitutes)
7. **Substitute from off-team**: Substitute's team must be OFF on that date