# Feature Specification: Shift Scheduler Redesign

**Feature Branch**: `001-shift-scheduler-redesign`

**Created**: 2026-10-02

**Status**: Draft

**Input**: User description: A desktop application for managing team shift schedules with rotation schemes, availability tracking, substitution, fairness balancing, and notifications. Core logic packaged separately for future WebUI migration.

## User Scenarios & Testing

### User Story 1 - Rotation Group & Team Management (Priority: P1)

As a shift supervisor, I want to configure a rotation group with a shift pattern (2-shift 6-day or 3-shift 10-day), create teams with auto-assigned offsets, and manage team members, so that the schedule engine knows who works when.

**Why this priority**: Foundation for all scheduling; without correct rotation config, nothing else works.

**Independent Test**: Create a 2-shift rotation group, add 3 teams (auto-offsets 0,2,4), add 2 people per team, verify each team's shift for any date matches the pattern.

**Acceptance Scenarios**:
1. **Given** empty system, **When** I create a 2-shift rotation group with cycle start 2026-01-01, **Then** pattern is [1,1,2,2,0,0] and cycle_start is saved
2. **Given** 2-shift rotation group, **When** I add 3 teams, **Then** they receive offsets 0, 2, 4 automatically
3. **Given** team with offset 0, **When** I query shift for cycle_start date, **Then** it returns 1st shift
4. **Given** team with offset 2, **When** I query shift for cycle_start date, **Then** it returns 2nd shift
5. **Given** team with offset 4, **When** I query shift for cycle_start date, **Then** it returns OFF

---

### User Story 2 - Availability Exceptions (Priority: P1)

As a shift supervisor, I want to mark operators as unavailable for date ranges (sick, vacation), so they are automatically excluded from shift assignments during that period.

**Why this priority**: Core operational need; sick/vacation handling is daily reality.

**Independent Test**: Add exception for person A from 2026-01-10 to 2026-01-12, generate schedule for that week, verify person A has no assignments in that range.

**Acceptance Scenarios**:
1. **Given** person with no exceptions, **When** I add sick exception 2026-01-10 to 2026-01-12, **Then** person is unavailable for those 3 dates
2. **Given** person with exception, **When** I generate schedule covering exception dates, **Then** person receives zero assignments in that range
3. **Given** exception deleted, **When** I regenerate schedule, **Then** person is eligible again

---

### User Story 3 - Schedule Generation with Constraints (Priority: P1)

As a shift supervisor, I want to generate a schedule for a date range that respects all hard constraints (1 shift/day, 12h rest, max consecutive shifts), so the output is legally and physically viable.

**Why this priority**: The core value proposition; invalid schedules are useless.

**Independent Test**: Generate 14-day schedule for 3 teams × 2 people, verify zero constraint violations via automated checker.

**Acceptance Scenarios**:
1. **Given** valid rotation group and people, **When** I generate schedule, **Then** every assigned person has exactly 1 shift per calendar day
3. **Given** person assigned 2nd shift on day N, **When** schedule generated, **Then** same person not assigned 1st shift on day N+1 (12h rest)
4. **Given** person assigned 1st shift on day N, **When** schedule generated, **Then** same person not assigned 2nd shift on day N-1 (12h rest)
5. **Given** person with 5 consecutive shifts, **When** schedule generated, **Then** person gets day off on day 6
6. **Given** 3-shift mode, **When** person has 3 consecutive 3rd shifts, **Then** person gets day off on day 4

---

### User Story 4 - Fairness Balancing (Priority: P1)

As a shift supervisor, I want shift assignments balanced across all operators over a rolling 28-day window, so no one is overburdened while others get fewer shifts.

**Why this priority**: Operational fairness prevents burnout and grievances; explicitly requested.

**Independent Test**: Generate 28-day schedule for 6 people, verify shift count variance ≤ 1.

**Acceptance Scenarios**:
1. **Given** 6 people in rotation group, **When** I generate 28-day schedule, **Then** max(shift_counts) - min(shift_counts) ≤ 1
2. **Given** person with fewer shifts in window, **When** choosing between eligible candidates, **Then** system prefers person with lower count
3. **Given** tie in shift counts, **When** choosing, **Then** system prefers person with oldest last_assignment_date

---

### User Story 5 - Automatic Substitution (Priority: P1)

As a shift supervisor, when a scheduled operator is unavailable, I want the system to automatically find and assign a substitute from teams that are off that day, respecting all constraints and fairness.

**Why this priority**: Daily operational need; manual substitution is error-prone.

**Independent Test**: Mark person A unavailable on day X, generate schedule, verify substitute from off-team assigned, all constraints pass.

**Acceptance Scenarios**:
1. **Given** person A scheduled but has exception on day X, **When** generating schedule, **Then** substitute from off-team assigned to that shift
2. **Given** multiple eligible substitutes, **When** choosing, **Then** system picks one with fewest shifts in fairness window
3. **Given** no eligible substitute (all off-team members violate constraints), **When** generating, **Then** shift marked unfilled with reason

---

### User Story 6 - Shift Swaps with Validation (Priority: P2)

As a shift supervisor, I want to record shift swaps between two operators with full constraint validation, so swaps don't create violations.

**Why this priority**: Swaps happen frequently; unvalidated swaps break constraints.

**Independent Test**: Create swap between person A (1st shift) and person B (2nd shift) on same day, verify both pass constraints post-swap.

**Acceptance Scenarios**:
1. **Given** valid swap request, **When** I submit swap, **Then** swap recorded and both persons' constraints validated
2. **Given** swap would cause 12h rest violation for person A, **When** I submit, **Then** swap rejected with specific error
3. **Given** swap would cause max consecutive violation for person B, **When** I submit, **Then** swap rejected

---

### User Story 7 - Notifications (Priority: P2)

As a shift supervisor, I want notifications sent via Telegram (person DM, team group, all-teams group) and Email (person only) when assignments change, substitutions happen, swaps are approved, or schedule is regenerated.

**Why this priority**: Communication is critical for operations; people must know their shifts.

**Independent Test**: Trigger each notification type, verify message sent to correct targets with correct content.

**Acceptance Scenarios**:
1. **Given** new assignment created, **When** notification sent, **Then** person receives DM, team group receives message, all-teams group receives message
2. **Given** substitution made, **When** notification sent, **Then** original person + substitute + team group + all-teams group notified
3. **Given** swap approved, **When** notification sent, **Then** both persons receive DM + email, team group notified
4. **Given** schedule regenerated, **When** notification sent, **Then** team group + all-teams group receive summary

---

### User Story 8 - CSV Export & UI (Priority: P2)

As a shift supervisor, I want to view the schedule in a grid (date × teams) and export to CSV for printing/sharing.

**Why this priority**: Daily usability; export needed for posting physical schedules.

**Independent Test**: Generate schedule, view grid, export CSV, verify CSV matches grid.

**Acceptance Scenarios**:
1. **Given** generated schedule, **When** I open Schedule View tab, **Then** grid shows date, day, and each team's shift+person
2. **Given** schedule with substitutes, **When** I view grid, **Then** substitutes marked with (S) indicator
3. **Given** schedule, **When** I export CSV, **Then** file contains Date, Day, Team1 Shift, Team1 Person, Team1 Sub, Team2..., Team3...

---

### User Story 9 - Core Package Separation (Priority: P1)

As a developer, I want all scheduling logic in a separate `shiftcore` package with no UI dependencies, so it can be reused by a future WebUI.

**Why this priority**: Architectural requirement for future WebUI migration.

**Independent Test**: Import `shiftcore` in a clean Python environment, run scheduler, verify no Tkinter imports.

**Acceptance Scenarios**:
1. **Given** clean venv, **When** `pip install -e ./shiftcore`, **Then** imports work without Tkinter
2. **Given** `shiftcore.scheduler.generate_schedule()`, **When** called with valid inputs, **Then** returns assignments without UI code

---

## Edge Cases

- What happens when rotation group cycle_start is in the past vs future?
- How does system handle leap years in rotation cycle?
- What if all off-team members are unavailable for substitution?
- What if fairness window has no eligible candidates for a shift?
- How are notifications handled if Telegram API is down? (queue + retry)
- What if person has both Telegram and Email? (send both)
- How to handle team member moving between teams mid-schedule?
- What if rotation group is changed (2-shift → 3-shift) with existing schedule?

---

## Requirements

### Functional Requirements

- **FR-001**: System MUST support creating a rotation group with configurable pattern (2-shift 6-day default, 3-shift 10-day option)
- **FR-002**: System MUST auto-assign team offsets (0, 2, 4...) when teams are added to rotation group
- **FR-003**: System MUST allow manual override of team offsets
- **FR-004**: System MUST calculate each team's shift for any date based on pattern + offset + cycle_start
- **FR-005**: System MUST support CRUD for teams (name, color, rotation_group_id, offset)
- **FR-006**: System MUST support CRUD for persons (name, team_id, role, active, contacts)
- **FR-007**: System MUST support availability exceptions (person_id, start_date, end_date, reason)
- **FR-008**: System MUST exclude persons with active exceptions from shift eligibility
- **FR-009**: System MUST enforce max 1 shift per calendar day per person
- **FR-010**: System MUST enforce ≥12 hours rest between shifts (blocks 2nd→1st next day, 1st→2nd prev day, 3rd→1st next day)
- **FR-011**: System MUST enforce max 5 consecutive shifts for 1st/2nd shift
- **FR-012**: System MUST enforce max 3 consecutive shifts for 3rd shift
- **FR-013**: System MUST balance shift counts across all persons in rotation group over rolling 28-day window
- **FR-014**: System MUST prefer person with fewer shifts in fairness window when assigning
- **FR-015**: System MUST break fairness ties by preferring person with oldest last_assignment_date
- **FR-016**: System MUST find substitutes from teams that are OFF on the shift date
- **FR-017**: System MUST validate substitutes against all constraints + fairness before assigning
- **FR-018**: System MUST mark shift unfilled if no eligible substitute exists
- **FR-019**: System MUST support shift swaps between two persons with full constraint validation
- **FR-020**: System MUST reject swaps that would violate any constraint for either person
- **FR-021**: System MUST send Telegram notifications to: person DM, team group, all-teams group
- **FR-022**: System MUST send Email notifications to: person only
- **FR-023**: System MUST notify on: new assignment, substitution, swap approval, schedule regeneration
- **FR-024**: System MUST queue notifications and retry on failure (Telegram/Email)
- **FR-025**: System MUST export schedule to CSV with columns: Date, Day, Team1 Shift, Team1 Person, Team1 Sub, Team2..., TeamN...
- **FR-026**: System MUST display schedule grid with date, day, and per-team shift+person+sub-indicator
- **FR-027**: System MUST package all scheduling logic in `shiftcore/` with zero UI dependencies
- **FR-028**: System MUST use SQLite for persistence (single file, no external DB)
- **FR-029**: System MUST support light/dark theme in desktop UI
- **FR-030**: System MUST run on Linux (primary) and Windows (packaged via PyInstaller)

### Key Entities

- **RotationGroup**: name, shift_model (2-shift|3-shift), pattern[ShiftType], cycle_start_date, active
- **Team**: id, name, color, rotation_group_id, offset (int, 0..pattern_len-1)
- **Person**: id, name, team_id, role, active, telegram_chat_id, email
- **AvailabilityException**: id, person_id, start_date, end_date, reason
- **ShiftAssignment**: id, date, shift_type (1|2|3), person_id, team_id, is_substitute, substitute_for_id, notes
- **ShiftSwap**: id, date, person_a_id, person_b_id, shift_a, shift_b, approved
- **PersonShiftCounter**: person_id, period_start (28-day window), shift_count, last_assignment_date
- **NotificationQueue**: id, target_type (person_dm|team_group|all_teams_group|email), target_id, message, status, retries

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: Schedule generation for 14 days × 3 teams × 2 people completes in <2 seconds
- **SC-002**: Zero constraint violations in generated schedules (verified by automated test suite)
- **SC-003**: Fairness variance (max - min shifts per person) ≤ 1 over any 28-day window
- **SC-004**: Substitution success rate ≥ 95% when off-team has ≥2 eligible members
- **SC-005**: Notification delivery success rate ≥ 99% (with retry)
- **SC-006**: CSV export matches on-screen grid 100%
- **SC-007**: `shiftcore` package imports in clean venv without Tkinter/PyQt dependencies
- **SC-008**: PyInstaller build produces working .exe on Windows and binary on Linux

---

## Assumptions

- Single rotation group active at a time (no concurrent departments)
- 2-shift mode is MVP; 3-shift is Phase 2
- Telegram bot token and chat IDs configured externally (env vars)
- SMTP credentials configured externally (env vars)
- SQLite database file stored in `data/shift_scheduler.db`
- Maximum 20 teams, 100 persons (performance scope)
- Schedule generation runs on-demand, not real-time
- Operators do not self-serve; supervisor manages all
- No authentication in MVP (single-user desktop app)
- Timezone: local system timezone (no multi-TZ support)

---

## Constitution Check

This specification aligns with the project constitution:
- ✅ Single responsibility: `shiftcore` for logic, UI separate
- ✅ Testability: Each user story independently testable
- ✅ No premature optimization: SQLite, simple fairness algorithm
- ✅ Explicit constraints: All hard constraints enumerated
- ✅ Observability: Notification queue with status tracking