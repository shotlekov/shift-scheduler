# Shift Scheduler - User Guide

## Table of Contents

1. [Getting Started](#getting-started)
2. [Main Window Overview](#main-window-overview)
3. [Schedule View](#schedule-view)
4. [Schedule Grid](#schedule-grid)
5. [Teams & People](#teams--people)
6. [Availability Exceptions](#availability-exceptions)
7. [Shift Swaps](#shift-swaps)
8. [Notifications](#notifications)
9. [Exporting Schedules](#exporting-schedules)
10. [Tips & Best Practices](#tips--best-practices)
11. [Troubleshooting](#troubleshooting)

---

## Getting Started

### First Launch

1. **Download and run** the application:
   - Linux: `./dist/shift-scheduler`
   - Windows: `dist/shift-scheduler.exe`
   - From source: `python src/app.py`

2. **Configure your rotation group** (first time only):
   - The app creates a default rotation group automatically
   - Go to **Schedule View** tab → set **Initial Date (Cycle Start)**
   - Choose **Shift Model**: 2-shift or 3-shift
   - **Teams are auto-created** with correct offsets and colors

3. **Add people**:
   - Go to **Teams & People** tab
   - Click **Add Person** in the right panel
   - Enter name, Telegram, email, role
   - Assign to a team via dropdown (or leave Unassigned)

4. **Generate your first schedule**:
   - Go to **Schedule View** tab
   - (Optional) Set manual shifts for first 2 days in the grid
   - Click **Generate Schedule**
   - View results in **Schedule Grid** tab

---

## Main Window Overview

The application has 6 tabs accessible from the top:

| Tab | Purpose |
|-----|---------|
| **Schedule View** | Configure and generate shift schedules |
| **Schedule Grid** | View simplified schedule with search and tooltips |
| **Teams & People** | Manage teams and team members |
| **Availability** | Set unavailable periods (vacation, sick) |
| **Shift Swaps** | Request and manage shift swaps |
| **Notifications** | Configure Telegram/Email notifications |

**Bottom Bar:**
- **Generate Schedule** — Creates new schedule for date range
- **Export CSV** — Exports current schedule to CSV
- **Status** — Shows current operation status

**Theme Switcher** (top-right): Toggle between Light and Dark mode

---

## Schedule View

This tab contains all schedule configuration and generation controls.

### Schedule Controls

| Field | Description |
|-------|-------------|
| **Initial Date (Cycle Start)** | Reference date for rotation cycle (ISO format: YYYY-MM-DD) |
| **Shift Model** | 2-shift (Day/Swing) or 3-shift (adds Night) |
| **Load Schedule** | Loads existing assignments for 18 months from Initial Date |

### Manual First 2 Days Configuration

Below the controls, a grid allows you to manually set shifts for the first 2 days of the cycle:

- **Rows**: Each team
- **Columns**: Day 1, Day 2 (with dates shown)
- **Options**: AUTO (use rotation), 1st, 2nd, 3rd, OFF
- **Apply Manual Configuration** button regenerates the full 18-month schedule with your overrides

### Actions

| Button | Action |
|--------|--------|
| **Generate Schedule** | Creates new 18-month schedule from Initial Date |
| **Export CSV** | Exports current schedule to CSV |
| **Refresh Grid** | Reloads schedule data in Schedule Grid tab |

### Status Bar

Shows current operation status at the bottom of the tab.

---

## Schedule Grid

This tab provides a clean, read-only view of the generated schedule with powerful filtering and inspection tools.

### Grid Layout

| Column | Description |
|--------|-------------|
| **Date** | Schedule date (YYYY-MM-DD) |
| **Day** | Day of week (Monday, Tuesday, etc.) |
| **Team 1** | Shift for Team 1 (1st/2nd/3rd/OFF) |
| **Team 2** | Shift for Team 2 |
| **Team 3...** | Additional teams based on shift model |

**Features:**
- **Zebra striping** — Alternating row colors for readability
- **18 months** — Shows ~548 days from Initial Date
- **Shift only** — Cells show shift type (1st/2nd/3rd/OFF), not person names
- **Substitute indicator** — "(S)" after shift means substitute assigned

### Search Bar

Type a person's name to filter the grid:
- Only rows where that person is assigned will show
- Works across all teams and dates
- Clear button resets the filter

### Hover Tooltips

Hover over any team cell to see a popup with squad details:
- Team name and date
- All assigned members for that shift
- Substitute status if applicable
- Default squad members if no assignment exists

### Keyboard Navigation

- `Tab` / `Shift+Tab` — Navigate between cells
- `Arrow keys` — Move between rows/columns
- `Escape` — Clear search filter

---

---

## Teams & People

### Teams Panel (Left)

**Columns:** ID, Name, Color, Offset, Members

**Actions:**
- **Regenerate Teams** — Recreates teams for current rotation group with correct offsets/colors
  - 2-shift (6-day cycle): 3 teams with offsets 0, 2, 4
  - 3-shift (10-day cycle): 5 teams with offsets 0, 2, 4, 6, 8
- Teams are **auto-generated** — no manual Add/Edit/Delete

**Team Offset:**
- Determines where team starts in rotation cycle
- **Auto-assigned** when using Regenerate Teams
- Offset 0 = starts on 1st shift (days 0,1)
- Offset 2 = starts on 2nd shift (days 2,3)
- Offset 4 = starts on OFF days (days 4,5)
- **Members** column shows count of assigned people

### People Panel (Right)

**Columns:** ID, Name, Telegram, Email, Team, Role, Active

**People are created unassigned** — assign to teams via dropdown.

**Actions:**
- **Add Person** — Creates unassigned person (Team = Unassigned)
  - Fields: Name, Telegram Chat ID, Email, Role, Team (dropdown)
- **Edit Person** — Modify any field including team assignment
- **Delete Person** — Remove person
- **Toggle Active** — Activate/deactivate (inactive people won't be scheduled)
- **Import CSV** — Import people from CSV file
- **Generate Demo People** — Creates 15 test people for testing

**Team Assignment:**
- Dropdown shows "Unassigned" + all teams
- Changing team updates member count in Teams panel instantly

**Roles:** operator, lead, supervisor (extensible for future)

### CSV Import Format

```csv
name,role,telegram,email
Alice Smith,operator,user123,alice@example.com
Bob Jones,lead,user456,bob@example.com
```

**Columns:** name (required), role (optional, defaults to "operator"), telegram (optional), email (optional)

**Roles:** operator, lead, supervisor (customizable)

---

## Availability Exceptions

Set periods when people are unavailable (vacation, sick leave, training).

### Adding an Exception

1. Select **Person** from dropdown
2. Set **Start Date** and **End Date** (inclusive)
3. Enter **Reason** (e.g., "Vacation", "Sick leave", "Training")
4. Click **Add Exception**

### Managing Exceptions

- **Exceptions List** shows all exceptions for selected person
- Select an exception → **Delete Selected** to remove
- **Refresh** button reloads exceptions for current person

**Important:** People with exceptions covering a date will NOT be scheduled on that date. The scheduler will automatically find substitutes from OFF teams.

---

## Shift Swaps

Allow two people to swap shifts on a specific date.

### Creating a Swap

1. Set **Date** for the swap
2. Select **Person A** and their **Shift** (1, 2, or 3)
3. Select **Person B** and their **Shift** (1, 2, or 3)
4. Click **Add Swap**

### Validation

The system automatically validates:
- Both people are active
- Both are available on that date (no exceptions)
- Swap doesn't violate rest hours (12h between shifts)
- Swap doesn't exceed max consecutive shifts
- No double-booking

If validation fails, an error message explains why.

### Managing Swaps

- **Swaps List** shows all swaps in ±30 days from today
- Select a swap → **Delete Selected** to remove
- Swaps are considered when generating schedules

---

## Notifications

Configure automated notifications for schedule changes.

### Telegram Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram
2. Copy the **Bot Token**
3. Create groups for:
   - **Team Group** — notifications for specific team
   - **All-Teams Group** — notifications for all teams
4. Get Chat IDs:
   - Add bot to groups
   - Send a message
   - Visit `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - Find `chat.id` (negative for groups)

### Email Setup

Configure SMTP settings:
- **SMTP Server** (e.g., smtp.gmail.com)
- **SMTP Port** (587 for TLS, 465 for SSL)
- **Username** (email address)
- **Password** (app password for Gmail)
- **From Address** (display name + email)

### Notification Triggers

| Trigger | Telegram | Email |
|---------|----------|-------|
| New assignment | Person DM + Team group + All-teams group | Person only |
| Substitution made | Person DM + Team group + All-teams group | Person only |
| Swap approved | Both persons DM + Team group | Both persons |
| Schedule regenerated | Team group + All-teams group | — |

### Notification Settings

- **Notify on shift swap** — Send when swap is created
- **Notify on substitution** — Send when substitute assigned
- **Notify on schedule change** — Send when schedule regenerated

### Notification History

View all sent/pending/failed notifications with:
- Type (person_dm, team_group, all_teams_group, email)
- Recipient
- Status (pending, sent, failed)
- Timestamp

---

## Importing People (Advanced)

The application supports importing people via CSV through the adapter API (not yet exposed in UI):

### CSV Format

```csv
name,role,telegram,email
Alice Smith,operator,user123,alice@example.com
Bob Jones,lead,user456,bob@example.com
```

### Using Python API

```python
from shiftcore_adapter import import_people_from_csv, generate_demo_people

# Import from CSV string
csv_data = """name,role,telegram,email
Alice Smith,operator,user123,alice@example.com
Bob Jones,lead,user456,bob@example.com"""
imported = import_people_from_csv(csv_data)
print(f"Imported {len(imported)} people")

# Generate demo data for testing
demo = generate_demo_people(20)
print(f"Generated {len(demo)} demo people")
```

---

## Exporting Schedules

### CSV Export

1. Generate a schedule in **Schedule View**
2. Click **Export CSV** (in Schedule View tab)
3. Choose filename and location
4. CSV includes:
   - Date, Day
   - For each team: Shift, Person, Substitute (Yes/No)

### CSV Format

```csv
Date,Day,Team 1 Shift,Team 1 Person,Team 1 Sub,Team 2 Shift,Team 2 Person,Team 2 Sub,Team 3 Shift,Team 3 Person,Team 3 Sub
2026-01-01,Thursday,1st,Alice,No,2nd,Bob,No,OFF,,No
2026-01-02,Friday,1st,Alice,No,2nd,Charlie,No,OFF,,No
```

**Note:** The CSV export includes person names and substitute status, while the Schedule Grid tab shows only shift types for clarity.

---

## Tips & Best Practices

### Rotation Setup

1. **Set Cycle Start correctly** — This is the anchor date for the rotation pattern. All schedule calculations reference this date.

2. **Use consistent offsets** — For 2-shift with 3 teams, use offsets 0, 2, 4. For 3-shift with 5 teams, use 0, 2, 4, 6, 8.

3. **Match team count to shift model** — 2-shift needs 3 teams, 3-shift needs 5 teams for full coverage.

### Fair Scheduling

1. **Keep teams balanced** — Similar number of people per team ensures fair distribution.

2. **Use availability exceptions** — Mark vacations/sick days in advance so scheduler finds substitutes automatically.

3. **Review fairness report** — After generation, check the variance (should be ≤1 for balanced).

### Substitutions

- Substitutes come from teams that are **OFF** that day
- The scheduler picks the fairest eligible person
- Substitutions are marked with "(S)" in the schedule grid

### Notifications

- Test Telegram/Email settings before relying on them
- Use "Load Settings" to verify saved configuration
- Check Notification History for delivery status

---

## Troubleshooting

### Common Issues

| Problem | Solution |
|---------|----------|
| "No rotation group configured" | Create a rotation group in Schedule View or Teams tab |
| "No available team members" | Add people to teams, check availability exceptions |
| "Insufficient rest hours" | Check previous/next day assignments; adjust manually or use swaps |
| "Max consecutive shifts exceeded" | Person has too many consecutive days; add exception or swap |
| Telegram notifications not sending | Verify bot token, chat IDs, and bot is in groups |
| Email notifications failing | Check SMTP settings, use app password for Gmail |
| Schedule grid empty | Click "Load Schedule" or "Generate Schedule" first |
| Theme not applying | Restart application after theme change |

### Database Issues

- Database file: `data/shift_scheduler.db`
- Backup before major changes: `cp data/shift_scheduler.db data/backup.db`
- Reset database: Delete `data/shift_scheduler.db` and restart app

### Performance

- For large date ranges (>60 days), generation may take a few seconds
- Use background processing (app stays responsive)
- Close unused tabs to free memory

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+N` | New team/person/exception/swap (context dependent) |
| `Ctrl+S` | Save (in dialogs) |
| `Escape` | Close dialog |
| `Tab` | Navigate between fields |
| `Enter` | Confirm dialog |

---

## Data Locations

| Data | Location |
|------|----------|
| SQLite Database | `data/shift_scheduler.db` |
| Configuration | Stored in database (schedule_metadata table) |
| Exported CSV | User-selected location |
| Logs | Console output (run from terminal to see) |

---

## Support

- **Issues**: [GitHub Issues](https://github.com/shotlekov/shift-scheduler/issues)
- **Documentation**: [GitHub Wiki](https://github.com/shotlekov/shift-scheduler/wiki)
- **Source Code**: [GitHub Repository](https://github.com/shotlekov/shift-scheduler)