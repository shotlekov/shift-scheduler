#!/usr/bin/env python3
"""
Shift Scheduler GUI Application
A desktop tool for managing team shift schedules with rotation schemes and constraints.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont
from datetime import date, datetime, timedelta
import json
import threading
import queue
from pathlib import Path
from typing import Optional, Dict, List, Callable, Any
from collections import defaultdict

# Import our modules
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))  # project root for shiftcore
sys.path.insert(0, str(Path(__file__).parent))  # src directory for adapter

# Use shiftcore adapter instead of legacy db.py/scheduler.py
from shiftcore_adapter import *
from shiftcore_adapter import _to_dict
from shiftcore import SHIFT_MODELS


class ScheduleEventBus:
    """Simple pub/sub event bus for schedule changes."""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)

    def subscribe(self, event_type: str, callback: Callable):
        """Subscribe to an event type."""
        self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable):
        """Unsubscribe from an event type."""
        if callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)

    def publish(self, event_type: str, data: Any = None):
        """Publish an event to all subscribers."""
        for callback in self._subscribers[event_type]:
            try:
                callback(data)
            except Exception as e:
                print(f"Error in event handler for {event_type}: {e}")


# Global event bus instance
schedule_event_bus = ScheduleEventBus()


class ShiftSchedulerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Shift Scheduler - Team Rotation Manager")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 800)

        # Initialize database
        init_db()

        # Set up theme and fonts
        self._setup_fonts()
        self._setup_palettes()
        self.current_theme = tk.StringVar(value="light")

        # Background task queue
        self._task_queue = queue.Queue()
        self._bg_thread = None
        self._start_background_polling()

        # App state
        self.selected_date = date.today()
        self.cycle_start_date = date.today()  # Will be configurable
        self.selected_team_id = None
        self.selected_person_id = None
        self.schedule_data = []
        self.shift_model = tk.StringVar(value="2-shift")  # "2-shift" or "3-shift"

        # Manual first 2 days configuration: {(team_id, date): shift_type}
        self.manual_first_days = {}

        # Build UI
        self._build_ui()
        self._apply_theme()

        # Default to admin role (no role selection dialog)
        self.user_role = tk.StringVar(value="admin")
        self._apply_role_permissions()

        # Load initial data
        self._on_load_notification_settings()
        self._refresh_all()

        # Subscribe to schedule events for dynamic updates
        schedule_event_bus.subscribe(
            "schedule.overlay_added", self._on_schedule_overlay_changed
        )
        schedule_event_bus.subscribe(
            "schedule.overlay_removed", self._on_schedule_overlay_changed
        )
        schedule_event_bus.subscribe(
            "schedule.base_reinitialized", self._on_schedule_base_reinitialized
        )

    def _on_schedule_overlay_changed(self, data):
        """Handle schedule overlay changes (substitutions, swaps, exceptions)."""
        # Refresh the schedule grid on main thread
        self.root.after(0, self._on_load_schedule)

    def _on_schedule_base_reinitialized(self, data):
        """Handle base schedule reinitialization."""
        # Full refresh needed
        self.root.after(0, self._refresh_all)

    def _setup_fonts(self):
        """Detect and set up proper fonts according to specification."""
        available_families = set(tkfont.families())
        preferred_sans = ["Inter", "Ubuntu", "Segoe UI", "DejaVu Sans"]
        preferred_mono = ["JetBrains Mono", "DejaVu Sans Mono"]

        # Find first available sans font
        sans_font = None
        for font in preferred_sans:
            if font in available_families:
                sans_font = font
                break
        if not sans_font:
            sans_font = "sans-serif"

        # Find first available mono font
        mono_font = None
        for font in preferred_mono:
            if font in available_families:
                mono_font = font
                break
        if not mono_font:
            mono_font = "monospace"

        self.sans_font = sans_font
        self.mono_font = mono_font

        # Named fonts for consistent usage (defined here so available during UI build)
        self.fUI = (self.sans_font, 10)  # Base UI font
        self.fUIBold = (self.sans_font, 10, "bold")  # Bold UI font
        self.fSmall = (self.sans_font, 9)  # Small headers (Use, Action, Weight, etc.)
        self.fMono = (self.mono_font, 10)  # Monospace for code/markdown

        # Configure default fonts
        default_font = tkfont.nametofont("TkDefaultFont")
        default_font.configure(family=sans_font, size=10)
        text_font = tkfont.nametofont("TkTextFont")
        text_font.configure(family=sans_font, size=10)
        heading_font = tkfont.nametofont("TkHeadingFont")
        heading_font.configure(family=sans_font, size=10, weight="bold")

    def _setup_palettes(self):
        """Define color palettes for both themes."""
        self.PALETTES = {
            "dark": {
                "app": "#0f172a",  # Slate-950
                "card": "#1e293b",  # Slate-800
                "input": "#0f172a",  # Slate-950
                "border": "#334155",  # Slate-700
                "text": "#f1f5f9",  # Slate-50
                "text2": "#94a3b8",  # Slate-400
                "accent": "#22d3ee",  # Cyan-400
                "accent_text": "#0f172a",  # Slate-950
                "accent_hover": "#67e8f9",  # Cyan-300
                "select": "#164e63",  # Slate-900/800 mix
                "zebra": "#172033",  # Darker card
            },
            "light": {
                "app": "#f1f5f9",  # Slate-50
                "card": "#ffffff",  # White
                "input": "#ffffff",  # White
                "border": "#cbd5e1",  # Slate-200
                "text": "#0f172a",  # Slate-950
                "text2": "#475569",  # Slate-600
                "accent": "#2563eb",  # Blue-600
                "accent_text": "#ffffff",  # White
                "accent_hover": "#1d4ed8",  # Blue-700
                "select": "#dbeafe",  # Blue-100
                "zebra": "#f8fafc",  # Slate-50
            },
        }

    def _get_palette(self):
        """Get current theme palette."""
        theme = self.current_theme.get()
        return self.PALETTES.get(theme, self.PALETTES["light"])

    def _apply_theme(self):
        """Apply theme to all widgets - called on init and theme change."""
        palette = self._get_palette()
        style = ttk.Style(self.root)

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # Configure root
        self.root.configure(background=palette["app"])

        # Base styles
        style.configure(
            ".", background=palette["app"], foreground=palette["text"], font=self.fUI
        )

        # Frames
        style.configure("TFrame", background=palette["app"])
        style.configure(
            "Card.TFrame",
            background=palette["card"],
            borderwidth=1,
            relief="solid",
            bordercolor=palette["border"],
        )
        style.configure(
            "Plain.TFrame", background=palette["card"], borderwidth=0, relief="flat"
        )
        style.configure(
            "Surface.TFrame", background=palette["card"], borderwidth=0, relief="flat"
        )

        # Labels
        style.configure(
            "TLabel",
            background=palette["app"],
            foreground=palette["text"],
            font=self.fUI,
            padding=(0, 4),
        )
        style.configure(
            "Secondary.TLabel",
            background=palette["app"],
            foreground=palette["text2"],
            font=self.fUI,
            padding=(0, 4),
        )
        style.configure(
            "Muted.TLabel",
            background=palette["app"],
            foreground=palette["text2"],
            font=self.fUI,
            padding=(0, 4),
        )
        style.configure(
            "Card.TLabel",
            background=palette["card"],
            foreground=palette["text"],
            font=self.fSmall,
            padding=(0, 4),
        )
        style.configure(
            "Card.Muted.TLabel",
            background=palette["card"],
            foreground=palette["text2"],
            font=self.fSmall,
            padding=(0, 4),
        )

        # Buttons - padding (16,6) for consistent height
        style.configure(
            "TButton",
            background=palette["input"],
            foreground=palette["text"],
            borderwidth=1,
            relief="solid",
            bordercolor=palette["border"],
            focuscolor=palette["accent"],
            padding=(16, 6),
            font=self.fUI,
        )
        style.map(
            "TButton",
            background=[
                ("active", palette["accent_hover"]),
                ("pressed", palette["accent"]),
                ("disabled", palette["input"]),
            ],
            foreground=[("disabled", palette["text2"])],
        )

        style.configure(
            "Accent.TButton",
            background=palette["accent"],
            foreground=palette["accent_text"],
            borderwidth=1,
            relief="solid",
            focuscolor=palette["accent"],
            padding=(16, 6),
            font=self.fUIBold,
        )
        style.map(
            "Accent.TButton",
            background=[
                ("active", palette["accent_hover"]),
                ("pressed", palette["accent"]),
            ],
            foreground=[("pressed", palette["accent_text"])],
        )

        style.configure(
            "Ghost.TButton",
            background=palette["card"],
            foreground=palette["text"],
            borderwidth=1,
            relief="solid",
            bordercolor=palette["border"],
            padding=(16, 6),
            font=self.fUI,
        )
        style.map(
            "Ghost.TButton",
            background=[
                ("active", palette["input"]),
                ("pressed", palette["accent_hover"]),
            ],
            foreground=[
                ("active", palette["text"]),
                ("pressed", palette["accent_text"]),
            ],
        )

        # Entries - padding (8,6)
        style.configure(
            "TEntry",
            fieldbackground=palette["input"],
            foreground=palette["text"],
            borderwidth=1,
            relief="solid",
            bordercolor=palette["border"],
            insertcolor=palette["text"],
            padding=(8, 6),
            font=self.fUI,
        )
        style.map(
            "TEntry",
            bordercolor=[("focus", palette["accent"])],
            fieldbackground=[("focus", palette["input"])],
        )

        # Combobox - padding (8,6), dropdown font set via root.option_add
        style.configure(
            "TCombobox",
            fieldbackground=palette["input"],
            foreground=palette["text"],
            borderwidth=1,
            relief="solid",
            bordercolor=palette["border"],
            arrowcolor=palette["text2"],
            padding=(8, 6),
            font=self.fUI,
        )
        style.map("TCombobox", bordercolor=[("focus", palette["accent"])])

        # Checkbuttons
        style.configure(
            "TCheckbutton",
            background=palette["app"],
            foreground=palette["text"],
            indicatorcolor=palette["input"],
            indicatorbordercolor=palette["border"],
        )
        style.map(
            "TCheckbutton",
            background=[("active", palette["app"])],
            foreground=[("active", palette["text"])],
            indicatorcolor=[
                ("selected", palette["accent"]),
                ("!selected", palette["input"]),
            ],
            indicatorbordercolor=[
                ("selected", palette["accent"]),
                ("focus", palette["accent"]),
            ],
        )

        style.configure(
            "Card.TCheckbutton",
            background=palette["card"],
            foreground=palette["text"],
            indicatorcolor=palette["input"],
            indicatorbordercolor=palette["border"],
        )
        style.map(
            "Card.TCheckbutton",
            background=[("active", palette["card"])],
            foreground=[("active", palette["text"])],
            indicatorcolor=[
                ("selected", palette["accent"]),
                ("!selected", palette["input"]),
            ],
            indicatorbordercolor=[
                ("selected", palette["accent"]),
                ("focus", palette["accent"]),
            ],
        )

        # Action checkboxes - centered in column
        style.configure(
            "Action.TCheckbutton",
            background=palette["card"],
            foreground=palette["text"],
            indicatorcolor=palette["input"],
            indicatorbordercolor=palette["border"],
            padding=[12, 4],
        )
        style.map(
            "Action.TCheckbutton",
            background=[("active", palette["card"])],
            foreground=[("active", palette["text"])],
            indicatorcolor=[
                ("selected", palette["accent"]),
                ("!selected", palette["input"]),
            ],
            indicatorbordercolor=[
                ("selected", palette["accent"]),
                ("focus", palette["accent"]),
            ],
        )

        # Notebook (tabs)
        style.configure("TNotebook", background=palette["app"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=palette["card"],
            foreground=palette["text2"],
            borderwidth=1,
            relief="solid",
            bordercolor=palette["border"],
            padding=[20, 10],
        )
        style.map(
            "TNotebook.Tab",
            background=[
                (
                    "selected",
                    palette["card"]
                    if self.current_theme.get() == "dark"
                    else palette["card"],
                ),
                ("active", palette["input"]),
            ],
            foreground=[("selected", palette["accent"]), ("active", palette["text"])],
            bordercolor=[("selected", palette["accent"])],
            padding=[("selected", [25, 12])],
        )

        # Treeview
        style.configure(
            "Treeview",
            background=palette["card"],
            fieldbackground=palette["card"],
            foreground=palette["text"],
            borderwidth=0,
            rowheight=28,
        )
        style.configure(
            "Treeview.Heading",
            background=palette["input"],
            foreground=palette["accent"],
            font=self.fUIBold,
            borderwidth=1,
            relief="solid",
            bordercolor=palette["border"],
        )
        style.map("Treeview.Heading", background=[("active", palette["accent_hover"])])
        style.map(
            "Treeview",
            background=[("selected", palette["select"]), ("focus", palette["select"])],
            foreground=[
                ("selected", palette["accent_text"]),
                ("focus", palette["accent_text"]),
            ],
        )

        # Scrollbars
        style.configure(
            "Vertical.TScrollbar",
            background=palette["input"],
            troughcolor=palette["app"],
            bordercolor=palette["border"],
            arrowcolor=palette["text2"],
            width=8,
        )
        style.map(
            "Vertical.TScrollbar",
            background=[
                ("active", palette["accent_hover"]),
                ("pressed", palette["accent"]),
            ],
        )

        style.configure(
            "Horizontal.TScrollbar",
            background=palette["input"],
            troughcolor=palette["app"],
            bordercolor=palette["border"],
            arrowcolor=palette["text2"],
            height=8,
        )
        style.map(
            "Horizontal.TScrollbar",
            background=[
                ("active", palette["accent_hover"]),
                ("pressed", palette["accent"]),
            ],
        )

        # Progressbar
        style.configure(
            "TProgressbar",
            background=palette["accent"],
            troughcolor=palette["input"],
            borderwidth=0,
            thickness=4,
        )

        # Separator
        style.configure("TSeparator", background=palette["border"])

        # Configure tk widgets
        self._configure_tk_widgets(palette)

    def _apply_role_permissions(self):
        """Apply UI permissions based on user role."""
        is_admin = self.user_role.get() == "admin"

        # Hide/show tabs based on role
        # For users, hide admin-only tabs: Teams & People, Availability, Shift Swaps, Notifications
        if not is_admin:
            # Get tab indices to hide
            tabs_to_hide = [
                "Teams & People",
                "Availability",
                "Shift Swaps",
                "Notifications",
            ]
            for tab_name in tabs_to_hide:
                for i in range(self.notebook.index("end")):
                    if self.notebook.tab(i, "text") == tab_name:
                        self.notebook.hide(i)
                        break

            # Disable schedule generation for users
            if hasattr(self, "generate_btn"):
                self.generate_btn.configure(state="disabled")

            # Disable manual config for users
            if hasattr(self, "apply_manual_btn"):
                self.apply_manual_btn.configure(state="disabled")

            # Add "My Requests" tab for users (placeholder for future)
            self._add_user_requests_tab()

    def _add_user_requests_tab(self):
        """Add a tab for users to request time off/sick leave."""
        # Create the tab if it doesn't exist
        if hasattr(self, "requests_tab"):
            return

        self.requests_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.requests_tab, text="My Requests")

        # Main paned window
        paned = ttk.PanedWindow(self.requests_tab, orient="vertical")
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        # Top panel - Submit new request
        top_frame = ttk.LabelFrame(paned, text="Submit New Request")
        paned.add(top_frame, weight=1)

        # Request form
        form_frame = ttk.Frame(top_frame)
        form_frame.pack(fill="both", expand=True, padx=8, pady=8)

        # Request type
        ttk.Label(form_frame, text="Request Type:").grid(
            row=0, column=0, sticky="w", pady=4
        )
        self.request_type_var = tk.StringVar(value="vacation")
        ttk.Radiobutton(
            form_frame,
            text="Vacation (Planned)",
            variable=self.request_type_var,
            value="vacation",
        ).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Radiobutton(
            form_frame,
            text="Sick Leave (Medical)",
            variable=self.request_type_var,
            value="sick",
        ).grid(row=0, column=2, sticky="w", padx=8)

        # Date range
        ttk.Label(form_frame, text="Start Date:").grid(
            row=1, column=0, sticky="w", pady=4
        )
        self.request_start_var = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(form_frame, textvariable=self.request_start_var, width=15).grid(
            row=1, column=1, sticky="w", padx=8
        )

        ttk.Label(form_frame, text="End Date:").grid(
            row=1, column=2, sticky="w", pady=4, padx=(16, 0)
        )
        self.request_end_var = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(form_frame, textvariable=self.request_end_var, width=15).grid(
            row=1, column=3, sticky="w", padx=8
        )

        # Reason/Notes
        ttk.Label(form_frame, text="Reason / Notes:").grid(
            row=2, column=0, sticky="nw", pady=4
        )
        self.request_notes_text = tk.Text(form_frame, height=4, width=50, font=self.fUI)
        self.request_notes_text.grid(
            row=2, column=1, columnspan=3, sticky="ew", padx=8, pady=4
        )

        # Submit button
        btn_frame = ttk.Frame(form_frame)
        btn_frame.grid(row=3, column=0, columnspan=4, pady=12)
        ttk.Button(
            btn_frame,
            text="Submit Request",
            command=self._submit_request,
            style="Accent.TButton",
        ).pack(side="left", padx=4)

        ttk.Button(
            btn_frame,
            text="Clear Form",
            command=self._clear_request_form,
        ).pack(side="left", padx=4)

        form_frame.columnconfigure(1, weight=1)
        form_frame.columnconfigure(3, weight=1)

        # Bottom panel - My requests list
        bottom_frame = ttk.LabelFrame(paned, text="My Requests")
        paned.add(bottom_frame, weight=2)

        # Requests treeview
        req_columns = (
            "id",
            "type",
            "start_date",
            "end_date",
            "status",
            "reason",
            "admin_notes",
        )
        self.requests_tree = ttk.Treeview(
            bottom_frame, columns=req_columns, show="headings", height=10
        )
        self.requests_tree.heading("id", text="ID")
        self.requests_tree.heading("type", text="Type")
        self.requests_tree.heading("start_date", text="Start Date")
        self.requests_tree.heading("end_date", text="End Date")
        self.requests_tree.heading("status", text="Status")
        self.requests_tree.heading("reason", text="Reason")
        self.requests_tree.heading("admin_notes", text="Admin Notes")

        self.requests_tree.column("id", width=50)
        self.requests_tree.column("type", width=100)
        self.requests_tree.column("start_date", width=100)
        self.requests_tree.column("end_date", width=100)
        self.requests_tree.column("status", width=100)
        self.requests_tree.column("reason", width=200)
        self.requests_tree.column("admin_notes", width=200)

        req_v_scroll = ttk.Scrollbar(
            bottom_frame, orient="vertical", command=self.requests_tree.yview
        )
        self.requests_tree.configure(yscrollcommand=req_v_scroll.set)
        self.requests_tree.pack(side="left", fill="both", expand=True)
        req_v_scroll.pack(side="right", fill="y")

        # Configure tags
        self.requests_tree.tag_configure(
            "pending", background="#fff3e0", foreground="#e65100"
        )
        self.requests_tree.tag_configure(
            "approved", background="#e8f5e9", foreground="#2e7d32"
        )
        self.requests_tree.tag_configure(
            "rejected", background="#ffebee", foreground="#c62828"
        )

        # Load requests
        self._load_user_requests()

    def _submit_request(self):
        """Submit a new time off/sick leave request."""
        try:
            start_date = date.fromisoformat(self.request_start_var.get())
            end_date = date.fromisoformat(self.request_end_var.get())

            if start_date > end_date:
                messagebox.showerror(
                    "Invalid Dates", "Start date must be before or equal to end date."
                )
                return

            request_type = self.request_type_var.get()
            notes = self.request_notes_text.get("1.0", "end-1c").strip()

            if not notes:
                messagebox.showerror(
                    "Missing Reason", "Please provide a reason for your request."
                )
                return

            # Save to database as availability exception with pending status
            # We'll use the exceptions table with a special reason prefix
            reason_prefix = f"[{request_type.upper()} REQUEST] "
            full_reason = reason_prefix + notes

            # For now, create as exception but with pending status
            # In a full implementation, we'd have a separate requests table
            from shiftcore.storage import get_repo

            repo = get_repo()

            # Get current user's person_id (for demo, use first active person)
            persons = repo.get_persons(active_only=True)
            if not persons:
                messagebox.showerror("Error", "No active persons found.")
                return

            # For demo, use first person - in real app, this would be the logged-in user
            person_id = persons[0].id

            repo.create_exception(
                person_id=person_id,
                start_date=start_date,
                end_date=end_date,
                reason=full_reason,
            )

            messagebox.showinfo(
                "Request Submitted",
                f"Your {request_type} request from {start_date} to {end_date} has been submitted.\n"
                f"An administrator will review and approve/reject it.",
            )

            self._clear_request_form()
            self._load_user_requests()

        except ValueError:
            messagebox.showerror(
                "Invalid Date", "Please enter valid dates in YYYY-MM-DD format."
            )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to submit request: {str(e)}")

    def _clear_request_form(self):
        """Clear the request form."""
        self.request_start_var.set(date.today().isoformat())
        self.request_end_var.set(date.today().isoformat())
        self.request_notes_text.delete("1.0", "end")
        self.request_type_var.set("vacation")

    def _load_user_requests(self):
        """Load and display user's requests."""
        # Clear existing
        for item in self.requests_tree.get_children():
            self.requests_tree.delete(item)

        try:
            from shiftcore.storage import get_repo

            repo = get_repo()

            # Get all exceptions for the current user (demo: first person)
            persons = repo.get_persons(active_only=True)
            if not persons:
                return
            person_id = persons[0].id

            # Get exceptions for a wide date range
            start_date = date.today() - timedelta(days=365)
            end_date = date.today() + timedelta(days=365)
            exceptions = repo.get_exceptions(person_id, start_date, end_date)

            for exc in exceptions:
                # Parse request type from reason
                reason = exc.reason
                req_type = "Unknown"
                clean_reason = reason
                if reason.startswith("[VACATION REQUEST] "):
                    req_type = "Vacation"
                    clean_reason = reason[len("[VACATION REQUEST] ") :]
                elif reason.startswith("[SICK REQUEST] "):
                    req_type = "Sick Leave"
                    clean_reason = reason[len("[SICK REQUEST] ") :]

                # Determine status (for demo, all pending)
                status = "Pending"
                tag = "pending"

                self.requests_tree.insert(
                    "",
                    "end",
                    values=(
                        exc.id,
                        req_type,
                        exc.start_date.isoformat(),
                        exc.end_date.isoformat(),
                        status,
                        clean_reason,
                        "",
                    ),
                    tags=(tag,),
                )
        except Exception as e:
            print(f"Error loading requests: {e}")

    def _configure_tk_widgets(self, palette):
        """Configure tk widgets (Canvas, ScrolledText) that need manual updates."""
        # Update canvas backgrounds
        if hasattr(self, "weights_canvas") and self.weights_canvas:
            self.weights_canvas.configure(
                background=palette["card"], highlightthickness=0
            )
        if hasattr(self, "users_canvas") and self.users_canvas:
            self.users_canvas.configure(
                background=palette["card"], highlightthickness=0
            )

        # Update ScrolledText widgets
        if hasattr(self, "result_text") and self.result_text:
            self.result_text.configure(
                background=palette["card"],
                foreground=palette["text"],
                insertbackground=palette["accent"],
                selectbackground=palette["select"],
                selectforeground=palette["accent_text"],
                borderwidth=0,
                highlightthickness=0,
                font=(self.mono_font, 10),
            )

        # Update info tab text widgets
        for text_widget in getattr(self, "info_text_widgets", []):
            text_widget.configure(
                background=palette["card"],
                foreground=palette["text"],
                insertbackground=palette["accent"],
                selectbackground=palette["select"],
                selectforeground=palette["accent_text"],
                borderwidth=0,
                highlightthickness=0,
                font=(self.mono_font, 10),
            )

        # Update treeview tags for existing trees
        for tree in [
            getattr(self, "ranking_tree", None),
            getattr(self, "details_tree", None),
        ]:
            if tree:
                tree.tag_configure("oddrow", background=palette["card"])
                tree.tag_configure("evenrow", background=palette["zebra"])

    def _start_background_polling(self):
        """Start polling loop for background task queue."""
        self._poll_task_queue()

    def _poll_task_queue(self):
        """Poll background task queue and execute callbacks on main thread."""
        try:
            while True:
                callback = self._task_queue.get_nowait()
                callback()
        except queue.Empty:
            pass
        self.root.after(50, self._poll_task_queue)

    def _run_in_background(self, task_func, on_done, on_error=None):
        """Run task_func in daemon thread; call on_done(result) or on_error(exc) on main thread."""

        def worker():
            try:
                result = task_func()
                self._task_queue.put(lambda r=result: on_done(r))
            except Exception as exc:
                if on_error:
                    self._task_queue.put(lambda e=exc: on_error(e))
                else:
                    self._task_queue.put(
                        lambda e=exc: self._show_error("Background task failed", str(e))
                    )

        threading.Thread(target=worker, daemon=True).start()

    def _show_error(self, title, message):
        """Show error message dialog."""
        messagebox.showerror(title, message)
        self.status_var.set(f"Error: {message}")

    def _set_busy(self, busy):
        """Show/hide busy state (cursor, button states)."""
        if busy:
            self.root.config(cursor="watch")
            for widget in [
                getattr(self, "generate_btn", None),
                getattr(self, "export_btn", None),
            ]:
                if widget:
                    widget.config(state="disabled")
        else:
            self.root.config(cursor="")
            for widget in [
                getattr(self, "generate_btn", None),
                getattr(self, "export_btn", None),
            ]:
                if widget:
                    widget.config(state="normal")

    def _build_ui(self):
        """Build the main user interface."""
        # Main container
        main_container = ttk.Frame(self.root)
        main_container.pack(fill="both", expand=True, padx=16, pady=16)

        # Header
        header_frame = ttk.Frame(main_container)
        header_frame.pack(fill="x", pady=(0, 16))

        ttk.Label(
            header_frame, text="Shift Scheduler", font=(self.sans_font, 18, "bold")
        ).pack(side="left")

        # Theme switcher
        theme_frame = ttk.Frame(header_frame)
        theme_frame.pack(side="right")
        ttk.Label(theme_frame, text="Theme:").pack(side="left", padx=(0, 8))
        theme_combo = ttk.Combobox(
            theme_frame,
            textvariable=self.current_theme,
            values=["light", "dark"],
            state="readonly",
            width=8,
        )
        theme_combo.pack(side="left")
        theme_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_theme())

        # Notebook for tabs
        self.notebook = ttk.Notebook(main_container)
        self.notebook.pack(fill="both", expand=True)

        # 1. Schedule Grid tab (main view) - FIRST TAB
        self.schedule_grid_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.schedule_grid_tab, text="Schedule Grid")
        self._build_schedule_grid_tab()

        # 2. Shift Swaps tab
        self.swaps_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.swaps_tab, text="Shift Swaps")
        self._build_swaps_tab()

        # 3. Availability tab (with sub-tabs)
        self.exceptions_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.exceptions_tab, text="Availability")
        self._build_exceptions_tab()

        # 4. Notifications tab
        self.notifications_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.notifications_tab, text="Notifications")
        self._build_notifications_tab()

        # 5. Teams & People tab
        self.teams_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.teams_tab, text="Teams & People")
        self._build_teams_tab()

        # 6. Schedule Initialization tab (formerly Schedule View)
        self.schedule_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.schedule_tab, text="Schedule Initialization")
        self._build_schedule_tab()

        # Bottom bar
        bottom_frame = ttk.Frame(main_container)
        bottom_frame.pack(fill="x", pady=(16, 0))

        self.generate_btn = ttk.Button(
            bottom_frame,
            text="Generate Schedule",
            command=self._on_generate_schedule,
            style="Accent.TButton",
        )
        self.generate_btn.pack(side="left", padx=(0, 8))

        self.export_btn = ttk.Button(
            bottom_frame,
            text="Export CSV",
            command=self._on_export_csv,
            style="Ghost.TButton",
        )
        self.export_btn.pack(side="left", padx=(0, 8))

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(
            bottom_frame, textvariable=self.status_var, style="Muted.TLabel"
        ).pack(side="right")

    def _build_schedule_tab(self):
        """Build the schedule controls tab."""
        # Main frame
        main_frame = ttk.Frame(self.schedule_tab)
        main_frame.pack(fill="both", expand=True, padx=8, pady=8)

        # Schedule controls
        controls_frame = ttk.LabelFrame(main_frame, text="Schedule Controls")
        controls_frame.pack(fill="x", pady=(0, 8))

        # Initial date and model selection
        date_frame = ttk.Frame(controls_frame)
        date_frame.pack(fill="x", padx=8, pady=8)

        ttk.Label(date_frame, text="Initial Date (Cycle Start):").grid(
            row=0, column=0, sticky="w", padx=(0, 4)
        )
        self.initial_date_var = tk.StringVar(value=date.today().isoformat())
        self.initial_date_var.trace_add(
            "write", lambda *args: self._refresh_manual_config()
        )
        ttk.Entry(date_frame, textvariable=self.initial_date_var, width=12).grid(
            row=0, column=1, padx=(0, 16)
        )

        ttk.Label(date_frame, text="Shift Model:").grid(
            row=0, column=2, sticky="w", padx=(0, 4)
        )
        self.shift_model_combo = ttk.Combobox(
            date_frame,
            textvariable=self.shift_model,
            values=["2-shift", "3-shift"],
            state="readonly",
            width=10,
        )
        self.shift_model_combo.grid(row=0, column=3, padx=(0, 16))
        self.shift_model_combo.bind("<<ComboboxSelected>>", self._on_shift_model_change)

        ttk.Button(
            date_frame, text="Load Schedule", command=self._on_load_schedule
        ).grid(row=0, column=4, padx=(16, 0))

        # Manual first 2 days configuration
        manual_frame = ttk.LabelFrame(
            controls_frame, text="Manual First 2 Days Configuration"
        )
        manual_frame.pack(fill="x", padx=8, pady=(0, 8))

        # Create a grid for manual configuration: 2 dates x teams
        self.manual_config_frame = ttk.Frame(manual_frame)
        self.manual_config_frame.pack(fill="x", padx=8, pady=8)

        # Will be populated in _refresh_manual_config()
        self.manual_config_vars = {}  # {(team_id, day_offset): StringVar}

        # Action buttons
        action_frame = ttk.LabelFrame(main_frame, text="Actions")
        action_frame.pack(fill="x", pady=(0, 8))

        btn_frame = ttk.Frame(action_frame)
        btn_frame.pack(fill="x", padx=8, pady=8)

        ttk.Button(
            btn_frame,
            text="Generate Schedule",
            command=self._on_generate_schedule,
            style="Accent.TButton",
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            btn_frame,
            text="Export CSV",
            command=self._on_export_csv,
            style="Ghost.TButton",
        ).pack(side="left", padx=(0, 8))

        ttk.Button(btn_frame, text="Refresh Grid", command=self._on_load_schedule).pack(
            side="left"
        )

        # Status
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(main_frame, textvariable=self.status_var, style="Muted.TLabel").pack(
            anchor="w", padx=8, pady=(8, 0)
        )

    def _build_schedule_grid_tab(self):
        """Build the schedule grid tab with split view: grid on left, squad details on right."""
        # Main paned window - horizontal split
        paned = ttk.PanedWindow(self.schedule_grid_tab, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        # LEFT PANE - Schedule Grid
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=3)  # 3/4 of width

        # Search bar
        search_frame = ttk.Frame(left_frame)
        search_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(search_frame, text="Search Person:").pack(side="left", padx=(0, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._on_search_changed())
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
        search_entry.pack(side="left", padx=(0, 8))

        ttk.Button(search_frame, text="Clear", command=self._on_clear_search).pack(
            side="left", padx=(0, 8)
        )

        ttk.Label(search_frame, text="(Type name to filter schedule)").pack(
            side="left", padx=(8, 0)
        )

        # Schedule grid
        grid_frame = ttk.LabelFrame(left_frame, text="Schedule Grid (18 months)")
        grid_frame.pack(fill="both", expand=True)

        # Create treeview for schedule - simplified columns
        self.schedule_tree = ttk.Treeview(
            grid_frame, columns=("date", "day"), show="headings", height=30
        )

        # Define base headings (will add team columns dynamically)
        self.schedule_tree.heading("date", text="Date")
        self.schedule_tree.heading("day", text="Day")

        # Define base column widths
        self.schedule_tree.column("date", width=100, anchor="center")
        self.schedule_tree.column("day", width=100, anchor="center")

        # Add scrollbars
        v_scrollbar = ttk.Scrollbar(
            grid_frame, orient="vertical", command=self.schedule_tree.yview
        )
        h_scrollbar = ttk.Scrollbar(
            grid_frame, orient="horizontal", command=self.schedule_tree.xview
        )
        self.schedule_tree.configure(
            yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set
        )

        # Pack treeview and scrollbars
        self.schedule_tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")

        grid_frame.grid_rowconfigure(0, weight=1)
        grid_frame.grid_columnconfigure(0, weight=1)

        # Configure zebra striping tags
        palette = self._get_palette()
        self.schedule_tree.tag_configure("oddrow", background=palette["card"])
        self.schedule_tree.tag_configure("evenrow", background=palette["zebra"])
        # Tag for unfilled shifts (needs coverage)
        self.schedule_tree.tag_configure(
            "unfilled", background="#ffebee", foreground="#c62828"
        )
        # Color coding tags for dynamic updates
        self.schedule_tree.tag_configure(
            "unavailable", background="#ffebee", foreground="#c62828"
        )  # Red for unavailable
        self.schedule_tree.tag_configure(
            "swapped", background="#e8f5e9", foreground="#2e7d32"
        )  # Green for swapped
        self.schedule_tree.tag_configure(
            "substituted", background="#fff3e0", foreground="#e65100"
        )  # Yellow/Amber for substituted

        # Bind events for tooltips and click selection
        self.schedule_tree.bind("<Motion>", self._on_tree_motion)
        self.schedule_tree.bind("<Leave>", self._on_tree_leave)
        self.schedule_tree.bind("<Button-1>", self._on_tree_click)
        self.schedule_tree.bind("<Double-1>", self._on_tree_double_click)

        # Tooltip window
        self.tooltip_window = None
        self.tooltip_item = None
        self.tooltip_col = None

        # RIGHT PANE - Squad Details
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)  # 1/4 of width

        # Squad details frame
        squad_frame = ttk.LabelFrame(right_frame, text="Squad Details")
        squad_frame.pack(fill="both", expand=True, padx=(8, 0))

        # Header showing selected cell info
        self.squad_header_var = tk.StringVar(value="Click a shift cell to view squad")
        ttk.Label(
            squad_frame,
            textvariable=self.squad_header_var,
            font=self.fUIBold,
            wraplength=300,
        ).pack(fill="x", padx=8, pady=8)

        # Squad list treeview
        squad_columns = ("name", "role", "status")
        self.squad_tree = ttk.Treeview(
            squad_frame, columns=squad_columns, show="headings", height=20
        )
        self.squad_tree.heading("name", text="Name")
        self.squad_tree.heading("role", text="Role")
        self.squad_tree.heading("status", text="Status")
        self.squad_tree.column("name", width=180)
        self.squad_tree.column("role", width=80)
        self.squad_tree.column("status", width=120)

        squad_v_scroll = ttk.Scrollbar(
            squad_frame, orient="vertical", command=self.squad_tree.yview
        )
        self.squad_tree.configure(yscrollcommand=squad_v_scroll.set)
        self.squad_tree.pack(side="left", fill="both", expand=True)
        squad_v_scroll.pack(side="right", fill="y")

        # Configure zebra striping for squad tree
        self.squad_tree.tag_configure("oddrow", background="#f5f5f5")
        self.squad_tree.tag_configure("evenrow", background="#ffffff")
        # Highlight assigned person
        palette = self._get_palette()
        self.squad_tree.tag_configure(
            "assigned", background=palette["select"], foreground=palette["accent_text"]
        )

    def _build_teams_tab(self):
        """Build the teams and people management tab."""
        # Main paned window
        paned = ttk.PanedWindow(self.teams_tab, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        # Left panel - Teams
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)

        # Teams list
        teams_frame = ttk.LabelFrame(left_frame, text="Teams (Auto-generated)")
        teams_frame.pack(fill="both", expand=True, pady=(0, 8))

        columns = ("id", "name", "color", "offset", "members")
        self.teams_tree = ttk.Treeview(
            teams_frame, columns=columns, show="headings", height=10
        )
        self.teams_tree.heading("id", text="ID")
        self.teams_tree.heading("name", text="Name")
        self.teams_tree.heading("color", text="Color")
        self.teams_tree.heading("offset", text="Offset")
        self.teams_tree.heading("members", text="Members")
        self.teams_tree.column("id", width=50)
        self.teams_tree.column("name", width=120)
        self.teams_tree.column("color", width=80)
        self.teams_tree.column("offset", width=60)
        self.teams_tree.column("members", width=70)

        teams_v_scroll = ttk.Scrollbar(
            teams_frame, orient="vertical", command=self.teams_tree.yview
        )
        self.teams_tree.configure(yscrollcommand=teams_v_scroll.set)
        self.teams_tree.grid(row=0, column=0, sticky="nsew")
        teams_v_scroll.grid(row=0, column=1, sticky="ns")

        # Team buttons - only Regenerate Teams
        team_btn_frame = ttk.Frame(teams_frame)
        team_btn_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)

        ttk.Button(
            team_btn_frame, text="Regenerate Teams", command=self._on_regenerate_teams
        ).pack(side="left")

        teams_frame.grid_rowconfigure(0, weight=1)
        teams_frame.grid_rowconfigure(1, weight=0)
        teams_frame.grid_columnconfigure(0, weight=1)

        # Right panel - People
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)

        # People list
        people_frame = ttk.LabelFrame(right_frame, text="People (Assign to Teams)")
        people_frame.pack(fill="both", expand=True, pady=(0, 8))

        columns = ("id", "name", "telegram", "email", "team", "role", "active")
        self.people_tree = ttk.Treeview(
            people_frame, columns=columns, show="headings", height=15
        )
        self.people_tree.heading("id", text="ID")
        self.people_tree.heading("name", text="Name")
        self.people_tree.heading("telegram", text="Telegram")
        self.people_tree.heading("email", text="Email")
        self.people_tree.heading("team", text="Team")
        self.people_tree.heading("role", text="Role")
        self.people_tree.heading("active", text="Active")
        self.people_tree.column("id", width=50)
        self.people_tree.column("name", width=150)
        self.people_tree.column("telegram", width=100)
        self.people_tree.column("email", width=150)
        self.people_tree.column("team", width=100)
        self.people_tree.column("role", width=100)
        self.people_tree.column("active", width=60)

        people_v_scroll = ttk.Scrollbar(
            people_frame, orient="vertical", command=self.people_tree.yview
        )
        people_h_scroll = ttk.Scrollbar(
            people_frame, orient="horizontal", command=self.people_tree.xview
        )
        self.people_tree.configure(
            yscrollcommand=people_v_scroll.set, xscrollcommand=people_h_scroll.set
        )
        self.people_tree.grid(row=0, column=0, sticky="nsew")
        people_v_scroll.grid(row=0, column=1, sticky="ns")
        people_h_scroll.grid(row=1, column=0, sticky="ew")

        people_frame.grid_rowconfigure(0, weight=1)
        people_frame.grid_columnconfigure(0, weight=1)

        # People buttons
        people_btn_frame = ttk.Frame(people_frame)
        people_btn_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=4)

        ttk.Button(
            people_btn_frame, text="Add Person", command=self._on_add_person
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            people_btn_frame, text="Edit Person", command=self._on_edit_person
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            people_btn_frame, text="Delete Person", command=self._on_delete_person
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            people_btn_frame,
            text="Toggle Active",
            command=self._on_toggle_person_active,
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            people_btn_frame,
            text="Import CSV",
            command=self._on_import_csv,
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            people_btn_frame,
            text="Generate Demo People",
            command=self._on_generate_demo_people,
        ).pack(side="left")

        people_frame.grid_rowconfigure(2, weight=0)

    def _build_exceptions_tab(self):
        """Build the availability exceptions tab with sub-tabs: Current, History, Upcoming."""
        # Main frame
        main_frame = ttk.Frame(self.exceptions_tab)
        main_frame.pack(fill="both", expand=True, padx=8, pady=8)

        # Sub-notebook for Current/History/Upcoming
        self.exceptions_sub_notebook = ttk.Notebook(main_frame)
        self.exceptions_sub_notebook.pack(fill="both", expand=True)

        # --- Current Sub-tab (default) ---
        self.exceptions_current_tab = ttk.Frame(self.exceptions_sub_notebook)
        self.exceptions_sub_notebook.add(self.exceptions_current_tab, text="Current")
        self._build_exceptions_subtab(self.exceptions_current_tab, "current")

        # --- History Sub-tab ---
        self.exceptions_history_tab = ttk.Frame(self.exceptions_sub_notebook)
        self.exceptions_sub_notebook.add(self.exceptions_history_tab, text="History")
        self._build_exceptions_subtab(self.exceptions_history_tab, "history")

        # --- Upcoming Sub-tab ---
        self.exceptions_upcoming_tab = ttk.Frame(self.exceptions_sub_notebook)
        self.exceptions_sub_notebook.add(self.exceptions_upcoming_tab, text="Upcoming")
        self._build_exceptions_subtab(self.exceptions_upcoming_tab, "upcoming")

        # Bind tab change event
        self.exceptions_sub_notebook.bind(
            "<<NotebookTabChanged>>", self._on_exceptions_subtab_changed
        )

    def _build_exceptions_subtab(self, parent_frame, subtab_type: str):
        """Build a sub-tab for exceptions (Current/History/Upcoming)."""
        # Controls frame
        controls_frame = ttk.LabelFrame(parent_frame, text="Availability Exceptions")
        controls_frame.pack(fill="both", expand=True, pady=(0, 8), padx=8)

        # Person selection
        person_frame = ttk.Frame(controls_frame)
        person_frame.pack(fill="x", padx=8, pady=8)

        ttk.Label(person_frame, text="Person:").pack(side="left")
        exception_person_var = tk.StringVar()
        exception_person_combo = ttk.Combobox(
            person_frame,
            textvariable=exception_person_var,
            state="readonly",
            width=25,
        )
        exception_person_combo.pack(side="left", padx=(4, 0))
        exception_person_combo.bind(
            "<<ComboboxSelected>>", self._on_exception_person_selected
        )

        ttk.Button(
            person_frame,
            text="Refresh",
            command=lambda: self._refresh_exceptions_for_person(subtab_type),
        ).pack(side="left", padx=(4, 0))

        # Store references for each sub-tab
        setattr(self, f"exception_person_var_{subtab_type}", exception_person_var)
        setattr(self, f"exception_person_combo_{subtab_type}", exception_person_combo)

        # Date range for exception (only for Current and Upcoming tabs)
        if subtab_type in ("current", "upcoming"):
            date_frame = ttk.Frame(controls_frame)
            date_frame.pack(fill="x", padx=8, pady=4)

            ttk.Label(date_frame, text="Start Date:").grid(
                row=0, column=0, sticky="w", padx=(0, 4)
            )
            exception_start_var = tk.StringVar(value=date.today().isoformat())
            ttk.Entry(date_frame, textvariable=exception_start_var, width=12).grid(
                row=0, column=1, padx=(0, 16)
            )

            ttk.Label(date_frame, text="End Date:").grid(
                row=0, column=2, sticky="w", padx=(0, 4)
            )
            exception_end_var = tk.StringVar(
                value=(date.today() + timedelta(days=7)).isoformat()
            )
            ttk.Entry(date_frame, textvariable=exception_end_var, width=12).grid(
                row=0, column=3, padx=(0, 16)
            )

            ttk.Label(date_frame, text="Reason:").grid(
                row=0, column=4, sticky="w", padx=(0, 4)
            )
            exception_reason_var = tk.StringVar()
            ttk.Entry(date_frame, textvariable=exception_reason_var, width=20).grid(
                row=0, column=5
            )

            ttk.Button(
                date_frame, text="Add Exception", command=self._on_add_exception
            ).grid(row=0, column=6, padx=(16, 0))
            ttk.Button(
                date_frame, text="Delete Selected", command=self._on_delete_exception
            ).grid(row=0, column=7)

            # Store references
            setattr(self, f"exception_start_var_{subtab_type}", exception_start_var)
            setattr(self, f"exception_end_var_{subtab_type}", exception_end_var)
            setattr(self, f"exception_reason_var_{subtab_type}", exception_reason_var)

        # Exceptions list
        exceptions_frame = ttk.LabelFrame(controls_frame, text="Exceptions List")
        exceptions_frame.pack(fill="both", expand=True, pady=(8, 0))

        columns = ("id", "person", "start_date", "end_date", "reason")
        exceptions_tree = ttk.Treeview(
            exceptions_frame, columns=columns, show="headings", height=12
        )
        exceptions_tree.heading("id", text="ID")
        exceptions_tree.heading("person", text="Person")
        exceptions_tree.heading("start_date", text="Start Date")
        exceptions_tree.heading("end_date", text="End Date")
        exceptions_tree.heading("reason", text="Reason")
        exceptions_tree.column("id", width=50)
        exceptions_tree.column("person", width=150)
        exceptions_tree.column("start_date", width=100)
        exceptions_tree.column("end_date", width=100)
        exceptions_tree.column("reason", width=200)

        exc_v_scroll = ttk.Scrollbar(
            exceptions_frame, orient="vertical", command=exceptions_tree.yview
        )
        exc_h_scroll = ttk.Scrollbar(
            exceptions_frame, orient="horizontal", command=exceptions_tree.xview
        )
        exceptions_tree.configure(
            yscrollcommand=exc_v_scroll.set, xscrollcommand=exc_h_scroll.set
        )
        exceptions_tree.grid(row=0, column=0, sticky="nsew")
        exc_v_scroll.grid(row=0, column=1, sticky="ns")
        exc_h_scroll.grid(row=1, column=0, sticky="ew")

        exceptions_frame.grid_rowconfigure(0, weight=1)
        exceptions_frame.grid_columnconfigure(0, weight=1)

        # Store tree reference
        setattr(self, f"exceptions_tree_{subtab_type}", exceptions_tree)

    def _build_swaps_tab(self):
        """Build the shift swaps tab with sub-tabs: Current, History, Upcoming."""
        # Main frame
        main_frame = ttk.Frame(self.swaps_tab)
        main_frame.pack(fill="both", expand=True, padx=8, pady=8)

        # Sub-notebook for Current/History/Upcoming
        self.swaps_sub_notebook = ttk.Notebook(main_frame)
        self.swaps_sub_notebook.pack(fill="both", expand=True)

        # --- Current Sub-tab (default) ---
        self.swaps_current_tab = ttk.Frame(self.swaps_sub_notebook)
        self.swaps_sub_notebook.add(self.swaps_current_tab, text="Current")
        self._build_swaps_subtab(self.swaps_current_tab, "current")

        # --- History Sub-tab ---
        self.swaps_history_tab = ttk.Frame(self.swaps_sub_notebook)
        self.swaps_sub_notebook.add(self.swaps_history_tab, text="History")
        self._build_swaps_subtab(self.swaps_history_tab, "history")

        # --- Upcoming Sub-tab ---
        self.swaps_upcoming_tab = ttk.Frame(self.swaps_sub_notebook)
        self.swaps_sub_notebook.add(self.swaps_upcoming_tab, text="Upcoming")
        self._build_swaps_subtab(self.swaps_upcoming_tab, "upcoming")

        # Bind tab change event
        self.swaps_sub_notebook.bind(
            "<<NotebookTabChanged>>", self._on_swaps_subtab_changed
        )

    def _build_swaps_subtab(self, parent_frame, subtab_type: str):
        """Build a sub-tab for swaps (Current/History/Upcoming)."""
        # Controls frame
        controls_frame = ttk.LabelFrame(parent_frame, text="Shift Swaps")
        controls_frame.pack(fill="both", expand=True, pady=(0, 8), padx=8)

        # Date selection
        date_frame = ttk.Frame(controls_frame)
        date_frame.pack(fill="x", padx=8, pady=8)

        ttk.Label(date_frame, text="Date:").grid(
            row=0, column=0, sticky="w", padx=(0, 4)
        )
        swap_date_var = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(date_frame, textvariable=swap_date_var, width=12).grid(
            row=0, column=1, padx=(0, 16)
        )

        # Person A selection
        ttk.Label(date_frame, text="Person A:").grid(
            row=0, column=2, sticky="w", padx=(0, 4)
        )
        swap_person_a_var = tk.StringVar()
        swap_person_a_combo = ttk.Combobox(
            date_frame, textvariable=swap_person_a_var, state="readonly", width=15
        )
        swap_person_a_combo.grid(row=0, column=3, padx=(0, 8))

        ttk.Label(date_frame, text="Shift:").grid(
            row=0, column=4, sticky="w", padx=(0, 4)
        )
        swap_shift_a_var = tk.StringVar(value="1")
        swap_shift_a_combo = ttk.Combobox(
            date_frame,
            textvariable=swap_shift_a_var,
            values=["1", "2", "3"],
            state="readonly",
            width=5,
        )
        swap_shift_a_combo.grid(row=0, column=5)

        # Person B selection
        ttk.Label(date_frame, text="Person B:").grid(
            row=0, column=6, sticky="w", padx=(0, 4)
        )
        swap_person_b_var = tk.StringVar()
        swap_person_b_combo = ttk.Combobox(
            date_frame, textvariable=swap_person_b_var, state="readonly", width=15
        )
        swap_person_b_combo.grid(row=0, column=7, padx=(0, 8))

        ttk.Label(date_frame, text="Shift:").grid(
            row=0, column=8, sticky="w", padx=(0, 4)
        )
        swap_shift_b_var = tk.StringVar(value="2")
        swap_shift_b_combo = ttk.Combobox(
            date_frame,
            textvariable=swap_shift_b_var,
            values=["1", "2", "3"],
            state="readonly",
            width=5,
        )
        swap_shift_b_combo.grid(row=0, column=9)

        ttk.Button(date_frame, text="Add Swap", command=self._on_add_swap).grid(
            row=0, column=10, padx=(16, 0)
        )
        ttk.Button(
            date_frame, text="Delete Selected", command=self._on_delete_swap
        ).grid(row=0, column=11)

        # Store references for each sub-tab
        setattr(self, f"swap_date_var_{subtab_type}", swap_date_var)
        setattr(self, f"swap_person_a_var_{subtab_type}", swap_person_a_var)
        setattr(self, f"swap_person_a_combo_{subtab_type}", swap_person_a_combo)
        setattr(self, f"swap_shift_a_var_{subtab_type}", swap_shift_a_var)
        setattr(self, f"swap_shift_a_combo_{subtab_type}", swap_shift_a_combo)
        setattr(self, f"swap_person_b_var_{subtab_type}", swap_person_b_var)
        setattr(self, f"swap_person_b_combo_{subtab_type}", swap_person_b_combo)
        setattr(self, f"swap_shift_b_var_{subtab_type}", swap_shift_b_var)
        setattr(self, f"swap_shift_b_combo_{subtab_type}", swap_shift_b_combo)

        # Swaps list
        swaps_frame = ttk.LabelFrame(controls_frame, text="Swaps List")
        swaps_frame.pack(fill="both", expand=True, pady=(8, 0))

        columns = ("id", "date", "person_a", "shift_a", "person_b", "shift_b")
        swaps_tree = ttk.Treeview(
            swaps_frame, columns=columns, show="headings", height=12
        )
        swaps_tree.heading("id", text="ID")
        swaps_tree.heading("date", text="Date")
        swaps_tree.heading("person_a", text="Person A")
        swaps_tree.heading("shift_a", text="Shift A")
        swaps_tree.heading("person_b", text="Person B")
        swaps_tree.heading("shift_b", text="Shift B")
        swaps_tree.column("id", width=50)
        swaps_tree.column("date", width=100)
        swaps_tree.column("person_a", width=150)
        swaps_tree.column("shift_a", width=60)
        swaps_tree.column("person_b", width=150)
        swaps_tree.column("shift_b", width=60)

        swap_v_scroll = ttk.Scrollbar(
            swaps_frame, orient="vertical", command=swaps_tree.yview
        )
        swap_h_scroll = ttk.Scrollbar(
            swaps_frame, orient="horizontal", command=swaps_tree.xview
        )
        swaps_tree.configure(
            yscrollcommand=swap_v_scroll.set, xscrollcommand=swap_h_scroll.set
        )
        swaps_tree.grid(row=0, column=0, sticky="nsew")
        swap_v_scroll.grid(row=0, column=1, sticky="ns")
        swap_h_scroll.grid(row=1, column=0, sticky="ew")

        swaps_frame.grid_rowconfigure(0, weight=1)
        swaps_frame.grid_columnconfigure(0, weight=1)

        # Store tree reference
        setattr(self, f"swaps_tree_{subtab_type}", swaps_tree)

    def _build_notifications_tab(self):
        """Build the notifications configuration tab."""
        main_frame = ttk.Frame(self.notifications_tab)
        main_frame.pack(fill="both", expand=True, padx=8, pady=8)

        # Telegram configuration
        telegram_frame = ttk.LabelFrame(main_frame, text="Telegram Notifications")
        telegram_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(telegram_frame, text="Bot Token:").grid(
            row=0, column=0, sticky="w", padx=8, pady=4
        )
        self.telegram_bot_token_var = tk.StringVar()
        ttk.Entry(
            telegram_frame, textvariable=self.telegram_bot_token_var, width=40
        ).grid(row=0, column=1, padx=8, pady=4)

        ttk.Label(telegram_frame, text="Team Group Chat ID:").grid(
            row=1, column=0, sticky="w", padx=8, pady=4
        )
        self.telegram_team_chat_var = tk.StringVar()
        ttk.Entry(
            telegram_frame, textvariable=self.telegram_team_chat_var, width=40
        ).grid(row=1, column=1, padx=8, pady=4)

        ttk.Label(telegram_frame, text="All-Teams Group Chat ID:").grid(
            row=2, column=0, sticky="w", padx=8, pady=4
        )
        self.telegram_all_chat_var = tk.StringVar()
        ttk.Entry(
            telegram_frame, textvariable=self.telegram_all_chat_var, width=40
        ).grid(row=2, column=1, padx=8, pady=4)

        # Email configuration
        email_frame = ttk.LabelFrame(main_frame, text="Email Notifications")
        email_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(email_frame, text="SMTP Server:").grid(
            row=0, column=0, sticky="w", padx=8, pady=4
        )
        self.smtp_server_var = tk.StringVar()
        ttk.Entry(email_frame, textvariable=self.smtp_server_var, width=40).grid(
            row=0, column=1, padx=8, pady=4
        )

        ttk.Label(email_frame, text="SMTP Port:").grid(
            row=1, column=0, sticky="w", padx=8, pady=4
        )
        self.smtp_port_var = tk.StringVar(value="587")
        ttk.Entry(email_frame, textvariable=self.smtp_port_var, width=10).grid(
            row=1, column=1, sticky="w", padx=8, pady=4
        )

        ttk.Label(email_frame, text="Username:").grid(
            row=2, column=0, sticky="w", padx=8, pady=4
        )
        self.smtp_username_var = tk.StringVar()
        ttk.Entry(email_frame, textvariable=self.smtp_username_var, width=40).grid(
            row=2, column=1, padx=8, pady=4
        )

        ttk.Label(email_frame, text="Password:").grid(
            row=3, column=0, sticky="w", padx=8, pady=4
        )
        self.smtp_password_var = tk.StringVar()
        ttk.Entry(
            email_frame, textvariable=self.smtp_password_var, width=40, show="*"
        ).grid(row=3, column=1, padx=8, pady=4)

        ttk.Label(email_frame, text="From Address:").grid(
            row=4, column=0, sticky="w", padx=8, pady=4
        )
        self.smtp_from_var = tk.StringVar()
        ttk.Entry(email_frame, textvariable=self.smtp_from_var, width=40).grid(
            row=4, column=1, padx=8, pady=4
        )

        # Notification settings
        settings_frame = ttk.LabelFrame(main_frame, text="Notification Settings")
        settings_frame.pack(fill="x", pady=(0, 8))

        self.notify_on_swap_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            settings_frame,
            text="Notify on shift swap",
            variable=self.notify_on_swap_var,
        ).grid(row=0, column=0, sticky="w", padx=8, pady=4)

        self.notify_on_substitution_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            settings_frame,
            text="Notify on substitution",
            variable=self.notify_on_substitution_var,
        ).grid(row=1, column=0, sticky="w", padx=8, pady=4)

        self.notify_on_schedule_change_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            settings_frame,
            text="Notify on schedule change",
            variable=self.notify_on_schedule_change_var,
        ).grid(row=2, column=0, sticky="w", padx=8, pady=4)

        # Save button
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(8, 0))

        ttk.Button(
            button_frame,
            text="Save Notification Settings",
            command=self._on_save_notifications,
        ).pack(side="right", padx=(8, 0))
        ttk.Button(
            button_frame,
            text="Load Settings",
            command=self._on_load_notification_settings,
        ).pack(side="right", padx=(8, 0))

        # Notification history
        history_frame = ttk.LabelFrame(main_frame, text="Notification History")
        history_frame.pack(fill="both", expand=True, pady=(8, 0))

        columns = ("id", "type", "recipient", "status", "created_at")
        self.notifications_tree = ttk.Treeview(
            history_frame, columns=columns, show="headings", height=10
        )
        self.notifications_tree.heading("id", text="ID")
        self.notifications_tree.heading("type", text="Type")
        self.notifications_tree.heading("recipient", text="Recipient")
        self.notifications_tree.heading("status", text="Status")
        self.notifications_tree.heading("created_at", text="Created")
        self.notifications_tree.column("id", width=50)
        self.notifications_tree.column("type", width=100)
        self.notifications_tree.column("recipient", width=150)
        self.notifications_tree.column("status", width=80)
        self.notifications_tree.column("created_at", width=120)

        notif_v_scroll = ttk.Scrollbar(
            history_frame, orient="vertical", command=self.notifications_tree.yview
        )
        self.notifications_tree.configure(yscrollcommand=notif_v_scroll.set)
        self.notifications_tree.grid(row=0, column=0, sticky="nsew")
        notif_v_scroll.grid(row=0, column=1, sticky="ns")
        history_frame.grid_rowconfigure(0, weight=1)
        history_frame.grid_columnconfigure(0, weight=1)

    def _on_save_notifications(self):
        """Save notification settings to metadata."""
        set_metadata("telegram_bot_token", self.telegram_bot_token_var.get())
        set_metadata("telegram_team_chat_id", self.telegram_team_chat_var.get())
        set_metadata("telegram_all_chat_id", self.telegram_all_chat_var.get())
        set_metadata("smtp_server", self.smtp_server_var.get())
        set_metadata("smtp_port", self.smtp_port_var.get())
        set_metadata("smtp_username", self.smtp_username_var.get())
        set_metadata("smtp_password", self.smtp_password_var.get())
        set_metadata("smtp_from", self.smtp_from_var.get())
        set_metadata("notify_on_swap", str(self.notify_on_swap_var.get()))
        set_metadata(
            "notify_on_substitution", str(self.notify_on_substitution_var.get())
        )
        set_metadata(
            "notify_on_schedule_change", str(self.notify_on_schedule_change_var.get())
        )
        messagebox.showinfo(
            "Settings Saved", "Notification settings saved successfully!"
        )

    def _on_load_notification_settings(self):
        """Load notification settings from metadata."""
        self.telegram_bot_token_var.set(get_metadata("telegram_bot_token", "") or "")
        self.telegram_team_chat_var.set(get_metadata("telegram_team_chat_id", "") or "")
        self.telegram_all_chat_var.set(get_metadata("telegram_all_chat_id", "") or "")
        self.smtp_server_var.set(get_metadata("smtp_server", "") or "")
        self.smtp_port_var.set(get_metadata("smtp_port", "587") or "587")
        self.smtp_username_var.set(get_metadata("smtp_username", "") or "")
        self.smtp_password_var.set(get_metadata("smtp_password", "") or "")
        self.smtp_from_var.set(get_metadata("smtp_from", "") or "")
        self.notify_on_swap_var.set(get_metadata("notify_on_swap", "True") == "True")
        self.notify_on_substitution_var.set(
            get_metadata("notify_on_substitution", "True") == "True"
        )
        self.notify_on_schedule_change_var.set(
            get_metadata("notify_on_schedule_change", "False") == "True"
        )

    def _refresh_notifications(self):
        """Refresh the notifications history tree."""
        for item in self.notifications_tree.get_children():
            self.notifications_tree.delete(item)

        # Get notification queue from repository
        repo = get_repo()
        notifications = repo.get_pending_notifications(limit=100)
        for notif in notifications:
            notif_dict = _to_dict(notif) if not isinstance(notif, dict) else notif
            self.notifications_tree.insert(
                "",
                "end",
                values=(
                    notif_dict.get("id", ""),
                    notif_dict.get("target_type", ""),
                    notif_dict.get("target_id", ""),
                    notif_dict.get("status", ""),
                    notif_dict.get("created_at", ""),
                ),
            )

    # Event handlers
    def _refresh_all(self):
        """Refresh all data in the UI."""
        self._refresh_teams()
        self._refresh_people()
        self._refresh_exception_people()
        self._refresh_swap_people()
        self._refresh_exceptions()
        self._refresh_swaps()
        self._refresh_notifications()
        self._refresh_manual_config()  # Refresh manual config when model/date changes
        self._on_load_schedule()

    def _refresh_teams(self):
        """Refresh the teams treeview."""
        for item in self.teams_tree.get_children():
            self.teams_tree.delete(item)

        teams = get_teams()
        member_counts = get_all_team_member_counts()
        for team in teams:
            member_count = member_counts.get(team["id"], 0)
            # Show color as a colored square
            color_display = f"  {team['color']}  "
            self.teams_tree.insert(
                "",
                "end",
                values=(
                    team["id"],
                    team["name"],
                    color_display,
                    team["offset"],
                    member_count,
                ),
            )

    def _refresh_people(self):
        """Refresh the people treeview."""
        for item in self.people_tree.get_children():
            self.people_tree.delete(item)

        people = get_people(active_only=False)
        teams = get_teams()
        team_map = {t["id"]: t["name"] for t in teams}

        for person in people:
            # Get team name
            team_id = person.get("team_id")
            team_name = team_map.get(team_id, "Unassigned") if team_id else "Unassigned"
            active_text = "Yes" if person["active"] else "No"
            telegram = person.get("telegram_chat_id", "") or ""
            email = person.get("email", "") or ""
            self.people_tree.insert(
                "",
                "end",
                values=(
                    person["id"],
                    person["name"],
                    telegram,
                    email,
                    team_name,
                    person["role"],
                    active_text,
                ),
            )

    def _refresh_exception_people(self):
        """Refresh the person combobox for exceptions in all sub-tabs."""
        people = get_people(active_only=False)
        teams = get_teams()
        team_map = {t["id"]: t["name"] for t in teams}

        person_names = []
        for p in people:
            team_id = p.get("team_id")
            team_name = team_map.get(team_id, "Unassigned") if team_id else "Unassigned"
            person_names.append(f"{p['name']} (Team: {team_name})")

        # Update all sub-tab combos
        for subtab_type in ("current", "history", "upcoming"):
            combo = getattr(self, f"exception_person_combo_{subtab_type}", None)
            if combo:
                combo["values"] = person_names

        # Store mapping for lookup
        self._exception_person_map = {
            f"{p['name']} (Team: {team_map.get(p.get('team_id'), 'Unassigned') if p.get('team_id') else 'Unassigned'})": p[
                "id"
            ]
            for p in people
        }

    def _refresh_swap_people(self):
        """Refresh the person comboboxes for swaps in all sub-tabs."""
        people = get_people(active_only=False)
        person_names = [p["name"] for p in people]

        # Update all sub-tab combos
        for subtab_type in ("current", "history", "upcoming"):
            combo_a = getattr(self, f"swap_person_a_combo_{subtab_type}", None)
            combo_b = getattr(self, f"swap_person_b_combo_{subtab_type}", None)
            if combo_a:
                combo_a["values"] = person_names
            if combo_b:
                combo_b["values"] = person_names

        # Store mapping for lookup
        self._swap_person_map = {p["name"]: p["id"] for p in people}

        # Update shift combo boxes based on current model
        model = self.shift_model.get()
        if model == "2-shift":
            shift_values = ["1", "2"]
        else:
            shift_values = ["1", "2", "3"]

        for subtab_type in ("current", "history", "upcoming"):
            combo_a = getattr(self, f"swap_shift_a_combo_{subtab_type}", None)
            combo_b = getattr(self, f"swap_shift_b_combo_{subtab_type}", None)
            if combo_a:
                combo_a["values"] = shift_values
            if combo_b:
                combo_b["values"] = shift_values
            # Reset to first valid value
            var_a = getattr(self, f"swap_shift_a_var_{subtab_type}", None)
            var_b = getattr(self, f"swap_shift_b_var_{subtab_type}", None)
            if var_a and shift_values:
                var_a.set(shift_values[0])
            if var_b and shift_values:
                var_b.set(shift_values[1] if len(shift_values) > 1 else shift_values[0])

    def _refresh_exceptions(self, subtab_type: str = None):
        """Refresh the exceptions treeview for a specific sub-tab."""
        if subtab_type is None:
            subtab_type = self._get_current_exceptions_subtab()

        vars = self._get_exceptions_vars(subtab_type)
        tree = vars["tree"]

        if not tree:
            return

        for item in tree.get_children():
            tree.delete(item)

        # Determine date range filter based on sub-tab type
        today = date.today()
        if subtab_type == "current":
            # Current month
            start_filter = today.replace(day=1)
            end_filter = (
                start_filter.replace(month=start_filter.month + 1)
                if start_filter.month < 12
                else start_filter.replace(year=start_filter.year + 1, month=1)
            ) - timedelta(days=1)
        elif subtab_type == "history":
            # All past (before current month)
            start_filter = date(1900, 1, 1)
            end_filter = today.replace(day=1) - timedelta(days=1)
        elif subtab_type == "upcoming":
            # Future (after current month)
            start_filter = (
                today.replace(day=1).replace(month=today.month + 1)
                if today.month < 12
                else today.replace(year=today.year + 1, month=1, day=1)
            )
            end_filter = date(2100, 1, 1)
        else:
            start_filter = date(1900, 1, 1)
            end_filter = date(2100, 1, 1)

        exceptions = get_availability_exceptions()
        for exc in exceptions:
            exc_start = date.fromisoformat(exc["start_date"])
            exc_end = date.fromisoformat(exc["end_date"])

            # Check if exception overlaps with filter range
            if exc_end < start_filter or exc_start > end_filter:
                continue

            person = get_person(exc["person_id"])
            person_name = person["name"] if person else "Unknown"
            tree = vars["tree"]
            if tree:
                tree.insert(
                    "",
                    "end",
                    values=(
                        exc["id"],
                        person_name,
                        exc["start_date"],
                        exc["end_date"],
                        exc["reason"],
                    ),
                )

    def _refresh_swaps(self, subtab_type: str = None):
        """Refresh the swaps treeview for a specific sub-tab."""
        if subtab_type is None:
            subtab_type = self._get_current_swaps_subtab()

        tree = getattr(self, f"swaps_tree_{subtab_type}", None)
        if not tree:
            return

        for item in tree.get_children():
            tree.delete(item)

        # Determine date range filter based on sub-tab type
        today = date.today()
        if subtab_type == "current":
            # Current month ±30 days
            start_filter = today - timedelta(days=30)
            end_filter = today + timedelta(days=30)
        elif subtab_type == "history":
            # All past
            start_filter = date(1900, 1, 1)
            end_filter = today - timedelta(days=1)
        elif subtab_type == "upcoming":
            # Future
            start_filter = today + timedelta(days=1)
            end_filter = date(2100, 1, 1)
        else:
            start_filter = date(1900, 1, 1)
            end_filter = date(2100, 1, 1)

        swaps = get_shift_swaps(start_filter, end_filter)
        tree = getattr(self, f"swaps_tree_{subtab_type}", None)
        if not tree:
            return

        for swap in swaps:
            tree.insert(
                "",
                "end",
                values=(
                    swap["id"],
                    swap["schedule_date"],
                    swap["person_a_name"],
                    swap["shift_a"],
                    swap["person_b_name"],
                    swap["shift_b"],
                ),
            )

    def _get_current_swaps_subtab(self) -> str:
        """Get the current swaps sub-tab type."""
        if not hasattr(self, "swaps_sub_notebook"):
            return "current"
        tab_id = self.swaps_sub_notebook.select()
        if not tab_id:
            return "current"
        tab_text = self.swaps_sub_notebook.tab(tab_id, "text")
        return tab_text.lower()

    def _on_swaps_subtab_changed(self, event=None):
        """Handle swaps sub-tab change."""
        self._refresh_swaps()

    def _on_load_schedule(self):
        """Load and display the schedule for 18 months from initial date."""
        try:
            initial_date = date.fromisoformat(self.initial_date_var.get())
            # Generate 18 months (approx 548 days)
            end_date = initial_date + timedelta(days=547)
            cycle_start = initial_date

            self._set_busy(True)
            self.status_var.set("Loading schedule...")

            def load_schedule():
                return get_schedule_grid(initial_date, end_date, cycle_start)

            def on_done(result):
                self.schedule_data = result
                self._setup_schedule_columns()
                self._populate_schedule_tree()
                # Don't refresh manual config here - it would reset user selections
                # self._refresh_manual_config()  # Only call when initial date/model changes
                self.status_var.set(
                    f"Loaded schedule for {len(result)} days (18 months)"
                )
                self._set_busy(False)

            def on_error(exc):
                self.status_var.set(f"Error: {str(exc)}")
                messagebox.showerror("Schedule Error", str(exc))
                self._set_busy(False)

            self._run_in_background(load_schedule, on_done, on_error)

        except ValueError as e:
            messagebox.showerror("Invalid Date", f"Please enter valid dates: {str(e)}")

    def _on_shift_model_change(self, event=None):
        """Handle shift model change - switch model, regenerate teams, clear schedule."""
        model = self.shift_model.get()

        # Confirm with user
        result = messagebox.askyesno(
            "Switch Shift Model",
            f"Switching to {model} will:\n"
            f"• Regenerate teams (3 teams for 2-shift, 5 for 3-shift)\n"
            f"• Clear all existing shift assignments\n"
            f"• People will become unassigned\n\n"
            f"Continue?",
        )
        if not result:
            # Revert combo box
            current_model = get_current_shift_model()
            self.shift_model.set(current_model)
            return

        try:
            self._set_busy(True)
            self.status_var.set(f"Switching to {model}...")

            def switch_model():
                return set_shift_model(model)

            def on_done(success):
                if success:
                    self.status_var.set(f"Switched to {model}. Teams regenerated.")
                    self._refresh_all()
                else:
                    self.status_var.set("Failed to switch model")
                    messagebox.showerror("Error", "Failed to switch shift model")
                self._set_busy(False)

            def on_error(exc):
                self.status_var.set(f"Error: {str(exc)}")
                messagebox.showerror("Error", str(exc))
                self._set_busy(False)

            self._run_in_background(switch_model, on_done, on_error)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to switch model: {str(e)}")
            self._set_busy(False)

    def _refresh_manual_config(self):
        """Refresh the manual first 2 days configuration UI."""
        # Clear existing widgets
        for widget in self.manual_config_frame.winfo_children():
            widget.destroy()

        self.manual_config_vars = {}

        teams = get_teams()
        if not teams:
            ttk.Label(self.manual_config_frame, text="No teams configured").pack(pady=8)
            return

        initial_date = date.fromisoformat(self.initial_date_var.get())

        # Header row
        ttk.Label(self.manual_config_frame, text="Team", font=self.fUIBold).grid(
            row=0, column=0, padx=8, pady=4
        )
        for day_offset in range(2):
            config_date = initial_date + timedelta(days=day_offset)
            ttk.Label(
                self.manual_config_frame,
                text=f"Day {day_offset + 1}\n{config_date.strftime('%Y-%m-%d (%a)')}",
                font=self.fUIBold,
            ).grid(row=0, column=day_offset + 1, padx=8, pady=4)

        # Team rows
        for i, team in enumerate(teams):
            ttk.Label(self.manual_config_frame, text=team["name"]).grid(
                row=i + 1, column=0, padx=8, pady=4, sticky="w"
            )

            for day_offset in range(2):
                config_date = initial_date + timedelta(days=day_offset)
                var = tk.StringVar(value="AUTO")
                self.manual_config_vars[(team["id"], day_offset)] = var

                # Get shift options based on current model
                model = self.shift_model.get()
                if model == "2-shift":
                    shift_options = ["AUTO", "1st", "2nd", "OFF"]
                else:
                    shift_options = ["AUTO", "1st", "2nd", "3rd", "OFF"]

                combo = ttk.Combobox(
                    self.manual_config_frame,
                    textvariable=var,
                    values=shift_options,
                    state="readonly",
                    width=8,
                )
                combo.grid(row=i + 1, column=day_offset + 1, padx=8, pady=4)
                combo.bind(
                    "<<ComboboxSelected>>",
                    lambda e, t=team["id"], d=day_offset: self._on_manual_config_change(
                        t, d
                    ),
                )

        # Apply button
        apply_frame = ttk.Frame(self.manual_config_frame)
        apply_frame.grid(row=len(teams) + 1, column=0, columnspan=3, pady=8)
        ttk.Button(
            apply_frame,
            text="Apply Manual Configuration",
            command=self._on_apply_manual_config,
        ).pack()

    def _on_manual_config_change(self, team_id: int, day_offset: int):
        """Handle manual configuration change - stores selection but doesn't regenerate."""
        var = self.manual_config_vars.get((team_id, day_offset))
        if var:
            value = var.get()
            initial_date = date.fromisoformat(self.initial_date_var.get())
            config_date = initial_date + timedelta(days=day_offset)

            if value == "AUTO":
                # Remove manual override
                self.manual_first_days.pop((team_id, config_date), None)
            else:
                # Store manual override
                shift_map = {"1st": 1, "2nd": 2, "3rd": 3, "OFF": 0}
                self.manual_first_days[(team_id, config_date)] = shift_map.get(value, 0)

    def _on_apply_manual_config(self):
        """Apply manual first 2 days configuration by regenerating schedule."""
        if not self.manual_first_days:
            messagebox.showinfo("No Changes", "No manual overrides configured.")
            return

        initial_date = date.fromisoformat(self.initial_date_var.get())
        end_date = initial_date + timedelta(days=547)  # 18 months
        cycle_start = initial_date

        result = messagebox.askyesno(
            "Apply Manual Configuration",
            f"This will regenerate the schedule from {initial_date} to {end_date} (18 months)\n"
            f"with {len(self.manual_first_days)} manual override(s) for the first 2 days.\n"
            f"All existing assignments will be replaced.\n\nContinue?",
        )
        if not result:
            return

        self._set_busy(True)
        self.status_var.set("Applying manual configuration...")

        def do_generate_schedule():
            return generate_schedule(
                initial_date,
                end_date,
                cycle_start,
                use_substitutes=True,
                manual_overrides=self.manual_first_days,
            )

        def on_done(result):
            message = f"Schedule regenerated with manual overrides!\n"
            message += f"Assignments: {len(result['assignments'])}\n"
            message += f"Conflicts: {len(result['conflicts'])}\n"
            message += f"Substitutes used: {len(result['substitutes_used'])}\n"
            message += f"Unfilled shifts: {len(result['unfilled_shifts'])}"

            messagebox.showinfo("Generation Complete", message)
            self.status_var.set("Schedule regenerated successfully")
            self._set_busy(False)
            self._on_load_schedule()  # Refresh the schedule view

        def on_error(exc):
            self.status_var.set(f"Error: {str(exc)}")
            messagebox.showerror("Generation Error", str(exc))
            self._set_busy(False)

        self._run_in_background(do_generate_schedule, on_done, on_error)

    def _setup_schedule_columns(self):
        """Set up schedule tree columns dynamically based on teams."""
        teams = get_teams()

        # Clear existing columns
        self.schedule_tree["columns"] = ("date", "day")

        # Add team columns
        for team in teams:
            col_name = f"team_{team['id']}"
            self.schedule_tree["columns"] = (*self.schedule_tree["columns"], col_name)

        # Set headings
        self.schedule_tree.heading("date", text="Date")
        self.schedule_tree.heading("day", text="Day")
        for team in teams:
            col_name = f"team_{team['id']}"
            self.schedule_tree.heading(col_name, text=team["name"])
            self.schedule_tree.column(col_name, width=120, anchor="center")

        # Set base column widths
        self.schedule_tree.column("date", width=100, anchor="center")
        self.schedule_tree.column("day", width=100, anchor="center")

    def _populate_schedule_tree(self):
        """Populate the schedule treeview with schedule data."""
        for item in self.schedule_tree.get_children():
            self.schedule_tree.delete(item)

        teams = get_teams()
        search_term = (
            self.search_var.get().lower() if hasattr(self, "search_var") else ""
        )

        for i, row in enumerate(self.schedule_data):
            # Format team data dynamically - only shift, no person names
            values = [row["date"], row["day_name"]]

            # Check if this row matches search (person name in any team)
            row_matches = True
            if search_term:
                row_matches = False
                for team in teams:
                    team_data = row["teams"].get(
                        team["id"],
                        {"shift": "OFF", "person": "", "is_sub": False},
                    )
                    if (
                        team_data["person"]
                        and search_term in team_data["person"].lower()
                    ):
                        row_matches = True
                        break

            if not row_matches:
                continue

            # Determine row tag based on cell states
            row_has_unfilled = False
            row_has_unavailable = False
            row_has_swapped = False
            row_has_substituted = False

            for team in teams:
                team_data = row["teams"].get(
                    team["id"],
                    {"shift": "OFF", "person": "", "is_sub": False},
                )

                # Format team display - only shift
                if team_data["shift"] == "OFF":
                    values.append("OFF")
                else:
                    shift_text = team_data["shift"]
                    if team_data.get("unfilled"):
                        # Unfilled shift - needs coverage
                        shift_text = "NEEDS COVERAGE"
                        row_has_unfilled = True
                    elif team_data["is_sub"]:
                        shift_text += " (S)"
                        row_has_substituted = True
                    elif team_data.get("is_swapped"):
                        row_has_swapped = True
                    elif team_data.get("is_unavailable"):
                        row_has_unavailable = True
                    values.append(shift_text)

            # Apply color coding tags based on cell states (priority: unfilled > unavailable > swapped > substituted > zebra)
            if row_has_unfilled:
                tag = "unfilled"
            elif row_has_unavailable:
                tag = "unavailable"
            elif row_has_swapped:
                tag = "swapped"
            elif row_has_substituted:
                tag = "substituted"
            else:
                tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.schedule_tree.insert("", "end", values=values, tags=(tag,))

    # Search handlers
    def _on_search_changed(self):
        """Handle search text change - repopulate grid with filter."""
        self._populate_schedule_tree()

    def _on_clear_search(self):
        """Clear search filter."""
        self.search_var.set("")
        self._populate_schedule_tree()

    # Tooltip handlers
    def _on_tree_motion(self, event):
        """Show tooltip with squad members on hover."""
        # Identify row and column under mouse
        region = self.schedule_tree.identify("region", event.x, event.y)
        if region != "cell":
            self._hide_tooltip()
            return

        row_id = self.schedule_tree.identify_row(event.y)
        col_id = self.schedule_tree.identify_column(event.x)

        if not row_id or not col_id:
            self._hide_tooltip()
            return

        # Skip date/day columns (col #1 and #2)
        col_index = int(col_id.replace("#", ""))
        if col_index <= 2:
            self._hide_tooltip()
            return

        # Check if tooltip already shown for this cell
        if self.tooltip_item == row_id and self.tooltip_col == col_id:
            return

        # Get team index (col_index - 3 because date=1, day=2, team_1=3, etc.)
        team_index = col_index - 3
        teams = get_teams()
        if team_index >= len(teams):
            self._hide_tooltip()
            return

        team = teams[team_index]
        row_data = self.schedule_tree.item(row_id)
        date_str = row_data["values"][0]

        # Get squad members for this team/date
        squad_info = self._get_squad_for_team_date(team["id"], date_str)
        if not squad_info:
            self._hide_tooltip()
            return

        self._show_tooltip(
            event.x_root, event.y_root, squad_info, team["name"], date_str
        )
        self.tooltip_item = row_id
        self.tooltip_col = col_id

    def _on_tree_leave(self, event):
        """Hide tooltip when mouse leaves tree."""
        self._hide_tooltip()

    def _on_tree_click(self, event):
        """Handle click on team cell - populate squad details in right pane."""
        # Identify row and column under mouse
        region = self.schedule_tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        row_id = self.schedule_tree.identify_row(event.y)
        col_id = self.schedule_tree.identify_column(event.x)

        if not row_id or not col_id:
            return

        # Skip date/day columns (col #1 and #2)
        col_index = int(col_id.replace("#", ""))
        if col_index <= 2:
            return

        # Get team index (col_index - 3 because date=1, day=2, team_1=3, etc.)
        team_index = col_index - 3
        teams = get_teams()
        if team_index >= len(teams):
            return

        team = teams[team_index]
        row_data = self.schedule_tree.item(row_id)
        date_str = row_data["values"][0]
        shift_text = row_data["values"][
            col_index - 1
        ]  # -1 because values array is 0-indexed

        # Populate squad details in right pane
        self._populate_squad_details(team, date_str, shift_text)

    def _on_tree_double_click(self, event):
        """Handle double-click on team cell - same as single click for now."""
        self._on_tree_click(event)

    def _populate_squad_details(self, team: dict, date_str: str, shift_text: str):
        """Populate the right pane with squad details for the selected team/date/shift."""
        # Update header
        self.squad_header_var.set(f"{team['name']} - {date_str} - {shift_text}")

        # Clear existing squad tree
        for item in self.squad_tree.get_children():
            self.squad_tree.delete(item)

        # Clear any existing substitute action frame
        if hasattr(self, "substitute_action_frame") and self.substitute_action_frame:
            self.substitute_action_frame.destroy()
            self.substitute_action_frame = None

        try:
            target_date = date.fromisoformat(date_str)
            persons = get_people(active_only=True)
            team_persons = [p for p in persons if p.get("team_id") == team["id"]]

            if not team_persons:
                return

            # Check if this is an unfilled shift (NEEDS COVERAGE)
            is_unfilled = shift_text == "NEEDS COVERAGE"
            unfilled_info = None

            if is_unfilled:
                # Fetch unfilled shift info from database
                unfilled_shifts = get_repo().get_unfilled_shifts(
                    target_date, target_date
                )
                for u in unfilled_shifts:
                    if u["team_id"] == team["id"] and u[
                        "shift_type"
                    ] == self._shift_name_to_int(shift_text):
                        unfilled_info = u
                        break

            # Check assignments for this date
            assignments = get_repo().get_assignments(target_date, target_date)
            team_assignments = [a for a in assignments if a.team_id == team["id"]]

            # Check swaps for this date
            swaps = get_repo().get_swaps(target_date, target_date)
            swap_map = {}
            for s in swaps:
                if s["person_a_id"] not in swap_map:
                    swap_map[s["person_a_id"]] = []
                if s["person_b_id"] not in swap_map:
                    swap_map[s["person_b_id"]] = []
                swap_map[s["person_a_id"]].append(
                    {"person_id": s["person_b_id"], "shift": s["shift_b"]}
                )
                swap_map[s["person_b_id"]].append(
                    {"person_id": s["person_a_id"], "shift": s["shift_a"]}
                )

            # Check exceptions for this date
            exceptions = get_repo().get_exceptions()
            exception_map = {}
            for exc in exceptions:
                exc_start = date.fromisoformat(exc["start_date"])
                exc_end = date.fromisoformat(exc["end_date"])
                if exc_start <= target_date <= exc_end:
                    exception_map[exc["person_id"]] = True

            # Build a map of person_id -> assignment info for this team/date
            assignment_map = {}
            for a in team_assignments:
                person = get_person(a.person_id)
                shift_name = a.shift_type.name
                sub_text = " (Substitute)" if a.is_substitute else ""
                assignment_map[a.person_id] = {
                    "shift": shift_name + sub_text,
                    "status": "Assigned" + (" (Sub)" if a.is_substitute else ""),
                    "person_name": person["name"] if person else "Unknown",
                    "is_substitute": a.is_substitute,
                }

            # Add all team members to squad tree with status indicators
            for i, p in enumerate(team_persons):
                person_id = p["id"]
                # Check if this person is assigned to the specific shift clicked
                is_assigned_to_shift = False
                if person_id in assignment_map:
                    assign_info = assignment_map[person_id]
                    # shift_text from grid is like "1st", "2nd", "3rd", "OFF", "1st (S)", etc.
                    # Check if the assigned shift matches the clicked shift (ignoring substitute marker)
                    assigned_shift = (
                        assign_info["shift"]
                        .replace(" (Substitute)", "")
                        .replace(" (Sub)", "")
                    )
                    if shift_text.replace(" (S)", "") == assigned_shift:
                        is_assigned_to_shift = True

                # Determine status indicators
                is_unavailable = exception_map.get(person_id, False)
                is_swapped = person_id in swap_map
                is_substituted = assignment_map.get(person_id, {}).get(
                    "is_substitute", False
                )

                # Determine display status and tag
                if is_assigned_to_shift:
                    if is_unavailable:
                        status_text = "Unavailable ⚠"
                        tag = "unavailable"
                    elif is_swapped:
                        status_text = "Swapped ↔"
                        tag = "swapped"
                    elif is_substituted:
                        status_text = "Substituted ↻"
                        tag = "substituted"
                    else:
                        status_text = "Assigned ✓"
                        tag = "assigned"
                else:
                    if is_unavailable:
                        status_text = "Unavailable ⚠"
                        tag = "unavailable"
                    elif is_swapped:
                        status_text = "Swapped ↔"
                        tag = "swapped"
                    else:
                        status_text = "Available"
                        tag = "evenrow" if i % 2 == 0 else "oddrow"

                self.squad_tree.insert(
                    "",
                    "end",
                    values=(p["name"], p["role"], status_text),
                    tags=(tag,),
                )

            # Configure squad tree tags for color coding
            palette = self._get_palette()
            self.squad_tree.tag_configure(
                "assigned",
                background=palette["select"],
                foreground=palette["accent_text"],
            )
            self.squad_tree.tag_configure(
                "unavailable", background="#ffebee", foreground="#c62828"
            )
            self.squad_tree.tag_configure(
                "swapped", background="#e8f5e9", foreground="#2e7d32"
            )
            self.squad_tree.tag_configure(
                "substituted", background="#fff3e0", foreground="#e65100"
            )

            # If this is an unfilled shift, show recommended substitute and action buttons
            if is_unfilled and unfilled_info:
                self._show_substitute_action_panel(
                    team, date_str, shift_text, unfilled_info
                )

        except Exception as e:
            # Silently fail - just show empty squad
            pass

    def _shift_name_to_int(self, shift_name: str) -> int:
        """Convert shift name to integer (1, 2, 3)."""
        shift_map = {"FIRST": 1, "SECOND": 2, "THIRD": 3, "1st": 1, "2nd": 2, "3rd": 3}
        return shift_map.get(shift_name.upper(), 1)

    def _show_substitute_action_panel(
        self, team: dict, date_str: str, shift_text: str, unfilled_info: dict
    ):
        """Show panel with recommended substitute and Apply/Cancel buttons."""
        # Create action frame at the bottom of squad_frame
        squad_frame = (
            self.squad_tree.master.master
        )  # squad_frame is parent of squad_tree

        self.substitute_action_frame = ttk.Frame(squad_frame)
        self.substitute_action_frame.pack(fill="x", padx=8, pady=8, side="bottom")

        # Show recommended substitute info
        rec_name = unfilled_info.get("recommended_substitute_name", "None")
        rec_team_id = unfilled_info.get("recommended_substitute_team_id")
        rec_team_name = ""
        if rec_team_id:
            rec_team = get_team(rec_team_id)
            rec_team_name = f" (from {rec_team['name']})" if rec_team else ""

        reason = unfilled_info.get("reason", "No available team members")

        info_text = f"⚠ {reason}\nRecommended: {rec_name}{rec_team_name}"
        ttk.Label(
            self.substitute_action_frame,
            text=info_text,
            font=self.fSmall,
            foreground="#c62828",
            wraplength=280,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        # Buttons frame
        btn_frame = ttk.Frame(self.substitute_action_frame)
        btn_frame.pack(fill="x")

        def apply_substitute():
            """Apply the recommended substitute."""
            sub_id = unfilled_info.get("recommended_substitute_id")
            if not sub_id:
                messagebox.showwarning(
                    "No Substitute", "No recommended substitute available."
                )
                return

            # Confirm with user
            result = messagebox.askyesno(
                "Apply Substitute",
                f"Assign {rec_name}{rec_team_name} to {team['name']} {shift_text} on {date_str}?\n\n"
                f"This will create a substitute assignment.",
            )
            if not result:
                return

            # Create the substitute assignment
            # Use shift_type from unfilled_info (stored as int 1, 2, 3) instead of shift_text
            shift_type_int = unfilled_info.get("shift_type", 1)
            from shiftcore.models import ShiftAssignment, ShiftType
            from shiftcore.storage import get_repo

            assignment = ShiftAssignment(
                schedule_date=date.fromisoformat(date_str),
                shift_type=ShiftType(shift_type_int),
                person_id=sub_id,
                team_id=team["id"],
                is_substitute=True,
                substitute_for_id=None,
                notes=f"Substitute from team {rec_team_id}"
                if rec_team_id
                else "Manual substitute assignment",
            )

            get_repo().save_assignment(assignment)

            # Remove from unfilled shifts
            get_repo().delete_unfilled_shift(date_str, team["id"], shift_type_int)

            # Refresh schedule
            self._on_load_schedule()
            messagebox.showinfo(
                "Success", f"Substitute {rec_name} assigned successfully!"
            )

        def cancel_substitute():
            """Cancel - just close the panel."""
            self.substitute_action_frame.destroy()
            self.substitute_action_frame = None

        ttk.Button(
            btn_frame,
            text="Apply Substitute",
            command=apply_substitute,
            style="Accent.TButton",
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            btn_frame,
            text="Cancel",
            command=cancel_substitute,
        ).pack(side="left")

    def _get_squad_for_team_date(self, team_id: int, date_str: str) -> str:
        """Get squad members for a team on a specific date."""
        try:
            target_date = date.fromisoformat(date_str)
            persons = get_people(active_only=True)
            team_persons = [p for p in persons if p.get("team_id") == team_id]

            if not team_persons:
                return None

            # Check assignments for this date
            assignments = _get_repo().get_assignments(target_date, target_date)
            team_assignments = [a for a in assignments if a.team_id == team_id]

            lines = [f"Team: {get_team(team_id)['name']}", f"Date: {date_str}"]

            if team_assignments:
                for a in team_assignments:
                    person = get_person(a.person_id)
                    shift_name = a.shift_type.name
                    sub_text = " (Substitute)" if a.is_substitute else ""
                    lines.append(
                        f"  {shift_name}: {person.name if person else 'Unknown'}{sub_text}"
                    )
            else:
                # Show default squad
                for p in team_persons:
                    lines.append(f"  {p['name']} ({p['role']})")

            return "\n".join(lines)
        except Exception:
            return None

    def _show_tooltip(self, x: int, y: int, text: str, team_name: str, date_str: str):
        """Show tooltip window near mouse cursor."""
        self._hide_tooltip()

        self.tooltip_window = tk.Toplevel(self.root)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x + 10}+{y + 10}")

        label = tk.Label(
            self.tooltip_window,
            text=text,
            justify="left",
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            font=(self.sans_font, 9),
            padx=8,
            pady=4,
        )
        label.pack()

    def _hide_tooltip(self):
        """Hide tooltip window."""
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None
        self.tooltip_item = None
        self.tooltip_col = None

    def _on_generate_schedule(self):
        """Generate a new schedule based on current teams and people."""
        try:
            initial_date = date.fromisoformat(self.initial_date_var.get())
            end_date = initial_date + timedelta(days=547)  # 18 months
            cycle_start = initial_date

            result = messagebox.askyesno(
                "Generate Schedule",
                f"This will generate a schedule from {initial_date} to {end_date} (18 months).\n"
                f"All existing assignments in this range will be cleared.\n"
                f"Manual first 2 days configuration will be applied.\n"
                f"Continue?",
            )
            if not result:
                return

            self._set_busy(True)
            self.status_var.set("Generating schedule...")

            def do_generate_schedule():
                return generate_schedule(
                    initial_date,
                    end_date,
                    cycle_start,
                    use_substitutes=True,
                    manual_overrides=self.manual_first_days,
                )

            def on_done(result):
                message = f"Schedule generated!\n"
                message += f"Assignments: {len(result['assignments'])}\n"
                message += f"Conflicts: {len(result['conflicts'])}\n"
                message += f"Substitutes used: {len(result['substitutes_used'])}\n"
                message += f"Unfilled shifts: {len(result['unfilled_shifts'])}"

                messagebox.showinfo("Generation Complete", message)
                self.status_var.set("Schedule generated successfully")
                self._set_busy(False)
                self._on_load_schedule()  # Refresh the schedule view

            def on_error(exc):
                self.status_var.set(f"Error: {str(exc)}")
                messagebox.showerror("Generation Error", str(exc))
                self._set_busy(False)

            self._run_in_background(do_generate_schedule, on_done, on_error)

        except ValueError as e:
            messagebox.showerror("Invalid Date", f"Please enter valid dates: {str(e)}")

    def _on_export_csv(self):
        """Export the current schedule to CSV."""
        if not self.schedule_data:
            messagebox.showwarning("No Data", "Please load a schedule first")
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export Schedule as CSV",
        )

        if not filename:
            return

        try:
            import csv

            teams = get_teams()

            with open(filename, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                # Write header
                header = ["Date", "Day"]
                for team in teams:
                    header.extend(
                        [
                            f"{team['name']} Shift",
                            f"{team['name']} Person",
                            f"{team['name']} Sub",
                        ]
                    )
                writer.writerow(header)

                # Write data
                for row in self.schedule_data:
                    row_data = [row["date"], row["day_name"]]
                    for team in teams:
                        team_data = row["teams"].get(
                            team["id"],
                            {"shift": "OFF", "person": "", "is_sub": False},
                        )
                        row_data.extend(
                            [
                                team_data["shift"],
                                team_data["person"],
                                "Yes" if team_data["is_sub"] else "No",
                            ]
                        )
                    writer.writerow(row_data)

            messagebox.showinfo("Export Complete", f"Schedule exported to {filename}")
            self.status_var.set(f"Exported to {filename}")

        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export CSV: {str(e)}")

    def _on_person_selected(self, event=None):
        """Handle person selection in the combobox."""
        person_name = self.person_var.get()
        if person_name in getattr(self, "_person_map", {}):
            self.selected_person_id = self._person_map[person_name]
            self._on_view_person_schedule()

    def _on_view_person_schedule(self):
        """View the schedule for the selected person."""
        if not hasattr(self, "selected_person_id") or self.selected_person_id is None:
            self.person_schedule_text.delete("1.0", tk.END)
            self.person_schedule_text.insert(tk.END, "Please select a person")
            return

        try:
            initial_date = date.fromisoformat(self.initial_date_var.get())
            end_date = initial_date + timedelta(days=547)  # 18 months

            self._set_busy(True)
            self.status_var.set("Loading person schedule...")

            def load_person_schedule():
                return get_person_schedule(
                    self.selected_person_id, initial_date, end_date
                )

            def on_done(result):
                self.person_schedule_text.delete("1.0", tk.END)
                if not result:
                    self.person_schedule_text.insert(
                        tk.END,
                        "No schedule found for this person in the selected date range",
                    )
                else:
                    lines = []
                    for entry in result:
                        sub_text = " (Substitute)" if entry["is_substitute"] else ""
                        lines.append(
                            f"{entry['date']} ({entry['team']}): {entry['shift']}{sub_text}"
                        )
                        if entry["notes"]:
                            lines.append(f"  Notes: {entry['notes']}")
                    self.person_schedule_text.insert(tk.END, "\n".join(lines))
                self.status_var.set(
                    f"Loaded schedule for person ID {self.selected_person_id}"
                )
                self._set_busy(False)

            def on_error(exc):
                self.person_schedule_text.delete("1.0", tk.END)
                self.person_schedule_text.insert(
                    tk.END, f"Error loading schedule: {str(exc)}"
                )
                self.status_var.set(f"Error: {str(exc)}")
                messagebox.showerror("Error", str(exc))
                self._set_busy(False)

            self._run_in_background(load_person_schedule, on_done, on_error)

        except ValueError as e:
            messagebox.showerror("Invalid Date", f"Please enter valid dates: {str(e)}")

    # Team management handlers
    def _on_add_team(self):
        """Handle adding a new team."""
        dialog = TeamDialog(self.root, "Add Team")
        if dialog.result:
            name, color, initial_shift_offset = dialog.result
            try:
                team_id = create_team(name, color, initial_shift_offset)
                self._refresh_teams()
                self.status_var.set(f"Team '{name}' added successfully")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to add team: {str(e)}")

    def _on_edit_team(self):
        """Handle editing a team."""
        selection = self.teams_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a team to edit")
            return

        item = self.teams_tree.item(selection[0])
        team_id = item["values"][0]
        team = get_team(team_id)

        initial_shift_offset = (
            team["initial_shift_offset"] if "initial_shift_offset" in team.keys() else 0
        )
        dialog = TeamDialog(
            self.root, "Edit Team", team["name"], team["color"], initial_shift_offset
        )
        if dialog.result:
            name, color, initial_shift_offset = dialog.result
            try:
                update_team(team_id, name, color, initial_shift_offset)
                self._refresh_teams()
                self.status_var.set(f"Team '{name}' updated successfully")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to update team: {str(e)}")

    def _on_delete_team(self):
        """Handle deleting a team."""
        selection = self.teams_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a team to delete")
            return

        item = self.teams_tree.item(selection[0])
        team_id = item["values"][0]
        team_name = item["values"][1]

        result = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete team '{team_name}'?\n"
            f"This will also delete all team members and their assignments.",
        )

        if result:
            try:
                delete_team(team_id)
                self._refresh_teams()
                self._refresh_people()
                self.status_var.set(f"Team '{team_name}' deleted successfully")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete team: {str(e)}")

    # Team management handlers
    def _on_regenerate_teams(self):
        """Regenerate teams for the current rotation group based on shift model."""
        rotation = get_rotation_group()
        if not rotation:
            messagebox.showwarning(
                "No Rotation Group", "Please create a rotation group first"
            )
            return

        result = messagebox.askyesno(
            "Regenerate Teams",
            f"This will regenerate teams for the {rotation.shift_model} model:\n"
            f"• {SHIFT_MODELS[rotation.shift_model]['team_count']} teams will be created\n"
            f"• Existing teams will be deleted\n"
            f"• People assigned to teams will become unassigned\n\n"
            f"Continue?",
        )
        if not result:
            return

        try:
            self._set_busy(True)
            self.status_var.set("Regenerating teams...")

            def regenerate():
                return create_teams_for_rotation_group(rotation.id)

            def on_done(teams):
                self.status_var.set(f"Regenerated {len(teams)} teams")
                self._refresh_teams()
                self._refresh_people()
                self._refresh_exception_people()
                self._refresh_swap_people()
                self._set_busy(False)

            def on_error(exc):
                self.status_var.set(f"Error: {str(exc)}")
                messagebox.showerror("Error", str(exc))
                self._set_busy(False)

            self._run_in_background(regenerate, on_done, on_error)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to regenerate teams: {str(e)}")
            self._set_busy(False)

    # Person management handlers
    def _on_add_person(self):
        """Handle adding a new person (unassigned initially)."""
        dialog = PersonDialog(self.root, "Add Person")
        if dialog.result:
            name, telegram, email, role, team_id = dialog.result
            try:
                person_id = create_person_unassigned(name, role, telegram, email)
                if team_id:
                    assign_person_to_team(person_id, team_id)
                self._refresh_teams()
                self._refresh_people()
                self._refresh_exception_people()
                self._refresh_swap_people()
                team_name = get_team(team_id)["name"] if team_id else "Unassigned"
                self.status_var.set(f"Person '{name}' added to {team_name}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to add person: {str(e)}")

    def _on_edit_person(self):
        """Handle editing a person."""
        selection = self.people_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a person to edit")
            return

        item = self.people_tree.item(selection[0])
        person_id = item["values"][0]
        person = get_person(person_id)

        if not person:
            messagebox.showerror("Error", "Person not found")
            return

        dialog = PersonDialog(
            self.root,
            "Edit Person",
            person_id=person_id,
            name=person["name"],
            telegram=person.get("telegram_chat_id", ""),
            email=person.get("email", ""),
            role=person["role"],
            team_id=person.get("team_id"),
        )
        if dialog.result:
            name, telegram, email, role, team_id = dialog.result
            try:
                update_person(
                    person_id, name, team_id, role, person["active"], telegram, email
                )
                self._refresh_teams()
                self._refresh_people()
                self._refresh_exception_people()
                self._refresh_swap_people()
                self.status_var.set(f"Person '{name}' updated successfully")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to update person: {str(e)}")

    def _on_delete_person(self):
        """Handle deleting a person."""
        selection = self.people_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a person to delete")
            return

        item = self.people_tree.item(selection[0])
        person_id = item["values"][0]
        person_name = item["values"][1]

        result = messagebox.askyesno(
            "Confirm Delete", f"Are you sure you want to delete person '{person_name}'?"
        )

        if result:
            try:
                delete_person(person_id)
                self._refresh_teams()
                self._refresh_people()
                self._refresh_exception_people()
                self._refresh_swap_people()
                self.status_var.set(f"Person '{person_name}' deleted successfully")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete person: {str(e)}")

    def _on_toggle_person_active(self):
        """Toggle a person's active status."""
        selection = self.people_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a person")
            return

        item = self.people_tree.item(selection[0])
        person_id = item["values"][0]
        person = get_person(person_id)

        if not person:
            messagebox.showerror("Error", "Person not found")
            return

        new_status = 0 if person["active"] else 1
        status_text = "activated" if new_status == 1 else "deactivated"

        try:
            update_person(
                person_id,
                person["name"],
                person["team_id"],
                person["role"],
                new_status,
                person.get("telegram_chat_id", ""),
                person.get("email", ""),
            )
            self._refresh_teams()
            self._refresh_people()
            self._refresh_exception_people()
            self._refresh_swap_people()
            self.status_var.set(f"Person '{person['name']}' {status_text} successfully")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update person: {str(e)}")

    def _on_import_csv(self):
        """Import people from CSV file."""
        filename = filedialog.askopenfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Import People from CSV",
        )
        if not filename:
            return

        try:
            with open(filename, "r", encoding="utf-8") as f:
                csv_content = f.read()

            imported = import_people_from_csv(csv_content)
            self._refresh_teams()
            self._refresh_people()
            self._refresh_exception_people()
            self._refresh_swap_people()
            messagebox.showinfo("Import Complete", f"Imported {len(imported)} people")
            self.status_var.set(f"Imported {len(imported)} people from CSV")
        except Exception as e:
            messagebox.showerror("Import Error", f"Failed to import CSV: {str(e)}")

    def _on_generate_demo_people(self):
        """Generate demo people for testing."""
        result = messagebox.askyesno(
            "Generate Demo People",
            "This will generate 15 demo people with random names, roles, and contact info.\n"
            "They will be created as unassigned (no team).\n\nContinue?",
        )
        if not result:
            return

        try:
            self._set_busy(True)
            self.status_var.set("Generating demo people...")

            def generate():
                return generate_demo_people(15)

            def on_done(people):
                self._refresh_teams()
                self._refresh_people()
                self._refresh_exception_people()
                self._refresh_swap_people()
                self.status_var.set(f"Generated {len(people)} demo people")
                self._set_busy(False)
                messagebox.showinfo(
                    "Demo People Generated", f"Created {len(people)} demo people"
                )

            def on_error(exc):
                self.status_var.set(f"Error: {str(exc)}")
                messagebox.showerror("Error", str(exc))
                self._set_busy(False)

            self._run_in_background(generate, on_done, on_error)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate demo people: {str(e)}")
            self._set_busy(False)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate demo people: {str(e)}")
            self._set_busy(False)

    # Exception handlers
    def _get_current_exceptions_subtab(self) -> str:
        """Get the current exceptions sub-tab type."""
        if not hasattr(self, "exceptions_sub_notebook"):
            return "current"
        tab_id = self.exceptions_sub_notebook.select()
        if not tab_id:
            return "current"
        tab_text = self.exceptions_sub_notebook.tab(tab_id, "text")
        return tab_text.lower()

    def _get_exceptions_vars(self, subtab_type: str = None):
        """Get the exception variables for a specific sub-tab."""
        if subtab_type is None:
            subtab_type = self._get_current_exceptions_subtab()
        return {
            "person_var": getattr(self, f"exception_person_var_{subtab_type}", None),
            "person_combo": getattr(
                self, f"exception_person_combo_{subtab_type}", None
            ),
            "start_var": getattr(self, f"exception_start_var_{subtab_type}", None),
            "end_var": getattr(self, f"exception_end_var_{subtab_type}", None),
            "reason_var": getattr(self, f"exception_reason_var_{subtab_type}", None),
            "tree": getattr(self, f"exceptions_tree_{subtab_type}", None),
        }

    def _on_exception_person_selected(self, event=None):
        """Handle person selection for exceptions."""
        pass  # Will refresh when button clicked

    def _on_add_exception(self):
        """Handle adding an availability exception."""
        subtab_type = self._get_current_exceptions_subtab()
        vars = self._get_exceptions_vars(subtab_type)

        person_key = vars["person_var"].get() if vars["person_var"] else ""
        if not person_key:
            messagebox.showwarning("No Person Selected", "Please select a person")
            return

        if person_key not in getattr(self, "_exception_person_map", {}):
            messagebox.showerror("Invalid Selection", "Please select a valid person")
            return

        person_id = self._exception_person_map[person_key]

        try:
            start_var = vars["start_var"]
            end_var = vars["end_var"]
            reason_var = vars["reason_var"]

            if not start_var or not end_var or not reason_var:
                messagebox.showerror("Error", "Form not available for this sub-tab")
                return

            start_date = date.fromisoformat(start_var.get())
            end_date = date.fromisoformat(end_var.get())
            reason = reason_var.get()

            if start_date > end_date:
                messagebox.showerror(
                    "Invalid Date Range", "Start date must be before end date"
                )
                return

            exception_id = add_availability_exception(
                person_id, start_date, end_date, reason
            )
            self._refresh_exceptions()
            self.status_var.set(f"Availability exception added for {person_key}")

            # Clear form
            reason_var.set("")
            start_var.set(date.today().isoformat())
            end_var.set((date.today() + timedelta(days=7)).isoformat())

        except ValueError as e:
            messagebox.showerror("Invalid Date", f"Please enter valid dates: {str(e)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add exception: {str(e)}")

    def _on_delete_exception(self):
        """Handle deleting an availability exception."""
        subtab_type = self._get_current_exceptions_subtab()
        vars = self._get_exceptions_vars(subtab_type)
        tree = vars["tree"]

        if not tree:
            return

        selection = tree.selection()
        if not selection:
            messagebox.showwarning(
                "No Selection", "Please select an exception to delete"
            )
            return

        item = tree.item(selection[0])
        exception_id = item["values"][0]

        result = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete this availability exception?",
        )

        if result:
            try:
                delete_availability_exception(exception_id)
                self._refresh_exceptions()
                self.status_var.set("Availability exception deleted successfully")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete exception: {str(e)}")

    def _refresh_exceptions_for_person(self, subtab_type: str = None):
        """Refresh exceptions for the selected person."""
        if subtab_type is None:
            subtab_type = self._get_current_exceptions_subtab()
        self._refresh_exceptions(subtab_type)

    def _on_exceptions_subtab_changed(self, event=None):
        """Handle exceptions sub-tab change."""
        self._refresh_exceptions()

    # Swap handlers
    def _get_swaps_vars(self, subtab_type: str = None):
        """Get the swap variables for a specific sub-tab."""
        if subtab_type is None:
            subtab_type = self._get_current_swaps_subtab()
        return {
            "date_var": getattr(self, f"swap_date_var_{subtab_type}", None),
            "person_a_var": getattr(self, f"swap_person_a_var_{subtab_type}", None),
            "person_a_combo": getattr(self, f"swap_person_a_combo_{subtab_type}", None),
            "shift_a_var": getattr(self, f"swap_shift_a_var_{subtab_type}", None),
            "shift_a_combo": getattr(self, f"swap_shift_a_combo_{subtab_type}", None),
            "person_b_var": getattr(self, f"swap_person_b_var_{subtab_type}", None),
            "person_b_combo": getattr(self, f"swap_person_b_combo_{subtab_type}", None),
            "shift_b_var": getattr(self, f"swap_shift_b_var_{subtab_type}", None),
            "shift_b_combo": getattr(self, f"swap_shift_b_combo_{subtab_type}", None),
            "tree": getattr(self, f"swaps_tree_{subtab_type}", None),
        }

    def _on_add_swap(self):
        """Handle adding a shift swap."""
        subtab_type = self._get_current_swaps_subtab()
        vars = self._get_swaps_vars(subtab_type)

        try:
            date_var = vars["date_var"]
            person_a_var = vars["person_a_var"]
            person_b_var = vars["person_b_var"]
            shift_a_var = vars["shift_a_var"]
            shift_b_var = vars["shift_b_var"]

            if not all(
                [date_var, person_a_var, person_b_var, shift_a_var, shift_b_var]
            ):
                messagebox.showerror("Error", "Form not available for this sub-tab")
                return

            swap_date = date.fromisoformat(date_var.get())
            person_a_name = person_a_var.get()
            person_b_name = person_b_var.get()
            shift_a = int(shift_a_var.get())
            shift_b = int(shift_b_var.get())

            if not person_a_name or not person_b_name:
                messagebox.showwarning(
                    "No Persons Selected", "Please select both persons"
                )
                return

            if person_a_name == person_b_name:
                messagebox.showerror(
                    "Same Person", "Please select two different persons"
                )
                return

            if person_a_name not in getattr(
                self, "_swap_person_map", {}
            ) or person_b_name not in getattr(self, "_swap_person_map", {}):
                messagebox.showerror("Invalid Selection", "Please select valid persons")
                return

            person_a_id = self._swap_person_map[person_a_name]
            person_b_id = self._swap_person_map[person_b_name]

            swap_id = add_shift_swap(
                swap_date, person_a_id, person_b_id, shift_a, shift_b
            )
            self._refresh_swaps()
            self.status_var.set(f"Shift swap added for {swap_date}")

        except ValueError as e:
            messagebox.showerror(
                "Invalid Input", f"Please enter valid values: {str(e)}"
            )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add swap: {str(e)}")

    def _on_delete_swap(self):
        """Handle deleting a shift swap."""
        subtab_type = self._get_current_swaps_subtab()
        vars = self._get_swaps_vars(subtab_type)
        tree = vars["tree"]

        if not tree:
            return

        selection = tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a swap to delete")
            return

        item = tree.item(selection[0])
        swap_id = item["values"][0]

        result = messagebox.askyesno(
            "Confirm Delete", f"Are you sure you want to delete this shift swap?"
        )

        if result:
            try:
                delete_shift_swap(swap_id)
                self._refresh_swaps()
                self.status_var.set("Shift swap deleted successfully")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete swap: {str(e)}")


class TeamDialog:
    def __init__(self, parent, title, name="", color="#2563eb", initial_shift_offset=0):
        self.result = None

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("350x220")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Center dialog
        self.dialog.geometry(
            "+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50)
        )

        # Name
        ttk.Label(self.dialog, text="Team Name:").pack(pady=(10, 0))
        self.name_var = tk.StringVar(value=name)
        ttk.Entry(self.dialog, textvariable=self.name_var, width=30).pack(pady=(0, 10))

        # Color
        ttk.Label(self.dialog, text="Color (hex):").pack(pady=(0, 0))
        self.color_var = tk.StringVar(value=color)
        ttk.Entry(self.dialog, textvariable=self.color_var, width=10).pack(pady=(0, 10))

        # Initial shift offset
        ttk.Label(self.dialog, text="Initial Shift Offset (days):").pack(pady=(0, 0))
        self.offset_var = tk.StringVar(value=str(initial_shift_offset))
        offset_frame = ttk.Frame(self.dialog)
        offset_frame.pack(pady=(0, 10))
        ttk.Entry(offset_frame, textvariable=self.offset_var, width=5).pack(side="left")
        ttk.Label(
            offset_frame, text="(0=1st shift start, 2=2nd shift start, 4=off start)"
        ).pack(side="left", padx=(8, 0))

        # Buttons
        btn_frame = ttk.Frame(self.dialog)
        btn_frame.pack(pady=10, side="bottom", fill="x")
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        ttk.Button(btn_frame, text="OK", command=self._on_ok).grid(
            row=0, column=0, padx=5
        )
        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel).grid(
            row=0, column=1, padx=5
        )

        # Wait for dialog to close
        self.dialog.wait_window()

    def _on_ok(self):
        name = self.name_var.get().strip()
        color = self.color_var.get().strip()

        if not name:
            messagebox.showerror("Validation Error", "Team name cannot be empty")
            return

        if not color.startswith("#") or len(color) != 7:
            messagebox.showerror(
                "Validation Error", "Color must be in hex format (e.g., #2563eb)"
            )
            return

        self.result = (name, color)
        self.dialog.destroy()

    def _on_cancel(self):
        self.dialog.destroy()


class PersonDialog:
    def __init__(
        self,
        parent,
        title,
        person_id=None,
        name="",
        telegram="",
        email="",
        role="operator",
        team_id=None,
    ):
        self.result = None
        self.person_id = person_id

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("400x400")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Center dialog
        self.dialog.geometry(
            "+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50)
        )

        # Get teams for dropdown
        teams = get_teams()
        team_options = ["Unassigned"] + [t["name"] for t in teams]
        team_map = {t["name"]: t["id"] for t in teams}
        reverse_team_map = {t["id"]: t["name"] for t in teams}

        # Name
        ttk.Label(self.dialog, text="Person Name:").pack(pady=(10, 0))
        self.name_var = tk.StringVar(value=name)
        ttk.Entry(self.dialog, textvariable=self.name_var, width=35).pack(pady=(0, 8))

        # Telegram
        ttk.Label(self.dialog, text="Telegram Chat ID:").pack(pady=(0, 0))
        self.telegram_var = tk.StringVar(value=telegram)
        ttk.Entry(self.dialog, textvariable=self.telegram_var, width=35).pack(
            pady=(0, 8)
        )

        # Email
        ttk.Label(self.dialog, text="Email:").pack(pady=(0, 0))
        self.email_var = tk.StringVar(value=email)
        ttk.Entry(self.dialog, textvariable=self.email_var, width=35).pack(pady=(0, 8))

        # Role
        ttk.Label(self.dialog, text="Role:").pack(pady=(0, 0))
        self.role_var = tk.StringVar(value=role)
        ttk.Entry(self.dialog, textvariable=self.role_var, width=35).pack(pady=(0, 8))

        # Team dropdown
        ttk.Label(self.dialog, text="Team:").pack(pady=(0, 0))
        self.team_var = tk.StringVar()
        current_team = (
            reverse_team_map.get(team_id, "Unassigned") if team_id else "Unassigned"
        )
        self.team_var.set(current_team)
        team_combo = ttk.Combobox(
            self.dialog,
            textvariable=self.team_var,
            values=team_options,
            state="readonly",
            width=32,
        )
        team_combo.pack(pady=(0, 10))

        # Buttons
        btn_frame = ttk.Frame(self.dialog)
        btn_frame.pack(pady=10, side="bottom", fill="x")
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        ttk.Button(btn_frame, text="OK", command=self._on_ok).grid(
            row=0, column=0, padx=5
        )
        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel).grid(
            row=0, column=1, padx=5
        )

        # Wait for dialog to close
        self.dialog.wait_window()

    def _on_ok(self):
        name = self.name_var.get().strip()
        telegram = self.telegram_var.get().strip() or None
        email = self.email_var.get().strip() or None
        role = self.role_var.get().strip()
        team_name = self.team_var.get()

        if not name:
            messagebox.showerror("Validation Error", "Person name cannot be empty")
            return

        if not role:
            role = "operator"

        # Get team_id from team_name
        teams = get_teams()
        team_map = {t["name"]: t["id"] for t in teams}
        team_id = team_map.get(team_name) if team_name != "Unassigned" else None

        self.result = (name, telegram, email, role, team_id)
        self.dialog.destroy()

    def _on_cancel(self):
        self.dialog.destroy()


def main():
    root = tk.Tk()
    app = ShiftSchedulerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
