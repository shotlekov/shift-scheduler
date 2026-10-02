#!/bin/bash
# Shift Scheduler Launcher Script
# Activates virtual environment and runs the application

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Install/upgrade required packages
pip install --upgrade pip

# Run the application
python "$SCRIPT_DIR/src/app.py"

# Deactivate virtual environment when done
deactivate