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
from typing import Optional, Dict, List

# Import our modules
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))  # project root for shiftcore
sys.path.insert(0, str(Path(__file__).parent))  # src directory for adapter

# Use shiftcore adapter instead of legacy db.py/scheduler.py
from shiftcore_adapter import *
from shiftcore_adapter import _to_dict
from shiftcore import SHIFT_MODELS


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

        # Load initial data
        self._on_load_notification_settings()
        self._refresh_all()

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

        # Named fonts for consistent usage
        self.fUI = (self.sans_font, 10)  # Base UI font
        self.fUIBold = (self.sans_font, 10, "bold")  # Bold UI font
        self.fSmall = (self.sans_font, 9)  # Small headers (Use, Action, Weight, etc.)
        self.fMono = (self.mono_font, 10)  # Monospace for code/markdown

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

        # Schedule tab
        self.schedule_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.schedule_tab, text="Schedule View")
        self._build_schedule_tab()

        # Teams tab
        self.teams_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.teams_tab, text="Teams & People")
        self._build_teams_tab()

        # Exceptions tab
        self.exceptions_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.exceptions_tab, text="Availability")
        self._build_exceptions_tab()

        # Swaps tab
        self.swaps_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.swaps_tab, text="Shift Swaps")
        self._build_swaps_tab()

        # Notifications tab
        self.notifications_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.notifications_tab, text="Notifications")
        self._build_notifications_tab()

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
        """Build the schedule viewing tab."""
        # Main paned window
        paned = ttk.PanedWindow(self.schedule_tab, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        # Left panel - Schedule grid
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=2)

        # Schedule controls
        controls_frame = ttk.LabelFrame(left_frame, text="Schedule Controls")
        controls_frame.pack(fill="x", pady=(0, 8))

        # Initial date and model selection
        date_frame = ttk.Frame(controls_frame)
        date_frame.pack(fill="x", padx=8, pady=8)

        ttk.Label(date_frame, text="Initial Date (Cycle Start):").grid(
            row=0, column=0, sticky="w", padx=(0, 4)
        )
        self.initial_date_var = tk.StringVar(value=date.today().isoformat())
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

        # Schedule grid
        grid_frame = ttk.LabelFrame(left_frame, text="Schedule Grid (18 months)")
        grid_frame.pack(fill="both", expand=True, pady=(0, 8))

        # Create treeview for schedule (dynamic columns based on teams)
        self.schedule_tree = ttk.Treeview(
            grid_frame, columns=("date", "day"), show="headings", height=25
        )

        # Define base headings (will add team columns dynamically)
        self.schedule_tree.heading("date", text="Date")
        self.schedule_tree.heading("day", text="Day")

        # Define base column widths
        self.schedule_tree.column("date", width=100)
        self.schedule_tree.column("day", width=100)

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

        # Right panel - Details and actions
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)

        # Selected date details
        details_frame = ttk.LabelFrame(right_frame, text="Date Details")
        details_frame.pack(fill="x", pady=(0, 8))

        self.date_details_text = tk.Text(
            details_frame, height=8, wrap="word", font=(self.mono_font, 9)
        )
        self.date_details_text.pack(fill="both", expand=True, padx=4, pady=4)

        # Person details
        person_frame = ttk.LabelFrame(right_frame, text="Person Details")
        person_frame.pack(fill="both", expand=True, pady=(0, 8))

        # Person selection
        person_select_frame = ttk.Frame(person_frame)
        person_select_frame.pack(fill="x", padx=4, pady=4)

        ttk.Label(person_select_frame, text="Person:").pack(side="left")
        self.person_var = tk.StringVar()
        self.person_combo = ttk.Combobox(
            person_select_frame,
            textvariable=self.person_var,
            state="readonly",
            width=20,
        )
        self.person_combo.pack(side="left", padx=(4, 0))
        self.person_combo.bind("<<ComboboxSelected>>", self._on_person_selected)

        ttk.Button(
            person_select_frame,
            text="View Schedule",
            command=self._on_view_person_schedule,
        ).pack(side="left", padx=(4, 0))

        # Person schedule text
        self.person_schedule_text = tk.Text(
            person_frame, height=10, wrap="word", font=(self.mono_font, 9)
        )
        self.person_schedule_text.pack(fill="both", expand=True, padx=4, pady=4)

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
        """Build the availability exceptions tab."""
        # Main frame
        main_frame = ttk.Frame(self.exceptions_tab)
        main_frame.pack(fill="both", expand=True, padx=8, pady=8)

        # Controls
        controls_frame = ttk.LabelFrame(main_frame, text="Availability Exceptions")
        controls_frame.pack(fill="both", expand=True, pady=(0, 8))

        # Person selection
        person_frame = ttk.Frame(controls_frame)
        person_frame.pack(fill="x", padx=8, pady=8)

        ttk.Label(person_frame, text="Person:").pack(side="left")
        self.exception_person_var = tk.StringVar()
        self.exception_person_combo = ttk.Combobox(
            person_frame,
            textvariable=self.exception_person_var,
            state="readonly",
            width=25,
        )
        self.exception_person_combo.pack(side="left", padx=(4, 0))
        self.exception_person_combo.bind(
            "<<ComboboxSelected>>", self._on_exception_person_selected
        )

        ttk.Button(
            person_frame, text="Refresh", command=self._refresh_exceptions_for_person
        ).pack(side="left", padx=(4, 0))

        # Date range for exception
        date_frame = ttk.Frame(controls_frame)
        date_frame.pack(fill="x", padx=8, pady=4)

        ttk.Label(date_frame, text="Start Date:").grid(
            row=0, column=0, sticky="w", padx=(0, 4)
        )
        self.exception_start_var = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(date_frame, textvariable=self.exception_start_var, width=12).grid(
            row=0, column=1, padx=(0, 16)
        )

        ttk.Label(date_frame, text="End Date:").grid(
            row=0, column=2, sticky="w", padx=(0, 4)
        )
        self.exception_end_var = tk.StringVar(
            value=(date.today() + timedelta(days=7)).isoformat()
        )
        ttk.Entry(date_frame, textvariable=self.exception_end_var, width=12).grid(
            row=0, column=3, padx=(0, 16)
        )

        ttk.Label(date_frame, text="Reason:").grid(
            row=0, column=4, sticky="w", padx=(0, 4)
        )
        self.exception_reason_var = tk.StringVar()
        ttk.Entry(date_frame, textvariable=self.exception_reason_var, width=20).grid(
            row=0, column=5
        )

        ttk.Button(
            date_frame, text="Add Exception", command=self._on_add_exception
        ).grid(row=0, column=6, padx=(16, 0))
        ttk.Button(
            date_frame, text="Delete Selected", command=self._on_delete_exception
        ).grid(row=0, column=7)

        # Exceptions list
        exceptions_frame = ttk.LabelFrame(controls_frame, text="Exceptions List")
        exceptions_frame.pack(fill="both", expand=True, pady=(8, 0))

        columns = ("id", "person", "start_date", "end_date", "reason")
        self.exceptions_tree = ttk.Treeview(
            exceptions_frame, columns=columns, show="headings", height=12
        )
        self.exceptions_tree.heading("id", text="ID")
        self.exceptions_tree.heading("person", text="Person")
        self.exceptions_tree.heading("start_date", text="Start Date")
        self.exceptions_tree.heading("end_date", text="End Date")
        self.exceptions_tree.heading("reason", text="Reason")
        self.exceptions_tree.column("id", width=50)
        self.exceptions_tree.column("person", width=150)
        self.exceptions_tree.column("start_date", width=100)
        self.exceptions_tree.column("end_date", width=100)
        self.exceptions_tree.column("reason", width=200)

        exc_v_scroll = ttk.Scrollbar(
            exceptions_frame, orient="vertical", command=self.exceptions_tree.yview
        )
        exc_h_scroll = ttk.Scrollbar(
            exceptions_frame, orient="horizontal", command=self.exceptions_tree.xview
        )
        self.exceptions_tree.configure(
            yscrollcommand=exc_v_scroll.set, xscrollcommand=exc_h_scroll.set
        )
        self.exceptions_tree.grid(row=0, column=0, sticky="nsew")
        exc_v_scroll.grid(row=0, column=1, sticky="ns")
        exc_h_scroll.grid(row=1, column=0, sticky="ew")

        exceptions_frame.grid_rowconfigure(0, weight=1)
        exceptions_frame.grid_columnconfigure(0, weight=1)

    def _build_swaps_tab(self):
        """Build the shift swaps tab."""
        # Main frame
        main_frame = ttk.Frame(self.swaps_tab)
        main_frame.pack(fill="both", expand=True, padx=8, pady=8)

        # Controls
        controls_frame = ttk.LabelFrame(main_frame, text="Shift Swaps")
        controls_frame.pack(fill="both", expand=True, pady=(0, 8))

        # Date selection
        date_frame = ttk.Frame(controls_frame)
        date_frame.pack(fill="x", padx=8, pady=8)

        ttk.Label(date_frame, text="Date:").grid(
            row=0, column=0, sticky="w", padx=(0, 4)
        )
        self.swap_date_var = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(date_frame, textvariable=self.swap_date_var, width=12).grid(
            row=0, column=1, padx=(0, 16)
        )

        # Person A selection
        ttk.Label(date_frame, text="Person A:").grid(
            row=0, column=2, sticky="w", padx=(0, 4)
        )
        self.swap_person_a_var = tk.StringVar()
        self.swap_person_a_combo = ttk.Combobox(
            date_frame, textvariable=self.swap_person_a_var, state="readonly", width=15
        )
        self.swap_person_a_combo.grid(row=0, column=3, padx=(0, 8))

        ttk.Label(date_frame, text="Shift:").grid(
            row=0, column=4, sticky="w", padx=(0, 4)
        )
        self.swap_shift_a_var = tk.StringVar(value="1")
        self.swap_shift_a_combo = ttk.Combobox(
            date_frame,
            textvariable=self.swap_shift_a_var,
            values=["1", "2", "3"],
            state="readonly",
            width=5,
        )
        self.swap_shift_a_combo.grid(row=0, column=5)

        # Person B selection
        ttk.Label(date_frame, text="Person B:").grid(
            row=0, column=6, sticky="w", padx=(0, 4)
        )
        self.swap_person_b_var = tk.StringVar()
        self.swap_person_b_combo = ttk.Combobox(
            date_frame, textvariable=self.swap_person_b_var, state="readonly", width=15
        )
        self.swap_person_b_combo.grid(row=0, column=7, padx=(0, 8))

        ttk.Label(date_frame, text="Shift:").grid(
            row=0, column=8, sticky="w", padx=(0, 4)
        )
        self.swap_shift_b_var = tk.StringVar(value="2")
        self.swap_shift_b_combo = ttk.Combobox(
            date_frame,
            textvariable=self.swap_shift_b_var,
            values=["1", "2", "3"],
            state="readonly",
            width=5,
        )
        self.swap_shift_b_combo.grid(row=0, column=9)

        ttk.Button(date_frame, text="Add Swap", command=self._on_add_swap).grid(
            row=0, column=10, padx=(16, 0)
        )
        ttk.Button(
            date_frame, text="Delete Selected", command=self._on_delete_swap
        ).grid(row=0, column=11)

        # Swaps list
        swaps_frame = ttk.LabelFrame(controls_frame, text="Swaps List")
        swaps_frame.pack(fill="both", expand=True, pady=(8, 0))

        columns = ("id", "date", "person_a", "shift_a", "person_b", "shift_b")
        self.swaps_tree = ttk.Treeview(
            swaps_frame, columns=columns, show="headings", height=12
        )
        self.swaps_tree.heading("id", text="ID")
        self.swaps_tree.heading("date", text="Date")
        self.swaps_tree.heading("person_a", text="Person A")
        self.swaps_tree.heading("shift_a", text="Shift A")
        self.swaps_tree.heading("person_b", text="Person B")
        self.swaps_tree.heading("shift_b", text="Shift B")
        self.swaps_tree.column("id", width=50)
        self.swaps_tree.column("date", width=100)
        self.swaps_tree.column("person_a", width=150)
        self.swaps_tree.column("shift_a", width=60)
        self.swaps_tree.column("person_b", width=150)
        self.swaps_tree.column("shift_b", width=60)

        swap_v_scroll = ttk.Scrollbar(
            swaps_frame, orient="vertical", command=self.swaps_tree.yview
        )
        swap_h_scroll = ttk.Scrollbar(
            swaps_frame, orient="horizontal", command=self.swaps_tree.xview
        )
        self.swaps_tree.configure(
            yscrollcommand=swap_v_scroll.set, xscrollcommand=swap_h_scroll.set
        )
        self.swaps_tree.grid(row=0, column=0, sticky="nsew")
        swap_v_scroll.grid(row=0, column=1, sticky="ns")
        swap_h_scroll.grid(row=1, column=0, sticky="ew")

        swaps_frame.grid_rowconfigure(0, weight=1)
        swaps_frame.grid_columnconfigure(0, weight=1)

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
        """Refresh the person combobox for exceptions."""
        people = get_people(active_only=False)
        teams = get_teams()
        team_map = {t["id"]: t["name"] for t in teams}

        person_names = []
        for p in people:
            team_id = p.get("team_id")
            team_name = team_map.get(team_id, "Unassigned") if team_id else "Unassigned"
            person_names.append(f"{p['name']} (Team: {team_name})")

        self.exception_person_combo["values"] = person_names
        # Store mapping for lookup
        self._exception_person_map = {
            f"{p['name']} (Team: {team_map.get(p.get('team_id'), 'Unassigned') if p.get('team_id') else 'Unassigned'})": p[
                "id"
            ]
            for p in people
        }

    def _refresh_swap_people(self):
        """Refresh the person comboboxes for swaps."""
        people = get_people(active_only=False)
        person_names = [p["name"] for p in people]
        self.swap_person_a_combo["values"] = person_names
        self.swap_person_b_combo["values"] = person_names
        # Store mapping for lookup
        self._swap_person_map = {p["name"]: p["id"] for p in people}

        # Update shift combo boxes based on current model
        model = self.shift_model.get()
        if model == "2-shift":
            shift_values = ["1", "2"]
        else:
            shift_values = ["1", "2", "3"]
        self.swap_shift_a_combo["values"] = shift_values
        self.swap_shift_b_combo["values"] = shift_values
        # Reset to first valid value
        if shift_values:
            self.swap_shift_a_var.set(shift_values[0])
            self.swap_shift_b_var.set(
                shift_values[1] if len(shift_values) > 1 else shift_values[0]
            )

    def _refresh_exceptions(self):
        """Refresh the exceptions treeview."""
        for item in self.exceptions_tree.get_children():
            self.exceptions_tree.delete(item)

        exceptions = get_availability_exceptions()
        for exc in exceptions:
            person = get_person(exc["person_id"])
            person_name = person["name"] if person else "Unknown"
            self.exceptions_tree.insert(
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

    def _refresh_swaps(self):
        """Refresh the swaps treeview."""
        for item in self.swaps_tree.get_children():
            self.swaps_tree.delete(item)

        swaps = get_shift_swaps(
            date.today() - timedelta(days=30), date.today() + timedelta(days=30)
        )
        for swap in swaps:
            self.swaps_tree.insert(
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
                self._refresh_manual_config()  # Refresh manual config UI
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

    def _on_manual_config_change(self, team_id: int, day_offset: int):
        """Handle manual configuration change."""
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

            # Reload schedule to reflect changes
            self._on_load_schedule()

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
            self.schedule_tree.column(col_name, width=200)

        # Set base column widths
        self.schedule_tree.column("date", width=100)
        self.schedule_tree.column("day", width=100)

    def _populate_schedule_tree(self):
        """Populate the schedule treeview with schedule data."""
        for item in self.schedule_tree.get_children():
            self.schedule_tree.delete(item)

        teams = get_teams()

        for row in self.schedule_data:
            # Format team data dynamically
            values = [row["date"], row["day_name"]]

            for team in teams:
                team_data = row["teams"].get(
                    team["id"],
                    {"shift": "OFF", "person": "UNASSIGNED", "is_sub": False},
                )

                # Format team display
                if team_data["shift"] == "OFF":
                    values.append("OFF")
                else:
                    person = team_data["person"]
                    if team_data["is_sub"]:
                        person += " (S)"
                    values.append(f"{team_data['shift']}: {person}")

            self.schedule_tree.insert("", "end", values=values)

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

            def generate_schedule():
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

            self._run_in_background(generate_schedule, on_done, on_error)

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
    def _on_exception_person_selected(self, event=None):
        """Handle person selection for exceptions."""
        pass  # Will refresh when button clicked

    def _on_add_exception(self):
        """Handle adding an availability exception."""
        person_key = self.exception_person_var.get()
        if not person_key:
            messagebox.showwarning("No Person Selected", "Please select a person")
            return

        if person_key not in getattr(self, "_exception_person_map", {}):
            messagebox.showerror("Invalid Selection", "Please select a valid person")
            return

        person_id = self._exception_person_map[person_key]

        try:
            start_date = date.fromisoformat(self.exception_start_var.get())
            end_date = date.fromisoformat(self.exception_end_var.get())
            reason = self.exception_reason_var.get()

            if start_date > end_date:
                messagebox.showerror(
                    "Invalid Date Range", "Start date must be before end date"
                )
                return

            exception_id = add_availability_exception(
                person_id, start_date, end_date, reason
            )
            self._refresh_exceptions()
            self.status_var.set(
                f"Availability exception added for {self.exception_person_var.get()}"
            )

            # Clear form
            self.exception_reason_var.set("")
            self.exception_start_var.set(date.today().isoformat())
            self.exception_end_var.set((date.today() + timedelta(days=7)).isoformat())

        except ValueError as e:
            messagebox.showerror("Invalid Date", f"Please enter valid dates: {str(e)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add exception: {str(e)}")

    def _on_delete_exception(self):
        """Handle deleting an availability exception."""
        selection = self.exceptions_tree.selection()
        if not selection:
            messagebox.showwarning(
                "No Selection", "Please select an exception to delete"
            )
            return

        item = self.exceptions_tree.item(selection[0])
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

    def _refresh_exceptions_for_person(self):
        """Refresh exceptions for the selected person."""
        person_key = self.exception_person_var.get()
        if person_key and person_key in getattr(self, "_exception_person_map", {}):
            self._refresh_exceptions()

    # Swap handlers
    def _on_add_swap(self):
        """Handle adding a shift swap."""
        try:
            swap_date = date.fromisoformat(self.swap_date_var.get())
            person_a_name = self.swap_person_a_var.get()
            person_b_name = self.swap_person_b_var.get()
            shift_a = int(self.swap_shift_a_var.get())
            shift_b = int(self.swap_shift_b_var.get())

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
        selection = self.swaps_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a swap to delete")
            return

        item = self.swaps_tree.item(selection[0])
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
