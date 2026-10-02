# Shift Scheduler - Deployment Guide

## Table of Contents

1. [Building Executables](#building-executables)
2. [Linux Deployment](#linux-deployment)
3. [Windows Deployment](#windows-deployment)
4. [Distribution](#distribution)
5. [Configuration](#configuration)
6. [Troubleshooting Builds](#troubleshooting-builds)

---

## Building Executables

### Prerequisites

**Linux:**
```bash
# Ubuntu/Debian
sudo apt-get install python3-tk python3-venv

# Fedora
sudo dnf install python3-tkinter

# Arch
sudo pacman -S tk
```

**Windows:**
- Python 3.10+ from python.org
- Visual Studio Build Tools (for some dependencies)

**Cross-compilation (Linux → Windows):**
```bash
# Requires Wine
sudo apt-get install wine64
pip install pyinstaller
```

### Build Script

Use the provided build script:

```bash
# Linux build
./build.sh

# Windows build (on Windows)
pyinstaller build.spec --clean --noconfirm

# Windows build (on Linux with Wine)
./build.sh --windows
```

### Build Configuration (build.spec)

```python
# Key settings in build.spec
a = Analysis(
    ['src/app.py'],
    pathex=['.', 'src', 'shiftcore'],
    datas=[('data', 'data')],  # Include data directory
    hiddenimports=[
        'shiftcore',
        'shiftcore.models',
        'shiftcore.constraints',
        'shiftcore.rotation',
        'shiftcore.fairness',
        'shiftcore.scheduler',
        'shiftcore.swaps',
        'shiftcore.notifications',
        'shiftcore.storage',
        'shiftcore.exceptions',
    ],
    # ...
)

exe = EXE(
    # ...
    name='shift-scheduler',
    console=False,  # No console window (GUI app)
    upx=True,       # Compress with UPX
    icon='src/assets/icon.ico',  # Optional icon
)
```

### Build Output

```
dist/
├── shift-scheduler          # Linux executable
└── shift-scheduler.exe      # Windows executable (if built)
```

---

## Linux Deployment

### Standalone Executable

The PyInstaller build creates a self-contained executable:

```bash
# Build
./build.sh

# Test
./dist/shift-scheduler

# Distribute
# Copy dist/shift-scheduler to target machine
# No Python installation required on target
```

### System Requirements

| Requirement | Minimum |
|-------------|---------|
| OS | Linux (glibc 2.28+) |
| Architecture | x86_64 |
| Display | X11 or Wayland |
| RAM | 256 MB |
| Disk | 100 MB |

### Dependencies Included

The executable bundles:
- Python 3.10+ interpreter
- All Python packages (shiftcore, tkinter, sqlite3, etc.)
- Tkinter runtime (Tcl/Tk libraries)
- SQLite library

### Installation Options

**Option 1: Direct executable**
```bash
# Copy to /usr/local/bin (requires sudo)
sudo cp dist/shift-scheduler /usr/local/bin/

# Or to user directory
mkdir -p ~/.local/bin
cp dist/shift-scheduler ~/.local/bin/
```

**Option 2: AppImage (recommended for distribution)**
```bash
# Install appimagetool
wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage

# Create AppDir structure
mkdir -p ShiftScheduler.AppDir/usr/bin
cp dist/shift-scheduler ShiftScheduler.AppDir/usr/bin/
# Add .desktop file and icon
./appimagetool-x86_64.AppImage ShiftScheduler.AppDir
```

**Option 3: DEB/RPM package**
```bash
# Use fpm or similar tools
# fpm -s dir -t deb -n shift-scheduler -v 1.0.0 dist/shift-scheduler=/usr/bin/
```

### Data Directory

The application stores data in `data/shift_scheduler.db` relative to the executable.

**For system-wide install:**
```bash
# Create data directory
sudo mkdir -p /var/lib/shift-scheduler
sudo chown $USER /var/lib/shift-scheduler

# Run with custom data path (modify app.py or use symlink)
ln -s /var/lib/shift-scheduler data
```

---

## Windows Deployment

### Building on Windows

```cmd
# Install dependencies
pip install pyinstaller python-telegram-bot aiosmtplib

# Build
pyinstaller build.spec --clean --noconfirm

# Output: dist/shift-scheduler.exe
```

### Building on Linux (Cross-compile)

```bash
# Install Wine and Python for Windows
sudo apt-get install wine64
# Download Python Windows installer and install via Wine
wine python-3.10.0-amd64.exe /quiet InstallAllUsers=1 PrependPath=1

# Install PyInstaller in Wine Python
wine python -m pip install pyinstaller python-telegram-bot aiosmtplib

# Build
./build.sh --windows
```

### Windows Requirements

| Requirement | Minimum |
|-------------|---------|
| OS | Windows 10 64-bit |
| Architecture | x86_64 |
| RAM | 256 MB |
| Disk | 150 MB |

### Distribution Options

**Option 1: Portable executable**
- Just distribute `dist/shift-scheduler.exe`
- Runs from any folder
- Data stored in `data/` subfolder

**Option 2: Installer (Inno Setup)**
```iss
; shift-scheduler.iss
[Setup]
AppName=Shift Scheduler
AppVersion=1.0.0
DefaultDirName={pf}\Shift Scheduler
OutputDir=dist
OutputBaseFilename=shift-scheduler-setup

[Files]
Source: "dist\shift-scheduler.exe"; DestDir: "{app}"
Source: "data\*"; DestDir: "{app}\data"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Shift Scheduler"; Filename: "{app}\shift-scheduler.exe"
Name: "{commondesktop}\Shift Scheduler"; Filename: "{app}\shift-scheduler.exe"
```

Compile with:
```bash
iscc shift-scheduler.iss
```

**Option 3: Microsoft Store / Winget**
- Package as MSIX for Store
- Submit to winget-pkgs repository

---

## Distribution

### Release Checklist

- [ ] All tests pass (`python -m pytest tests/ -v`)
- [ ] Version updated in `shiftcore/pyproject.toml` and `shiftcore/__init__.py`
- [ ] CHANGELOG.md updated
- [ ] Linux executable built and tested
- [ ] Windows executable built and tested
- [ ] Documentation updated
- [ ] GitHub Release created with artifacts

### GitHub Release

```bash
# Tag release
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0

# Create release on GitHub with:
# - dist/shift-scheduler (Linux)
# - dist/shift-scheduler.exe (Windows)
# - Release notes from CHANGELOG.md
```

### Distribution Channels

| Channel | Audience | Effort |
|---------|----------|--------|
| GitHub Releases | Developers, early adopters | Low |
| Website/Download page | General users | Medium |
| Microsoft Store | Windows users | High |
| Snap/Flatpak | Linux users | Medium |
| Homebrew | macOS users (future) | Medium |
| Chocolatey/Winget | Windows CLI users | Medium |

---

## Configuration

### Application Configuration

Configuration is stored in SQLite database (`schedule_metadata` table):

| Key | Description | Example |
|-----|-------------|---------|
| `telegram_bot_token` | Bot token from @BotFather | `123456:ABC-DEF...` |
| `telegram_team_chat_id` | Team group chat ID | `-1001234567890` |
| `telegram_all_chat_id` | All-teams group chat ID | `-1001234567891` |
| `smtp_server` | SMTP server hostname | `smtp.gmail.com` |
| `smtp_port` | SMTP port | `587` |
| `smtp_username` | SMTP username | `user@gmail.com` |
| `smtp_password` | SMTP password/app password | `abcd efgh ijkl mnop` |
| `smtp_from` | From email address | `Shift Scheduler <user@gmail.com>` |
| `notify_on_swap` | Enable swap notifications | `True` |
| `notify_on_substitution` | Enable substitution notifications | `True` |
| `notify_on_schedule_change` | Enable schedule change notifications | `False` |

### Setting Configuration

**Via UI:**
1. Open **Notifications** tab
2. Fill in fields
3. Click **Save Notification Settings**

**Via Database (for automation):**
```sql
INSERT INTO schedule_metadata (key, value) VALUES 
  ('telegram_bot_token', 'YOUR_TOKEN'),
  ('smtp_server', 'smtp.gmail.com')
ON CONFLICT(key) DO UPDATE SET value = excluded.value;
```

**Via Python:**
```python
from shiftcore import SQLiteRepository
from pathlib import Path

repo = SQLiteRepository(Path("data/shift_scheduler.db"))
repo.set_metadata("telegram_bot_token", "YOUR_TOKEN")
repo.set_metadata("smtp_server", "smtp.gmail.com")
```

### Environment Variables (Alternative)

For containerized deployments, you can pre-populate the database:

```dockerfile
# Dockerfile example
FROM python:3.10-slim
COPY dist/shift-scheduler /app/
COPY data/shift_scheduler.db /app/data/
WORKDIR /app
CMD ["./shift-scheduler"]
```

---

## Troubleshooting Builds

### Common Build Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: shiftcore` | Ensure `pathex` includes `.` and `shiftcore` in build.spec |
| `tkinter not found` | Install `python3-tk` (Linux) or ensure Python has tkinter (Windows) |
| `UPX not found` | Install UPX: `sudo apt-get install upx` or set `upx=False` in build.spec |
| `Icon not found` | Create `src/assets/icon.ico` or remove icon line from build.spec |
| `Permission denied` | Make build.sh executable: `chmod +x build.sh` |

### Runtime Issues

| Issue | Solution |
|-------|----------|
| `sqlite3.OperationalError: unable to open database file` | Ensure `data/` directory exists and is writable |
| `TclError: no display name` | Running headless? Use `xvfb-run ./shift-scheduler` or ensure DISPLAY is set |
| `Telegram notifications not working` | Verify bot token, chat IDs, and bot is added to groups |
| `Email notifications failing` | Use app password for Gmail, check SMTP settings |
| `Theme not applying` | Restart application after theme change |

### Debug Build

```bash
# Build with debug symbols
pyinstaller build.spec --clean --noconfirm --debug=all

# Run with verbose output
./dist/shift-scheduler --verbose 2>&1 | tee debug.log
```

### Size Optimization

```python
# In build.spec, add excludes to reduce size
a = Analysis(
    # ...
    excludes=[
        'matplotlib', 'numpy', 'pandas', 'scipy',
        'PIL', 'cv2', 'torch', 'tensorflow',
        'jupyter', 'notebook', 'IPython',
        'test', 'unittest', 'pdb', 'doctest',
    ],
    # ...
)
```

### Code Signing (Windows)

```bash
# Sign executable (requires certificate)
signtool sign /f certificate.pfx /p password /tr http://timestamp.digicert.com /td sha256 /fd sha256 dist/shift-scheduler.exe
```

### Code Signing (macOS - Future)

```bash
# When macOS support added
codesign --deep --force --verify --verbose --sign "Developer ID Application: Name" dist/shift-scheduler.app
```

---

## CI/CD Pipeline (GitHub Actions Example)

```yaml
# .github/workflows/build.yml
name: Build and Release

on:
  push:
    tags: ['v*']

jobs:
  build-linux:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          sudo apt-get update && sudo apt-get install -y python3-tk upx
          pip install pyinstaller python-telegram-bot aiosmtplib
      - name: Build
        run: ./build.sh
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: shift-scheduler-linux
          path: dist/shift-scheduler

  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: pip install pyinstaller python-telegram-bot aiosmtplib
      - name: Build
        run: pyinstaller build.spec --clean --noconfirm
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: shift-scheduler-windows
          path: dist/shift-scheduler.exe

  release:
    needs: [build-linux, build-windows]
    runs-on: ubuntu-latest
    steps:
      - name: Download artifacts
        uses: actions/download-artifact@v4
      - name: Create Release
        uses: softprops/action-gh-release@v1
        with:
          files: |
            shift-scheduler-linux/shift-scheduler
            shift-scheduler-windows/shift-scheduler.exe
          generate_release_notes: true
```

---

## Support Matrix

| Platform | Status | Notes |
|----------|--------|-------|
| Linux x86_64 | ✅ Supported | Primary target |
| Windows 10/11 x86_64 | ✅ Supported | Via PyInstaller |
| macOS | 🔄 Planned | Not yet tested |
| ARM64 Linux | 🔄 Planned | Raspberry Pi, etc. |
| Web (Future) | 📋 Planned | Phase 6: FastAPI + React |