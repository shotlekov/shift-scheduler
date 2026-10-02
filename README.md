# Shift Scheduler

A desktop application for managing team shift schedules with rotation schemes, availability tracking, and constraint validation.

## Features

- **Team Management**: Create and manage teams with color coding
- **Person Management**: Add team members with roles and active/inactive status
- **Rotation Scheme**: Automatic 6-day rotation (2 days 1st shift, 2 days 2nd shift, 2 days off)
- **Availability Tracking**: Mark persons as unavailable for date ranges
- **Constraint Validation**:
  - Cannot work 1st shift after 2nd shift on previous day
  - Cannot work 2nd shift before 1st shift on next day
  - Maximum 5 consecutive working days
  - Automatic substitution from resting team when needed
- **Shift Swaps**: Exchange shifts between team members
- **Schedule Generation**: Generate schedules in advance with automatic conflict resolution
- **Export**: Export schedules to CSV format
- **Substitution System**: Automatically find available substitutes from resting teams

## Shift Schedule
- **1st Shift**: 6:00 AM - 2:00 PM
- **2nd Shift**: 2:00 PM - 10:00 PM

## Rotation Pattern
Each team follows this 6-day cycle:
- Days 1-2: 1st shift
- Days 3-4: 2nd shift  
- Days 5-6: Day off

Teams are offset so each day has:
- One team on 1st shift
- One team on 2nd shift
- One team off

## Installation

1. Ensure Python 3.8+ is installed
2. Clone or copy this directory
3. Make the launcher script executable: `chmod +x start-app.sh`
4. Run the application: `./start-app.sh`

The application will automatically create a virtual environment and install dependencies on first run.

## Usage

1. **Setup Teams**: Create your teams in the "Teams & People" tab
2. **Add People**: Add team members to each team
3. **Set Availability**: Mark persons as unavailable for vacations, sick days, etc. in the "Availability" tab
4. **Generate Schedule**: Set date range and click "Generate Schedule"
5. **View Results**: Check the schedule in the "Schedule View" tab
6. **Manage Swaps**: Use the "Shift Swaps" tab to exchange shifts between team members
7. **Export**: Export the schedule to CSV for sharing or printing

## Constraints Enforced

- No person can work 1st shift immediately after working 2nd shift the previous day
- No person can work 2nd shift immediately before working 1st shift the next day
- No person can work more than 5 consecutive days
- When a person is unavailable, the system automatically finds substitutes from the team that is off that day
- Substitutes are also checked against all constraints

## Data Storage

All data is stored in a local SQLite database (`data/shift_scheduler.db`) in the application directory.

## License

MIT License