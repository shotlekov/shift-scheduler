# Shift Scheduler - Documentation

## Overview

Shift Scheduler is a desktop application for managing team shift schedules with rotation patterns, constraint validation, and notification support. It supports both 2-shift and 3-shift rotation models.

## Quick Links

- [User Guide](user-guide.md) — How to use the application
- [Architecture](architecture.md) — System design and components
- [API Reference](api.md) — shiftcore library API
- [Developer Guide](developer-guide.md) — Contributing and development setup
- [Deployment](deployment.md) — Building and distributing

## Architecture

```
shift-scheduler/
├── shiftcore/          # Core scheduling library (no UI dependencies)
│   ├── models.py       # Data models (Team, Person, ShiftAssignment, etc.)
│   ├── constraints.py  # Constraint validation (rest hours, max consecutive, etc.)
│   ├── rotation.py     # Rotation engine (pattern-based team shifts)
│   ├── fairness.py     # Fairness engine (balanced shift distribution)
│   ├── scheduler.py    # Schedule generation with substitution
│   ├── swaps.py        # Shift swap validation
│   ├── notifications.py # Telegram and email notification service
│   ├── storage.py      # SQLite repository
│   └── exceptions.py   # Custom exceptions
├── src/
│   ├── app.py          # Tkinter desktop GUI
│   └── shiftcore_adapter.py  # Compatibility adapter
├── tests/              # Unit tests (83 tests)
├── data/               # SQLite database storage
├── build.spec          # PyInstaller build configuration
├── build.sh            # Build script
└── docs/               # This documentation
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
2. Configure your rotation group (2-shift or 3-shift model)
3. Add teams with their shift offsets
4. Add people to each team
5. Set availability exceptions for people who are unavailable
6. Generate a schedule

### Shift Models

#### 2-Shift Model (Current)
- **Shift 1**: 06:00 - 14:00
- **Shift 2**: 14:00 - 22:00
- **Teams**: 3 teams with 6-day cycle `[1,1,2,2,0,0]`
- **Max consecutive**: 5 shifts

#### 3-Shift Model
- **Shift 1**: 06:00 - 14:00
- **Shift 2**: 14:00 - 22:00
- **Shift 3**: 22:00 - 06:00 (night shift, crosses midnight)
- **Teams**: 5 teams with 10-day cycle `[1,1,2,2,0,0,3,3,0,0]`
- **Max consecutive**: 5 shifts (3 for night shift)

### Constraint Rules

1. **One shift per day**: A person cannot work more than one shift on the same day
2. **Rest hours**: Minimum 12 hours between shifts
3. **Max consecutive**: Maximum 5 consecutive shifts (3 for night shifts)
4. **Availability**: People with availability exceptions cannot be scheduled

### Notifications

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

## Known Limitations

1. **Desktop only**: Currently a desktop application. WebUI planned for future.
2. **Single database**: Uses a local SQLite database. No multi-user support.
3. **Manual notification setup**: Telegram bot token and SMTP credentials must be configured manually.
4. **No import/export**: CSV export is available, but import is not yet implemented.

## Future Enhancements

1. **WebUI**: Migrate to a web-based interface using FastAPI + React
2. **Multi-user support**: Add authentication and concurrent editing
3. **Import/Export**: Support for importing schedules from CSV
4. **Mobile app**: Native mobile application for shift management
5. **Advanced reporting**: Generate reports on shift distribution and fairness metrics

## License

MIT License - see LICENSE file for details.