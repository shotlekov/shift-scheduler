# Shift Scheduler - User Guide

## Table of Contents

1. [Getting Started](#getting-started)
2. [Main Window Overview](#main-window-overview)
3. [Schedule View](#schedule-view)
4. [Teams & People](#teams--people)
5. [Availability Exceptions](#availability-exceptions)
6. [Shift Swaps](#shift-swaps)
7. [Notifications](#notifications)
8. [Exporting Schedules](#exporting-schedules)
9. [Tips & Best Practices](#tips--best-practices)
10. [Troubleshooting](#troubleshooting)

---

## Getting Started

### First Launch

1. **Download and run** the application:
   - Linux: `./dist/shift-scheduler`
   - Windows: `dist/shift-scheduler.exe`
   - From source: `python src/app.py`

2. **Configure your rotation group** (first time only):
   - The app creates a default rotation group automatically
   - Go to **Schedule View** tab → set **Cycle Start** date
   - Choose **Shift Model**: 2-shift or 3-shift

3. **Create teams**:
   - Go to **Teams & People** tab
   - Click **Add Team**
   - Set name, color, and initial shift offset

4. **Add people to teams**:
   - Select a team in the left panel
   - Click **Add Person** in the right panel
   - Enter name and role

5. **Generate your first schedule**:
   - Go to **Schedule View** tab
   - Set **Start Date** and **End Date**
   - Click **Generate Schedule**

---

## Main Window Overview

The application has 5 tabs accessible from the top:

| Tab | Purpose |
|-----|---------|
| **Schedule View** | View and generate shift schedules |
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

### Schedule Controls

| Field | Description |
|-------|-------------|
| **Start Date** | First date of schedule range (ISO format: YYYY-MM-DD) |
| **End Date** | Last date of schedule range |
| **Cycle Start** | Reference date for rotation cycle (must match rotation group) |
| **Shift Model** | 2-shift (Day/Swing) or 3-shift (adds Night) |
| **Load Schedule** | Loads existing assignments for the date range |

### Schedule Grid

The grid shows:
- **Rows**: Each date in the range
- **Columns**: Date, Day of week, one column per team
- **Cells**: Show shift (1st/2nd/3rd/OFF) and assigned person
- **Substitute indicator**: "(S)" after name means substitute

**Color coding:**
- Light theme: Alternating row colors for readability
- Dark theme: Slate-based color scheme

### Date Details Panel (Right Side)

Click any date row to see:
- All shifts and assignments for that date
- Substitutions and conflicts

### Person Details Panel

Select a person from dropdown → **View Schedule** to see:
- Their personal schedule for the date range
- Shift times, team, substitute status, notes

---

## Teams & People

### Teams Panel (Left)

**Columns:** ID, Name, Color

**Actions:**
- **Add Team** — Create new team
- **Edit Team** — Modify name, color, offset
- **Delete Team** — Removes team and all members

**Team Offset:**
- Determines where team starts in rotation cycle
- 2-shift (6-day cycle): Offsets 0, 2, 4 for 3 teams
- 3-shift (10-day cycle): Offsets 0, 2, 4, 6, 8 for 5 teams
- Offset 0 = starts on 1st shift (days 0,1)
- Offset 2 = starts on 2nd shift (days 2,3)
- Offset 4 = starts on OFF days (days 4,5)

### People Panel (Right)

**Columns:** ID, Name, Team, Role, Active

**Actions:**
- **Add Person** — Add to selected team
- **Edit Person** — Change name, role
- **Delete Person** — Remove person
- **Toggle Active** — Activate/deactivate (inactive people won't be scheduled)

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

## Exporting Schedules

### CSV Export

1. Load or generate a schedule in **Schedule View**
2. Click **Export CSV**
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