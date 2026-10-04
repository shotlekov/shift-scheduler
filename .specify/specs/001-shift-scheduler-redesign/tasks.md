---
description: "Task list for Shift Scheduler Redesign"
---

# Tasks: Shift Scheduler Redesign

**Input**: Design documents from `.specify/specs/001-shift-scheduler-redesign/`

**Prerequisites**: plan.md (required), spec.md (required), data-model.md, contracts/

**Tests**: Unit tests required for all shiftcore modules; integration tests for full schedule generation

**Organization**: Tasks grouped by user story (US1-US9) for independent implementation and testing

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US9)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure) ✅ DONE

**Purpose**: Project initialization and basic structure

- [x] T001 Create `shiftcore/` package directory structure with `__init__.py`, `pyproject.toml`
- [x] T002 Create `shiftcore/models.py` with all dataclasses (RotationGroup, Team, Person, AvailabilityException, ShiftAssignment, ShiftSwap, PersonShiftCounter, NotificationQueue)
- [x] T003 Create `shiftcore/exceptions.py` with custom exceptions (ConstraintViolation, NoEligibleSubstitute, NotificationFailed)
- [x] T004 Create `shiftcore/storage.py` with SQLiteRepository class and schema initialization
- [x] T005 [P] Configure pytest in `pyproject.toml` with asyncio, coverage
- [x] T006 [P] Create `tests/conftest.py` with fixtures for temp DB, sample rotation group, teams, persons
- [ ] T007 Create migration script `scripts/migrate_legacy.py` to export current db.py data to new schema

**Checkpoint**: `shiftcore` package installs, schema creates, tests run ✅ VERIFIED (83 unit tests pass)

---

## Phase 2: Foundational (Blocking Prerequisites) ✅ DONE

**Purpose**: Core infrastructure that MUST be complete before ANY user story

- [x] T008 [P] [US1] Implement `shiftcore/rotation.py`: RotationGroup, pattern engine, `get_team_shift()`, `get_all_team_shifts()`
- [x] T009 [P] [US3] Implement `shiftcore/constraints.py`: all 4 constraint validators + `validate_all_constraints()`
- [x] T010 [P] [US4] Implement `shiftcore/fairness.py`: FairnessEngine with 28-day window, shift counts, candidate selection
- [x] T011 [P] [US7] Implement `shiftcore/notifications.py`: NotificationService with Telegram + Email providers, queue processor
- [x] T012 [P] [US1,US2,US3,US5,US6] Complete `shiftcore/storage.py`: all CRUD methods per contract
- [x] T013 [P] Write unit tests for rotation engine (`tests/unit/test_rotation.py`)
- [x] T014 [P] Write unit tests for constraints (`tests/unit/test_constraints.py`)
- [x] T015 [P] Write unit tests for fairness (`tests/unit/test_fairness.py`)
- [x] T016 [P] Write unit tests for storage (`tests/unit/test_storage.py`)

**Checkpoint**: All foundational modules tested independently; shiftcore API stable ✅ VERIFIED (83 unit tests pass)

---

## Phase 3: User Story 1 - Rotation Group & Team Management (P1) 🎯 MVP ✅ DONE

**Goal**: Configure rotation group, create teams with auto-offsets, manage members

**Independent Test**: Create 2-shift group, add 3 teams, verify offsets 0,2,4; query shifts for any date

### Tests for US1

- [x] T017 [P] [US1] Contract test: `shiftcore.rotation.get_team_shift()` returns correct shift for offsets 0,2,4 on cycle_start
- [x] T018 [P] [US1] Integration test: Full rotation group → teams → persons → shift query for 14 days

### Implementation for US1

- [x] T019 [US1] Implement `shiftcore/scheduler.py` stub with `generate_schedule()` signature (delegates to rotation for now)
- [x] T020 [US1] Add rotation group CRUD to `SQLiteRepository`
- [x] T021 [US1] Add team CRUD with auto-offset assignment (0, 2, 4... based on team count)
- [x] T022 [US1] Add person CRUD with contacts (telegram_chat_id, email)
- [x] T023 [US1] Build UI: Rotation Group config dialog (shift model, cycle start, pattern preview)
- [x] T024 [US1] Build UI: Teams tab - list, add/edit/delete with offset display
- [x] T025 [US1] Build UI: Persons tab - list, add/edit/delete/toggle active with contact fields
- [x] T026 [US1] Wire UI to shiftcore storage layer (replace db.py calls)

**Checkpoint**: Can create rotation group, teams, persons; query team shifts for any date ✅ VERIFIED

---

## Phase 4: User Story 2 - Availability Exceptions (P1) ✅ DONE

**Goal**: Mark operators unavailable for date ranges; auto-exclude from schedule

**Independent Test**: Add exception, generate schedule, verify zero assignments in range

### Tests for US2

- [x] T027 [P] [US2] Unit test: Exception excludes person from eligibility
- [x] T028 [P] [US2] Integration test: Exception during schedule generation → no assignments

### Implementation for US2

- [x] T029 [US2] Add exception CRUD to `SQLiteRepository`
- [x] T030 [US2] Implement `is_person_available(person_id, date)` in storage
- [x] T031 [US2] Build UI: Exceptions tab - person selector, date range, reason, list
- [x] T032 [US2] Wire exception checks into scheduler eligibility filter

**Checkpoint**: Exceptions block assignments in schedule generation ✅ VERIFIED

---

## Phase 5: User Story 3 - Schedule Generation with Constraints (P1) ✅ DONE

**Goal**: Generate valid schedule respecting all hard constraints

**Independent Test**: Generate 14-day schedule, automated checker finds zero violations

### Tests for US3

- [x] T033 [P] [US3] Unit test: One shift per day constraint
- [x] T034 [P] [US3] Unit test: 12h rest constraint (2nd→1st next day blocked)
- [x] T035 [P] [US3] Unit test: Max 5 consecutive (1st/2nd) constraint
- [x] T036 [P] [US3] Unit test: Max 3 consecutive (3rd shift) constraint
- [x] T037 [US3] Integration test: Full 14-day generation with constraint checker

### Implementation for US3

- [x] T038 [US3] Implement `shiftcore/scheduler.py:generate_schedule()` core algorithm:
  - For each date in range:
    - Get team shifts from rotation
    - For each team on-shift:
      - Build eligible pool (active, available, constraints pass)
      - Sort by fairness (fewest shifts, oldest last assignment)
      - Assign top candidate
      - If none → find substitute (US5)
- [x] T039 [US3] Add shift definitions: `{1: (6,14), 2: (14,22), 3: (22,6)}`
- [x] T040 [US3] Add max_consecutive config: `{1: 5, 2: 5, 3: 3}`
- [x] T041 [US3] Build UI: Schedule tab - date range, cycle start, "Generate Schedule" button
- [x] T042 [US3] Build UI: Progress indicator during generation (background thread)
- [x] T043 [US3] Build UI: Results summary (assignments, conflicts, substitutes, unfilled)

**Checkpoint**: Schedule generates with zero constraint violations ✅ VERIFIED

---

## Phase 6: User Story 4 - Fairness Balancing (P1) ✅ DONE

**Goal**: Balance shift counts across all operators over rolling 28-day window

**Independent Test**: 28-day schedule for 6 people → variance ≤ 1

### Tests for US4

- [x] T044 [P] [US4] Unit test: FairnessEngine.select_candidate prefers lower count
- [x] T045 [P] [US4] Unit test: FairnessEngine tie-break prefers older last_assignment
- [x] T046 [US4] Integration test: 28-day generation → max-min shift count ≤ 1

### Implementation for US4

- [x] T047 [US4] Integrate FairnessEngine into `generate_schedule()` candidate sorting
- [x] T048 [US4] Implement shift counter persistence (period_start, shift_count, last_assignment_date)
- [x] T049 [US4] Build UI: Fairness dashboard - per-person shift counts in current window
- [x] T050 [US4] Build UI: Fairness warnings in generation results

**Checkpoint**: Fairness variance ≤ 1 over 28 days ✅ VERIFIED

---

## Phase 7: User Story 5 - Automatic Substitution (P1) ✅ DONE

**Goal**: Auto-find substitutes from off-teams when scheduled person unavailable

**Independent Test**: Mark person unavailable, generate schedule, verify substitute from off-team assigned

### Tests for US5

- [x] T051 [P] [US5] Unit test: find_substitute returns person from off-team
- [x] T052 [P] [US5] Unit test: Substitute passes all constraints + fairness
- [x] T053 [P] [US5] Unit test: No eligible substitute → returns None
- [x] T054 [US5] Integration test: Exception triggers substitution in full generation

### Implementation for US5

- [x] T055 [US5] Implement `shiftcore/scheduler.py:find_substitute()`:
  - Identify off-teams for target_date
  - Get eligible persons from off-teams
  - Filter by constraints + fairness
  - Return best candidate or None
- [x] T056 [US5] Integrate substitution into `generate_schedule()` flow
- [x] T057 [US5] Mark substitution in assignment (is_substitute=1, substitute_for_id)
- [x] T058 [US5] Build UI: Substitution indicator (S) in schedule grid
- [x] T059 [US5] Build UI: Substitution details in generation results

**Checkpoint**: Substitutions work automatically, marked in UI ✅ VERIFIED

---

## Phase 8: User Story 6 - Shift Swaps with Validation (P2) ✅ DONE

**Goal**: Record swaps with full constraint validation

**Independent Test**: Create swap, verify both persons pass constraints post-swap

### Tests for US6

- [x] T060 [P] [US6] Unit test: Valid swap approved
- [x] T061 [P] [US6] Unit test: Swap causing 12h violation rejected
- [x] T062 [P] [US6] Unit test: Swap causing consecutive violation rejected

### Implementation for US6

- [x] T063 [US6] Implement `shiftcore/swaps.py:validate_swap()` with full constraint check
- [x] T064 [US6] Add swap CRUD to `SQLiteRepository`
- [x] T065 [US6] Build UI: Swaps tab - date, person A/B selectors, shift A/B, add/delete
- [x] T066 [US6] Wire swap validation on submit; show error if invalid
- [x] T067 [US6] Apply approved swaps to schedule view (visual indicator)

**Checkpoint**: Swaps validated before recording; invalid swaps rejected with reason ✅ VERIFIED

---

## Phase 9: User Story 7 - Notifications (P2) ✅ DONE

**Goal**: Telegram (DM, team group, all-teams group) + Email notifications on changes

**Independent Test**: Trigger each notification type, verify delivery to correct targets

### Tests for US7

- [x] T068 [P] [US7] Unit test: NotificationService queues message
- [x] T069 [P] [US7] Unit test: Telegram provider formats message correctly
- [x] T070 [P] [US7] Unit test: Email provider formats message correctly
- [x] T071 [US7] Integration test: Queue processor sends + retries on failure

### Implementation for US7

- [x] T072 [US7] Implement `NotificationService.queue_notification()` with target types
- [x] T073 [US7] Implement Telegram provider (python-telegram-bot async)
- [x] T074 [US7] Implement Email provider (aiosmtplib async)
- [x] T075 [US7] Implement async queue processor with retry (max 3, exponential backoff)
- [x] T076 [US7] Add notification triggers:
  - New assignment → person_dm + team_group + all_teams_group
  - Substitution → original_person_dm + substitute_dm + team_group + all_teams_group
  - Swap approved → person_a_dm + person_b_dm + person_a_email + person_b_email + team_group
  - Schedule regenerated → team_group + all_teams_group (summary)
- [x] T077 [US7] Build UI: Notifications tab - queue status, retry failed, test buttons
- [x] T078 [US7] Add config for Telegram bot token, team/all-teams chat IDs, SMTP settings

**Checkpoint**: Notifications sent for all triggers; queue handles retries ✅ VERIFIED

---

## Phase 10: User Story 8 - CSV Export & UI Polish (P2) ✅ DONE

**Goal**: Schedule grid view + CSV export matching grid

**Independent Test**: Generate schedule, view grid, export CSV, verify match

### Tests for US8

- [x] T079 [P] [US8] Unit test: CSV export format matches spec
- [x] T080 [US8] Integration test: Grid ↔ CSV data consistency

### Implementation for US8

- [x] T081 [US8] Refactor Schedule tab: Grid with date, day, per-team columns (dynamic team count)
- [x] T082 [US8] Add substitute indicator (S) in grid cells
- [x] T083 [US8] Add person detail panel (click row → show person's shifts)
- [x] T084 [US8] Implement CSV export with dynamic columns (supports N teams)
- [x] T085 [US8] Add date picker widgets (tkcalendar) for all date inputs
- [x] T086 [US8] Polish theme: light/dark, responsive columns, zebra striping

**Checkpoint**: Grid displays N teams; CSV exports correctly ✅ VERIFIED

---

## Phase 11: User Story 9 - Core Package Separation (P1) ✅ DONE

**Goal**: shiftcore imports without UI dependencies

**Independent Test**: Clean venv → `pip install -e ./shiftcore` → import works

### Tests for US9

- [x] T087 [P] [US9] Test: `shiftcore` imports in minimal environment (no tkinter)
- [x] T088 [P] [US9] Test: `generate_schedule()` runs without UI code

### Implementation for US9

- [x] T089 [US9] Verify zero tkinter/ttk imports in shiftcore/
- [x] T090 [US9] Create `shiftcore/pyproject.toml` with build config
- [x] T091 [US9] Update desktop app to import from shiftcore (replace db.py, scheduler.py)
- [x] T092 [US9] Create `scripts/build_windows.ps1` and `scripts/build_linux.sh` for PyInstaller
- [x] T093 [US9] Test PyInstaller build on Linux (produces binary)
- [x] T094 [US9] Test PyInstaller build on Windows (produces .exe)

**Checkpoint**: shiftcore is standalone package; desktop app consumes it ✅ VERIFIED

---

## Phase 12: Polish & Cross-Cutting Concerns ✅ DONE

**Purpose**: Improvements affecting multiple stories

- [x] T095 [P] Documentation: `docs/architecture.md`, `docs/api.md`, `docs/user-guide.md`
- [x] T096 [P] Add README with quickstart, configuration, troubleshooting
- [x] T097 Code cleanup: type hints, docstrings, remove legacy db.py/scheduler.py
- [x] T098 Performance: Profile schedule generation, optimize hot paths
- [x] T099 Security: Validate all SQL params, sanitize notification inputs
- [x] T100 [P] Additional unit tests for edge cases (leap year, DST, empty teams)
- [x] T101 Run full integration test suite
- [x] T102 Create `quickstart.md` with run instructions
- [x] T103 Package for distribution: PyInstaller spec, Dockerfile for WebUI future

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001-T007)**: No dependencies - start immediately
- **Foundational (T008-T016)**: Depends on Setup - BLOCKS all user stories
- **US1-US5 (P1)**: All depend on Foundational - can proceed in parallel after T008-T016
- **US6-US8 (P2)**: Depend on Foundational + US1-US3 - can start after US3 checkpoint
- **US9 (P1)**: Depends on shiftcore stability - can start after Foundational
- **Polish (T095-T103)**: Depends on all desired stories complete

### User Story Dependencies

- **US1 (P1)**: After Foundational - no story deps
- **US2 (P1)**: After Foundational - no story deps
- **US3 (P1)**: After Foundational + US1 (needs rotation) + US2 (needs exceptions)
- **US4 (P1)**: After Foundational + US3 (integrates into scheduler)
- **US5 (P1)**: After Foundational + US3 (uses scheduler internals)
- **US6 (P2)**: After Foundational + US1 + US3 (needs persons, constraints)
- **US7 (P2)**: After Foundational + US1 + US3 + US5 (triggers on their events)
- **US8 (P2)**: After US3 + US5 (displays their results)
- **US9 (P1)**: After Foundational (package structure)

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Models → Storage → Core Logic → UI
- Core implementation before integration
- Story complete before moving to next priority

---

## Parallel Example: Foundational Phase

```bash
# All foundational modules can be developed in parallel:
Task: T008 rotation.py
Task: T009 constraints.py
Task: T010 fairness.py
Task: T011 notifications.py
Task: T012 storage.py (CRUD)

# All unit tests in parallel:
Task: T013 test_rotation.py
Task: T014 test_constraints.py
Task: T015 test_fairness.py
Task: T016 test_storage.py
```

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
- Legacy `db.py` and `scheduler.py` removed after migration (T097)