"""Tkinter front end for the mission generator.

Launch with:  dcsgen-gui   or   python -m dcsgen gui

All decisions about which options are valid live in gui_logic.py. This file only
draws the form, reads it into a FormState, and shows results.
"""

import random
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import __version__
from .briefing import compose
from .catalog import AIRCRAFT
from .eras import ERAS
from . import theme, ownership
from .conditions import DEFENCES_LABEL, defences_labels, SEASON_LABEL, TIME_LABEL, WEATHER_LABEL
from .gui_logic import (MISSION_LABEL, enemy_country_options, player_country_options, POSTURE_LABEL, SIDE_LABEL, START_KIND_LABEL, START_STATE_LABEL,
                        FormState, aircraft_for,
                        carriers_for, default_filename, default_output_dir, explain_import_error,
                        missions_for, repair,
                        start_kinds_for_mission, to_request, unit_summary)
from .maps import MAPS
from .planner import generate_plan


def _invert(d):
    return {v: k for k, v in d.items()}


class App:
    def __init__(self, root):
        self.root = root
        root.title(f"DCS Strike Package {__version__}")
        root.minsize(1280, 720)
        self.palette = theme.apply(root)
        self._busy = False
        self._airbase_cache = {}
        self._to_key = {}          # field -> {display text: key}
        self._tab_widgets = []
        self._maps = None          # map keys pydcs offers (None = not known yet)
        self.last_plan = None
        self.last_brief = None

        self.vars = {name: tk.StringVar() for name in
                     ("side", "era", "map", "mission", "aircraft", "posture", "start_kind", "start",
                      "start_state", "time_of_day", "season", "weather", "defences",
                      "player_country", "enemy_country",
                      "flights", "flight_size", "ground_units", "frontline_units", "statics", "max_units",
                      "seed")}
        self.opt_all = tk.BooleanVar(value=False)
        self.opt_awacs = tk.BooleanVar(value=True)
        self.opt_tanker = tk.BooleanVar(value=False)
        self.opt_kneeboard = tk.BooleanVar(value=True)
        self.opt_pdf = tk.BooleanVar(value=True)

        filtering, found = ownership.startup()
        self.opt_installed = tk.BooleanVar(value=ownership.load_choice() is not False)
        self._build_widgets()
        self.write_state(FormState(seed=random.randint(0, 999999)))
        self.on_change()
        if filtering:
            self.status.set(f"Showing the {found} aircraft found in your DCS install "
                            "(untick 'Only aircraft installed in my DCS' to see all).")

    # ---- layout -------------------------------------------------------------

    def _build_widgets(self):
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(2, weight=1)
        outer.rowconfigure(0, weight=1)

        col1 = ttk.Frame(outer)
        col1.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        col2 = ttk.Frame(outer)
        col2.grid(row=0, column=1, sticky="ns", padx=(0, 10))

        def frame(parent, title):
            f = ttk.LabelFrame(parent, text=title, padding=8)
            f.pack(fill="x", pady=(0, 8))
            return f

        def combo(parent, row, label, field, readonly=True, width=30):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
            cb = ttk.Combobox(parent, textvariable=self.vars[field], width=width,
                               state="readonly" if readonly else "normal")
            cb.grid(row=row, column=1, sticky="ew", pady=3, padx=(8, 0))
            cb.bind("<<ComboboxSelected>>", self.on_change)
            return cb

        def spin(parent, row, label, field, lo, hi, step=1):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
            sp = ttk.Spinbox(parent, from_=lo, to=hi, increment=step, width=8,
                              textvariable=self.vars[field], command=self.on_change)
            sp.grid(row=row, column=1, sticky="w", pady=3, padx=(8, 0))
            sp.bind("<FocusOut>", self.on_change)
            sp.bind("<Return>", self.on_change)
            return sp

        f_mission = frame(col1, "Mission")
        self.cb_side = combo(f_mission, 0, "Side", "side")
        self.cb_era = combo(f_mission, 1, "Era", "era")
        self.cb_map = combo(f_mission, 2, "Map", "map")
        self.cb_mission = combo(f_mission, 3, "Mission type", "mission")
        self.cb_aircraft = combo(f_mission, 4, "Aircraft", "aircraft")
        ttk.Checkbutton(f_mission, text="All aircraft for my side (not only historical)",
                        variable=self.opt_all, command=self.on_change).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(0, 3))
        self.cb_posture = combo(f_mission, 6, "Posture", "posture")
        self.cb_defences = combo(f_mission, 7, "Enemy defences", "defences")
        self.cb_pcountry = combo(f_mission, 8, "My country", "player_country")
        self.cb_ecountry = combo(f_mission, 9, "Enemy country", "enemy_country")
        ttk.Checkbutton(f_mission, text="AWACS (if one existed then)", variable=self.opt_awacs,
                        command=self.on_change).grid(row=10, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(f_mission, text="Tanker matched to my aircraft", variable=self.opt_tanker,
                        command=self.on_change).grid(row=11, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(f_mission, text="Only aircraft installed in my DCS", variable=self.opt_installed,
                        command=self.on_installed_toggle).grid(row=12, column=0, columnspan=2, sticky="w")

        f_start = frame(col1, "Start")
        self.cb_kind = combo(f_start, 0, "Start type", "start_kind")
        self.cb_start = combo(f_start, 1, "Start location", "start", readonly=False)
        ttk.Label(f_start, text="Suggested", style="Dim.TLabel").grid(row=2, column=0, sticky="w")
        self.suggest_row = ttk.Frame(f_start)
        self.suggest_row.grid(row=2, column=1, sticky="w", padx=(8, 0), pady=3)
        self.suggest_buttons = []
        for _ in range(3):
            b = ttk.Button(self.suggest_row, text="-", width=16)
            b.pack(side="left", padx=(0, 4))
            self.suggest_buttons.append(b)
        self.cb_state = combo(f_start, 3, "Start state", "start_state")

        f_cond = frame(col2, "Conditions")
        self.cb_time = combo(f_cond, 0, "Time of day", "time_of_day")
        self.cb_season = combo(f_cond, 1, "Season", "season")
        self.cb_weather = combo(f_cond, 2, "Weather", "weather")

        f_size = frame(col2, "Size")
        spin(f_size, 0, "Flights in package (1-3)", "flights", 1, 3)
        spin(f_size, 1, "Aircraft in your flight (1-4)", "flight_size", 1, 4)
        spin(f_size, 2, "Active ground units (60-100)", "ground_units", 60, 100, 5)
        spin(f_size, 3, "Frontline units (0-160, active war)", "frontline_units", 0, 160, 10)
        spin(f_size, 4, "Static objects (20-50)", "statics", 20, 50, 5)
        spin(f_size, 5, "Unit limit", "max_units", 20, 400, 10)
        ttk.Label(f_size, text="Seed").grid(row=6, column=0, sticky="w", pady=3)
        seed_row = ttk.Frame(f_size)
        seed_row.grid(row=6, column=1, sticky="w", pady=3, padx=(8, 0))
        ttk.Entry(seed_row, textvariable=self.vars["seed"], width=10).pack(side="left")
        ttk.Button(seed_row, text="New seed", command=self.new_seed).pack(side="left", padx=6)

        f_out = frame(col2, "Output")
        ttk.Checkbutton(f_out, text="Put briefing on the in-game kneeboard",
                        variable=self.opt_kneeboard).pack(anchor="w")
        ttk.Checkbutton(f_out, text="Also save a PDF next to the .miz",
                        variable=self.opt_pdf).pack(anchor="w")
        ttk.Button(f_out, text="Preview briefing", command=self.preview).pack(fill="x", pady=(8, 2))
        ttk.Button(f_out, text="Generate .miz...", style="Accent.TButton",
                   command=self.generate).pack(fill="x", pady=2)
        ttk.Button(f_out, text="Export briefing PDF...", command=self.export_pdf).pack(fill="x", pady=2)
        ttk.Button(f_out, text="Export kneeboard PNGs...", command=self.export_pngs).pack(fill="x", pady=2)

        right = ttk.LabelFrame(outer, text="Briefing", padding=6)
        right.grid(row=0, column=2, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        self.notebook = ttk.Notebook(right)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self._show_tabs([("Overview", "Press 'Preview briefing' to see the briefing.\n"
                                       "There is one tab for the overview, one for the target photos "
                                       "and one for each flight.")])

        self.status = tk.StringVar(value="")
        ttk.Label(outer, textvariable=self.status, wraplength=1200, justify="left",
                  style="Dim.TLabel").grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))

    # ---- aircraft found in the user's DCS install ----------------------------

    def on_installed_toggle(self):
        ownership.save_choice(self.opt_installed.get())
        n = ownership.apply(self.opt_installed.get())
        self.on_change()
        if self.opt_installed.get() and n is None:
            self.status.set("DCS was not found, so every aircraft is offered.  " + self.status.get())
        elif n is not None:
            self.status.set(f"Showing the {n} aircraft found in your DCS install.  " + self.status.get())

    # ---- reading and writing the form ----------------------------------------

    def _key(self, field, fallback):
        return self._to_key.get(field, {}).get(self.vars[field].get(), fallback)

    @staticmethod
    def _int(var, default):
        try:
            return int(str(var.get()).strip())
        except (TypeError, ValueError):
            return default

    def read_state(self):
        kind = self._key("start_kind", "airbase")
        start_text = self.vars["start"].get().strip()
        start = (self._key("start", "") if kind != "airbase" else start_text)
        return FormState(
            side=self._key("side", "blue"),
            era=self._key("era", ""), map_key=self._key("map", ""),
            mission=self._key("mission", ""), aircraft=self._key("aircraft", ""),
            posture=self._key("posture", ""), start_kind=kind, start_name=start,
            flights=self._int(self.vars["flights"], 3),
            flight_size=self._int(self.vars["flight_size"], 2),
            max_units=self._int(self.vars["max_units"], 240),
            seed=self._int(self.vars["seed"], 0),
            start_state=self._key("start_state", "cold"), any_aircraft=bool(self.opt_all.get()),
            awacs=bool(self.opt_awacs.get()), tanker=bool(self.opt_tanker.get()),
            time_of_day=self._key("time_of_day", "day"), season=self._key("season", "random"),
            weather=self._key("weather", "scattered"),
            defences=self._key("defences", "medium"),
            player_country=self._key("player_country", "usa"),
            enemy_country=self._key("enemy_country", "random"),
            ground_units=self._int(self.vars["ground_units"], 80),
            frontline_units=self._int(self.vars["frontline_units"], 80),
            statics=self._int(self.vars["statics"], 35))

    def _offer(self, field, widget, mapping):
        """Fill a combobox with {key: display} and remember how to read it back."""
        self._to_key[field] = _invert(mapping)
        widget["values"] = list(mapping.values())

    def _map_choices(self):
        """Maps to offer: only those the installed pydcs has (all of them if pydcs is absent)."""
        if self._maps is None:
            try:
                from .builder import available_map_keys
                self._maps = available_map_keys() or list(MAPS)
            except Exception:  # noqa: BLE001 - pydcs missing: preview still works
                self._maps = list(MAPS)
        return {k: MAPS[k].display for k in self._maps}

    def write_state(self, s):
        era = ERAS[s.era]
        self._offer("side", self.cb_side, SIDE_LABEL)
        self._offer("era", self.cb_era, {k: e.label for k, e in ERAS.items()})
        maps = self._map_choices()
        if s.map_key not in maps:
            s.map_key = next(iter(maps))
        self._offer("map", self.cb_map, maps)
        self._offer("mission", self.cb_mission,
                    {k: MISSION_LABEL[k]
                     for k in missions_for(s.era, side=s.side, any_era=s.any_aircraft, map_key=s.map_key)})
        self._offer("aircraft", self.cb_aircraft,
                    {a.key: a.label for a in aircraft_for(s.era, s.mission, s.start_kind, s.side, s.any_aircraft)})
        self._offer("posture", self.cb_posture, POSTURE_LABEL)
        self._offer("start_state", self.cb_state, START_STATE_LABEL)
        self._offer("time_of_day", self.cb_time, TIME_LABEL)
        self._offer("season", self.cb_season, SEASON_LABEL)
        self._offer("weather", self.cb_weather, WEATHER_LABEL)
        self._offer("defences", self.cb_defences, defences_labels(s.mission))
        self._offer("player_country", self.cb_pcountry, dict(player_country_options(s.era, s.side)))
        self._offer("enemy_country", self.cb_ecountry, dict(enemy_country_options(s.era, s.side)))
        self._offer("start_kind", self.cb_kind,
                    {k: START_KIND_LABEL[k]
                     for k in start_kinds_for_mission(s.era, s.mission, s.side, s.any_aircraft)})

        self.vars["side"].set(SIDE_LABEL[s.side])
        self.vars["era"].set(era.label)
        self.vars["map"].set(MAPS[s.map_key].display)
        self.vars["mission"].set(MISSION_LABEL[s.mission])
        self.vars["aircraft"].set(AIRCRAFT[s.aircraft].label)
        self.vars["posture"].set(POSTURE_LABEL[s.posture])
        self.vars["start_kind"].set(START_KIND_LABEL[s.start_kind])
        self.vars["start_state"].set(START_STATE_LABEL[s.start_state])
        self.vars["time_of_day"].set(TIME_LABEL[s.time_of_day])
        self.vars["season"].set(SEASON_LABEL[s.season])
        self.vars["weather"].set(WEATHER_LABEL[s.weather])
        self.vars["defences"].set(defences_labels(s.mission)[s.defences])
        self.vars["player_country"].set(dict(player_country_options(s.era, s.side))[s.player_country])
        self.vars["enemy_country"].set(dict(enemy_country_options(s.era, s.side))[s.enemy_country])
        self.opt_all.set(s.any_aircraft)
        self.opt_awacs.set(s.awacs)
        self.opt_tanker.set(s.tanker)
        self._suggest(s)

        if s.start_kind == "airbase":
            names = self._airbases(s.map_key)
            self._to_key["start"] = {}
            self.cb_start["values"] = names
            self.cb_start.configure(state="normal")
            self.vars["start"].set(s.start_name or MAPS[s.map_key].default_airbase)
        else:
            carriers = dict(carriers_for(s.era, s.start_kind, s.side))
            self._offer("start", self.cb_start, carriers)
            self.cb_start.configure(state="readonly")
            self.vars["start"].set(carriers[s.start_name])

        self.vars["flights"].set(str(s.flights))
        self.vars["flight_size"].set(str(s.flight_size))
        self.vars["ground_units"].set(str(s.ground_units))
        self.vars["frontline_units"].set(str(s.frontline_units))
        self.vars["statics"].set(str(s.statics))
        self.vars["max_units"].set(str(s.max_units))
        self.vars["seed"].set(str(s.seed))

    def _suggest(self, s):
        """Three suggested airbases for this map and side; buttons are only live for airbase starts."""
        names = list(MAPS[s.map_key].suggested(s.side))
        for i, b in enumerate(self.suggest_buttons):
            name = names[i] if i < len(names) else ""
            b.configure(text=name or "-", state="normal" if name and s.start_kind == "airbase" else "disabled",
                        command=(lambda n=name: self.pick_start(n)) if name else (lambda: None))

    def pick_start(self, name):
        self.vars["start"].set(name)
        self.on_change()

    def _airbases(self, map_key):
        """Airbase names from pydcs when it is installed; otherwise an empty list (free typing)."""
        if map_key not in self._airbase_cache:
            try:
                from .builder import airbase_names
                self._airbase_cache[map_key] = airbase_names(map_key)
            except Exception:  # noqa: BLE001 - pydcs missing or terrain name mismatch
                self._airbase_cache[map_key] = []
        return self._airbase_cache[map_key]

    # ---- events ---------------------------------------------------------------

    def on_change(self, *_):
        if self._busy:
            return
        self._busy = True
        try:
            state, msgs = repair(self.read_state())
            self.write_state(state)
            self.status.set("  ".join(msgs))
        finally:
            self._busy = False

    def new_seed(self):
        self.vars["seed"].set(str(random.randint(0, 999999)))

    def _plan(self):
        self.on_change()
        state = self.read_state()
        try:
            plan = generate_plan(to_request(state))
        except ValueError as e:
            messagebox.showerror("Cannot generate that mission", str(e))
            return None, state
        return plan, state

    def _show_tabs(self, tabs):
        """tabs: [(label, text)] - one notebook tab each."""
        for w in self._tab_widgets:
            try:
                self.notebook.forget(w)
                w.destroy()
            except Exception:  # noqa: BLE001
                pass
        self._tab_widgets = []
        for label, text in tabs:
            box = ScrolledText(self.notebook, wrap="word", font=("Consolas", 10))
            theme.style_text(box)
            box.insert("1.0", text)
            box.configure(state="disabled")
            self.notebook.add(box, text=label)
            self._tab_widgets.append(box)

    def _show_brief(self, brief):
        self.last_brief = brief
        self._show_tabs([(p.tab, p.as_text()) for p in brief.pages])

    def preview(self):
        plan, _ = self._plan()
        if plan is None:
            return
        self.last_plan = plan
        self._show_brief(compose(plan))
        extra = "  ".join(plan.notes)
        self.status.set(f"Seed {plan.request.seed}: {unit_summary(plan)}. {extra}".strip())

    def _need_brief(self):
        plan, _ = self._plan()
        if plan is None:
            return None, None
        self.last_plan = plan
        brief = compose(plan)
        self._show_brief(brief)
        return plan, brief

    def _render(self, plan, brief):
        try:
            from . import render
            return render, render.render_pages(plan, brief)
        except ImportError:
            messagebox.showerror("Pillow is missing",
                                 "Drawing the briefing pages needs the Pillow library.\n\n"
                                 "Double-click setup.bat, or run:  py -m pip install pillow")
            return None, None

    def export_pdf(self):
        plan, brief = self._need_brief()
        if plan is None:
            return
        path = filedialog.asksaveasfilename(
            title="Save briefing PDF", defaultextension=".pdf",
            initialdir=str(default_output_dir()), initialfile=default_filename(self.read_state())[:-4] + ".pdf",
            filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        render, pages = self._render(plan, brief)
        if render is None:
            return
        render.save_pdf(pages, path)
        self.status.set(f"Saved {path} (route headings appear once a mission is generated on a map).")

    def export_pngs(self):
        plan, brief = self._need_brief()
        if plan is None:
            return
        folder = filedialog.askdirectory(title="Folder for the kneeboard images",
                                         initialdir=str(default_output_dir()))
        if not folder:
            return
        render, pages = self._render(plan, brief)
        if render is None:
            return
        files = render.kneeboard_files(pages)
        for name, data in files:
            (Path(folder) / name).write_bytes(data)
        self.status.set(f"Saved {len(files)} kneeboard images to {folder}")

    def generate(self):
        plan, state = self._plan()
        if plan is None:
            return
        self._show_brief(compose(plan))

        path = filedialog.asksaveasfilename(
            title="Save mission", defaultextension=".miz",
            initialdir=str(default_output_dir()), initialfile=default_filename(state),
            filetypes=[("DCS mission", "*.miz")])
        if not path:
            return
        try:
            from .builder import build_mission
        except ImportError as e:
            messagebox.showerror("Cannot write the mission", explain_import_error(e))
            return
        pdf_path = str(Path(path).with_suffix(".pdf")) if self.opt_pdf.get() else None
        try:
            result = build_mission(plan, path, kneeboard=bool(self.opt_kneeboard.get()),
                                   pdf_path=pdf_path)
        except Exception as e:  # noqa: BLE001 - show any builder problem to the user
            report = Path(path).with_name("dcsgen_error.txt")
            try:
                report.write_text(f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}", encoding="utf-8")
                where = f"\n\nFull details were saved to:\n{report}\nSend me that file."
            except OSError:
                where = ""
            messagebox.showerror("Could not write the mission", f"{type(e).__name__}: {e}{where}")
            return
        warnings = list(result.warnings)
        if result.briefing is not None:
            self._show_brief(result.briefing)
        body = f"Saved {path}\n\n{unit_summary(plan)}"
        if result.kneeboard_pages:
            body += f"\n\nKneeboard: {result.kneeboard_pages} pages added."
        if pdf_path:
            body += f"\nPDF: {pdf_path}"
        if warnings:
            body += "\n\nWarnings:\n- " + "\n- ".join(warnings)
        messagebox.showinfo("Mission written", body)
        self.status.set(f"Saved {path}. {len(warnings)} warning(s).")


def _set_app_identity():
    """Windows: give the program its own taskbar identity, so it shows our icon, not Python's."""
    try:
        import ctypes
        import sys
        if sys.platform == "win32":
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DCSStrikePackage.App")
    except Exception:  # noqa: BLE001 - cosmetic only
        pass


def _set_window_icon(root):
    assets = Path(__file__).parent / "assets"
    try:
        root.iconbitmap(default=str(assets / "icon.ico"))       # Windows title bar and taskbar
    except Exception:  # noqa: BLE001
        pass
    try:
        root._icon_image = tk.PhotoImage(file=str(assets / "icon.png"))
        root.iconphoto(True, root._icon_image)                  # other platforms / fallback
    except Exception:  # noqa: BLE001
        pass


def main():
    _set_app_identity()
    root = tk.Tk()
    _set_window_icon(root)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
