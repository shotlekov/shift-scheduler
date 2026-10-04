# Shift Scheduler

A desktop application for managing team shift schedules with rotation schemes, availability tracking, constraint validation, fairness balancing, and notification support.

## Features

- **Rotation Models**: 2-shift (Day/Swing) and 3-shift (Day/Swing/Night) with auto-team creation
- **Team Management**: Auto-generated teams with correct offsets and color coding
- **Person Management**: Add team members with roles, Telegram, email, and active/inactive status
- **Availability Tracking**: Mark persons as unavailable for date ranges (vacation, sick, training)
- **Constraint Validation**:
  - One shift per day per person
  - Minimum 12 hours rest between shifts (handles night shift crossing midnight)
  - Maximum consecutive shifts (5 for day/swing, 3 for night)
  - Automatic substitution from OFF teams when needed
- **Fairness Balancing**: Rolling 28-day window with shift count + last assignment tiebreaker
- **Shift Swaps**: Exchange shifts between team members with full constraint validation
- **Schedule Generation**: Generate schedules in advance with automatic conflict resolution
- **Notifications**: Telegram (DM, team group, all-teams group) + Email with retry queue
- **Export**: Export schedules to CSV format
- **Modern UI**: Light/dark theme, searchable schedule grid with hover tooltips

## Shift Models

### 2-Shift Model (Default)
- **Shift 1**: 06:00 - 14:00
- **Shift 2**: 14:00 - 22:00
- **Teams**: 3 teams with 6-day cycle `[1,1,2,2,0,0]`
- **Max consecutive**: 5 shifts
- **Offsets**: 0, 2, 4 (evenly distributed)

### 3-Shift Model
- **Shift 1**: 06:00 - 14:00
- **Shift 2**: 14:00 - 22:00
- **Shift 3**: 22:00 - 06:00 (night shift, crosses midnight)
- **Teams**: 5 teams with 10-day cycle `[1,1,2,2,0,0,3,3,0,0]`
- **Max consecutive**: 5 shifts (3 for night shift)
- **Offsets**: 0, 2, 4, 6, 8 (evenly distributed)

## Architecture

```
shift-scheduler/
├── shiftcore/          # Core scheduling library (no UI dependencies)
│   ├── models.py       # Data models + SHIFT_MODELS config, TEAM_COLORS
│   ├── constraints.py  # Constraint validation (rest hours, max consecutive, etc.)
│   ├── rotation.py     # Rotation engine (pattern-based team shifts)
│   ├── fairness.py     # Fairness engine (balanced shift distribution)
│   ├── scheduler.py    # Schedule generation with substitution
│   ├── swaps.py        # Shift swap validation
│   ├── notifications.py # Telegram and email notification service
│   ├── storage.py      # SQLite repository + auto-team creation
│   └── exceptions.py   # Custom exceptions
├── src/
│   ├── app.py          # Tkinter desktop GUI
│   └── shiftcore_adapter.py  # Compatibility adapter + CSV import, demo data
├── tests/              # Unit tests (83 tests, all passing)
├── data/               # SQLite database storage
├── build.spec          # PyInstaller build configuration
├── build.sh            # Build script
└── docs/               # Documentation
```

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/shotlekov/shift-scheduler.git
cd shift-scheduler

# Install dependencies (Python 3.10+ required)
pip install -r requirements.txt

# Run the application
python src/app.py
```

### Pre-built Binary

Download the latest release from the [releases page](https://github.com/shotlekov/shift-scheduler/releases), or build from source:

```bash
./build.sh
```

The executable will be in `dist/shift-scheduler` (Linux) or `dist/shift-scheduler.exe` (Windows).

## Requirements

- Python 3.10+
- tkinter (usually included with Python)
- Optional: `python-telegram-bot>=20.0` and `aiosmtplib>=2.0` for notifications

Install optional dependencies:
```bash
pip install python-telegram-bot aiosmtplib
```

## Usage

### Getting Started

1. Launch the application
2. Configure your rotation group (2-shift or 3-shift model) — teams are auto-created
3. Add people (unassigned by default, then assign to teams via dropdown)
4. Set availability exceptions for people who are unavailable
5. Generate a schedule
6. View results in **Schedule Grid** tab with search and tooltips

### Schedule Grid Tab

The new **Schedule Grid** tab provides a clean, read-only view:
- **Simplified columns**: DATE | DAY | TEAM 1 | TEAM 2 | TEAM 3... (shift only)
- **Zebra striping** for readability
- **Search bar** to filter by person name
- **Hover tooltips** showing squad members for each team/date
- **18 months** of schedule from Initial Date

### Adapter Enhancements

The `shiftcore_adapter.py` provides additional utilities:
- **CSV Import**: Import people from CSV (columns: name, role, telegram, email)
- **Demo Data Generation**: Generate test people for development
- **Unassigned Persons**: Create people without team assignment, assign later
- **Shift Model Info**: Query shift model configurations programmatically

## Constraint Rules

1. **One shift per day**: A person cannot work more than one shift on the same day
2. **Rest hours**: Minimum 12 hours between shifts
3. **Max consecutive**: Maximum 5 consecutive shifts (3 for night shifts)
4. **Availability**: People with availability exceptions cannot be scheduled

## Notifications

The application supports notifications via:
- **Telegram**: Direct messages, team groups, and all-teams group
- **Email**: Individual email notifications

Configure notification settings in the "Notifications" tab.

## Testing

Run the test suite:

```bash
python -m pytest tests/ -v
```

All 83 tests should pass.

## Building

### Linux

```bash
./build.sh
```

### Windows

```bash
pyinstaller build.spec --clean --noconfirm
```

The executable will be in `dist/shift-scheduler.exe`.

## Documentation

- [User Guide](docs/user-guide.md) — How to use the application
- [Architecture](docs/architecture.md) — System design and components
- [API Reference](docs/api.md) — shiftcore library API
- [Developer Guide](docs/developer-guide.md) — Contributing and development setup
- [Deployment](docs/deployment.md) — Building and distributing

## Known Limitations

1. **Desktop only**: Currently a desktop application. WebUI planned for future.
2. **Single database**: Uses a local SQLite database. No multi-user support.
3. **Manual notification setup**: Telegram bot token and SMTP credentials must be configured manually.

## Future Enhancements

1. **WebUI**: Migrate to a web-based interface using FastAPI + React
2. **Multi-user support**: Add authentication and concurrent editing
3. **Mobile app**: Native mobile application for shift management
4. **Advanced reporting**: Generate reports on shift distribution and fairness metrics

## License

MIT License - see LICENSE file for details.