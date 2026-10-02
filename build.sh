#!/bin/bash
# Build script for Shift Scheduler
# Creates standalone executables for Windows and Linux

set -e

echo "Building Shift Scheduler..."

# Ensure data directory exists
mkdir -p data

# Build for current platform
echo "Building for $(uname -s)..."
pyinstaller build.spec --clean --noconfirm

# Copy the built executable to dist/
echo "Build complete!"
echo "Executable location: dist/shift-scheduler"

# For Windows cross-compilation (requires Wine on Linux)
if [ "$1" == "--windows" ]; then
    echo "Building for Windows..."
    pyinstaller build.spec --clean --noconfirm --target-arch x86_64 --distpath dist/windows
    echo "Windows executable: dist/windows/shift-scheduler.exe"
fi

echo "Done!"
