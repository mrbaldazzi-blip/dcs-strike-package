"""Command line interface.

  python -m dcsgen generate --era modern --map caucasus --aircraft f16c --mission strike --dry-run
  python -m dcsgen generate --side red --era nineties --aircraft su25 --mission cas --pdf
  python -m dcsgen list-aircraft --era late_cold_war --side red
  python -m dcsgen scan-mods
  python -m dcsgen dump-names
  python -m dcsgen list-maps
  python -m dcsgen list-airbases --map caucasus      (needs pydcs)
  python -m dcsgen check-units                       (needs pydcs)
"""

import argparse
import json
import random
import sys
from collections import Counter
from dataclasses import asdict

from . import __version__
from .briefing import compose
from .catalog import AIRCRAFT, available_aircraft
from .eras import ERAS
from .gui_logic import explain_import_error
from .maps import MAPS
from .models import MissionRequest, MissionType, Posture, StartLocation
from .planner import generate_plan


def _generate(args):
    seed = args.seed if args.seed is not None else random.randint(0, 999999)
    req = MissionRequest(
        era=args.era, map_key=args.map, aircraft=args.aircraft,
        mission_type=MissionType(args.mission), posture=Posture(args.posture),
        start=StartLocation(args.start_kind, args.start or ""), seed=seed,
        flights=args.flights, flight_size=args.flight_size, max_units=args.max_units,
        side=args.side, start_state=args.start_state, any_aircraft=args.all_aircraft,
        time_of_day=args.time, season=args.season, weather=args.weather,
        ground_units=args.ground_units, frontline_units=args.frontline_units, statics=args.statics, defences=args.defences,
        awacs=not args.no_awacs, tanker=args.tanker,
        player_country=args.player_country, enemy_country=args.enemy_country)
    try:
        plan = generate_plan(req)
    except ValueError as e:
        sys.exit(f"Cannot generate that mission: {e}")

    brief = compose(plan)
    briefing = brief.as_text()
    by_tag = Counter()
    for g in plan.groups:
        by_tag[g.tag] += g.count
    aircraft = sum(f.size for f in plan.flights)
    print(f"[seed {seed}] units: {plan.total_units} of {req.max_units} "
          f"(flights {aircraft}, " + ", ".join(f"{k} {v}" for k, v in sorted(by_tag.items())) + ")")
    for note in plan.notes:
        print(f"  note: {note}")

    if args.json:
        print(json.dumps(asdict(plan), indent=2, default=str))
        return
    if args.dry_run:
        print()
        print(briefing)
        return

    try:
        from .builder import build_mission
    except ImportError as e:
        sys.exit(explain_import_error(e) + "\n\nUse --dry-run to preview the mission without it.")
    pdf = args.out.rsplit(".", 1)[0] + ".pdf" if args.pdf else None
    result = build_mission(plan, args.out, kneeboard=not args.no_kneeboard, pdf_path=pdf)
    print(f"Wrote {args.out}" + (f" and {pdf}" if pdf else ""))
    if result.kneeboard_pages:
        print(f"  kneeboard pages added: {result.kneeboard_pages}")
    for w in result.warnings:
        print(f"  warning: {w}")


def _list_aircraft(args):
    eras = [args.era] if args.era else list(ERAS)
    for ek in eras:
        print(f"{ERAS[ek].label}  [{ek}]")
        for a in available_aircraft(ek, side=args.side):
            roles = ",".join(sorted(r.value for r in a.roles))
            extra = (" carrier" if a.carrier else "")
            print(f"  {a.key:<9} {a.side:<5} {a.label:<34} {roles}{extra}")


def _list_maps(args):
    for m in MAPS.values():
        print(f"  {m.key:<15} {m.display:<18} default start: {m.default_airbase or '(choose with --start)'}")


def _gui(args):
    try:
        from .gui import main as gui_main
    except ImportError as e:
        sys.exit(f"The GUI needs tkinter ({e}). It ships with the python.org Windows installer; "
                 "on Linux install your distribution's python3-tk package.")
    gui_main()


def _builder_call(name, *a):
    try:
        from . import builder
    except ImportError as e:
        sys.exit(explain_import_error(e))
    return getattr(builder, name)(*a)


def _diagnose(args):
    """Report what 'dcs' package is installed, so wrong-package problems are obvious."""
    import importlib
    import importlib.metadata as md
    import platform

    print(f"dcsgen {__version__}   Python {platform.python_version()} ({platform.system()})")
    for dist in ("pydcs", "dcs"):
        try:
            print(f"pip package '{dist}': version {md.version(dist)}")
        except md.PackageNotFoundError:
            print(f"pip package '{dist}': not installed")
    try:
        dcs = importlib.import_module("dcs")
    except ImportError as e:
        print(f"import dcs: FAILED ({e})")
        return
    print(f"import dcs: ok, from {getattr(dcs, '__file__', '?')}")
    print(f"  has Mission class: {hasattr(dcs, 'Mission')}  "
          "(False means this is NOT pydcs; run setup.bat to fix)")
    for sub in ("countries", "planes", "vehicles", "ships", "terrain", "mission"):
        try:
            importlib.import_module(f"dcs.{sub}")
            print(f"  dcs.{sub}: ok")
        except ImportError as e:
            print(f"  dcs.{sub}: MISSING ({e})")
    try:
        from .builder import _terrain  # noqa: F401  (also runs the wrong-package check)
        print("dcsgen builder: loads ok")
    except ImportError as e:
        print(f"dcsgen builder: FAILED ({e})")


def _list_modules(args):
    from . import ownership
    keys, folders = ownership.detect()
    if folders is None:
        print("DCS was not found (or it has no Mods\\aircraft folder), so every aircraft is offered.")
        return 0
    print(f"Folders in Mods\\aircraft: {', '.join(folders)}")
    print(f"Aircraft offered: {', '.join(sorted(keys or []))}")
    print(f"Folders that matched no aircraft: {', '.join(ownership.unmatched(folders)) or 'none'}")
    try:                                    # what pydcs calls the Tiger, Sabre and MiG-15 types
        import dcs.planes as planes
        print("pydcs aircraft with F-5, F-86 or MiG-15 in the name:")
        for name in sorted(dir(planes)):
            if any(t in name.upper() for t in ("F_5", "F_86", "MIG_15", "MIG15")):
                print(f"  {name}  id={getattr(getattr(planes, name), 'id', '?')}")
    except Exception as e:  # noqa: BLE001
        print(f"(pydcs not available: {e})")
    return 0


def _paths(args):
    from . import liveryscan, mods, gui_logic
    installs = liveryscan.install_dirs()
    print("DCS install folder(s) found:")
    for i in installs or []:
        print(f"  {i}")
    if not installs:
        print("  none. Put the folder (the one that contains 'Bazar') in dcs_path.txt next to this program.")
    print(f"Windows Saved Games folder: {mods.saved_games_dir()}")
    profs = mods.saved_games_profiles()
    print("DCS profiles in it: " + (", ".join(p.name for p in profs) or "none"))
    print(f"Missions will be saved to: {gui_logic.default_output_dir()}")
    return 0


def _scan_mods(args):
    from .catalog import AIRCRAFT
    from .mods import resolve_mod_type, saved_games_profiles, scan_installed_mods
    print("DCS profiles:", [str(p) for p in saved_games_profiles()] or "none found")
    found = scan_installed_mods()
    for folder, ids in found.items():
        print(f"  mod folder {folder}: {ids}")
    for a in AIRCRAFT.values():
        if a.mod:
            tid, src = resolve_mod_type(a, found)
            print(f"{a.display}: type id '{tid}' ({src})")


def _dump_names(args):
    d = _builder_call("dump_names")
    with open(args.out, "w", encoding="utf-8") as f:
        for k, names in d.items():
            f.write(f"## {k}\n" + "\n".join(names) + "\n\n")
    print(f"Wrote {args.out}")


def _dump_liveries(args):
    lines = _builder_call("dump_liveries")
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {args.out}  (send me this file)")


def _probe_land(args):
    lines = _builder_call("dump_land_probe")
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {args.out}  (send me this file)")


def _probe_runways(args):
    lines = _builder_call("dump_runway_probe")
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {args.out}  (send me this file)")


def _check_runways(args):
    lines = _builder_call("dump_runway_check")
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {args.out}  (send me this file)")


def _fetch_runways(args):
    from . import runways
    try:
        runways.fetch()
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Could not build the runway file: {e}")


def _fetch_coast(args):
    from . import coast
    try:
        coast.fetch()
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Could not build the coastline file: {e}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="dcsgen", description="DCS Strike Package: era-based DCS World mission generator.")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="generate a mission")
    g.add_argument("--side", choices=["blue", "red"], default="blue", help="side you fly for")
    g.add_argument("--era", choices=list(ERAS), required=True)
    g.add_argument("--map", choices=list(MAPS), default="caucasus")
    g.add_argument("--aircraft", choices=list(AIRCRAFT), required=True)
    g.add_argument("--mission", choices=[m.value for m in MissionType], required=True)
    g.add_argument("--posture", choices=[x.value for x in Posture], default=Posture.ACTIVE_WAR.value)
    g.add_argument("--start-kind", choices=["airbase", "carrier", "supercarrier"], default="airbase")
    g.add_argument("--start", help="airbase name, or carrier key (default: map/era default)")
    g.add_argument("--flights", type=int, default=3, help="simultaneous flights in the package, 1-3")
    g.add_argument("--flight-size", type=int, default=2, help="aircraft in your flight, 1-4")
    g.add_argument("--max-units", type=int, default=240, help="performance budget")
    g.add_argument("--ground-units", type=int, default=80, help="active ground units, 60-100")
    g.add_argument("--frontline-units", type=int, default=80, help="frontline units (active war), 0-160")
    g.add_argument("--statics", type=int, default=35, help="static objects, 20-50")
    g.add_argument("--start-state", choices=["cold", "hot", "runway"], default="cold")
    g.add_argument("--time", choices=["day", "night", "sunrise", "presunrise", "sunset", "random"],
                   default="day", help="time of day")
    g.add_argument("--season", choices=["random", "summer", "winter", "spring", "autumn"],
                   default="random")
    g.add_argument("--player-country", default="default",
                   help="your country key, e.g. usa, uk, germany, russia, china (default: USA or Russia/USSR)")
    g.add_argument("--enemy-country", default="random",
                   help="enemy country key, or random (weighted by era; the default)")
    g.add_argument("--no-awacs", action="store_true", help="leave the AWACS out")
    g.add_argument("--tanker", action="store_true", help="add a tanker matched to your aircraft")
    g.add_argument("--defences", choices=["light", "medium", "heavy"], default="medium",
                   help="enemy air defences: light (no SAMs), medium (1-2 sites), heavy (saturated)")
    g.add_argument("--weather", default="scattered",
                   help="scattered (default), clear, few, broken, overcast, rain, thunderstorm, fog, haze or random")
    g.add_argument("--all-aircraft", action="store_true", help="allow any aircraft of your side, not only historical ones")
    g.add_argument("--seed", type=int, default=None)
    g.add_argument("--out", default="mission.miz")
    g.add_argument("--pdf", action="store_true", help="also write the briefing as a PDF")
    g.add_argument("--no-kneeboard", action="store_true", help="do not add briefing pages to the kneeboard")
    g.add_argument("--dry-run", action="store_true", help="print the briefing only; no pydcs needed")
    g.add_argument("--json", action="store_true", help="print the full plan as JSON; no pydcs needed")
    g.set_defaults(fn=_generate)

    la = sub.add_parser("list-aircraft", help="list aircraft, optionally for one era")
    la.add_argument("--era", choices=list(ERAS))
    la.add_argument("--side", choices=["blue", "red"])
    la.set_defaults(fn=_list_aircraft)

    sub.add_parser("list-maps", help="list maps").set_defaults(fn=_list_maps)
    sub.add_parser("gui", help="open the graphical interface").set_defaults(fn=_gui)
    sub.add_parser("diagnose", help="report which pydcs is installed and whether it loads").set_defaults(
        fn=_diagnose)

    sub.add_parser("list-modules", help="show which aircraft modules were found in your DCS install").set_defaults(
        fn=_list_modules)
    sub.add_parser("paths", help="show where DCS and your Saved Games folder were found").set_defaults(fn=_paths)
    sub.add_parser("scan-mods", help="show aircraft mods found in Saved Games").set_defaults(fn=_scan_mods)
    dn = sub.add_parser("dump-names", help="write every unit name your pydcs knows to a text file")
    dn.add_argument("--out", default="pydcs_names.txt")
    dn.set_defaults(fn=_dump_names)

    dl = sub.add_parser("dump-liveries", help="write how your pydcs lists countries and liveries to a text file")
    dl.add_argument("--out", default="pydcs_liveries.txt")
    dl.set_defaults(fn=_dump_liveries)

    cr = sub.add_parser("check-runways", help="list every airfield and how well its real runway was matched")
    cr.add_argument("--out", default="runway_check.txt")
    cr.set_defaults(fn=_check_runways)

    fr = sub.add_parser("fetch-runways", help="download real runway lengths and positions once")
    fr.set_defaults(fn=_fetch_runways)

    fc = sub.add_parser("fetch-coast", help="download real coastlines once, so units are never placed in the sea")
    fc.set_defaults(fn=_fetch_coast)

    pr = sub.add_parser("probe-runways", help="write where runway data may be found to a text file")
    pr.add_argument("--out", default="pydcs_runways.txt")
    pr.set_defaults(fn=_probe_runways)

    pl = sub.add_parser("probe-land", help="write whether your pydcs can tell land from water to a text file")
    pl.add_argument("--out", default="pydcs_land.txt")
    pl.set_defaults(fn=_probe_land)

    lb = sub.add_parser("list-airbases", help="list airbases on a map (needs pydcs)")
    lb.add_argument("--map", choices=list(MAPS), required=True)
    lb.set_defaults(fn=lambda a: print("\n".join(_builder_call("list_airbases", a.map))))

    sub.add_parser("check-units", help="verify every DCS unit name resolves (needs pydcs)").set_defaults(
        fn=lambda a: print("\n".join(_builder_call("check_units")) or "All unit names resolved."))

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
