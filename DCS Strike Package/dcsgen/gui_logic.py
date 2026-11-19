"""Form logic for the GUI, kept free of tkinter so it can be tested anywhere.

The window offers only choices that are valid together. When one choice makes another invalid
(say you switch side while an F-16 is selected), `repair` fixes the dependent choice and says
what it changed.
"""

from dataclasses import dataclass, replace
from pathlib import Path

from .catalog import AIRCRAFT, available_aircraft, can_fly, refuel_method
from .conditions import DEFAULT_DEFENCES, DEFENCES_LABEL, DEFAULT_WEATHER, SEASON_LABEL, TIME_LABEL, WEATHER_LABEL
from .eras import ERAS, opposite
from .maps import MAPS
from .models import SIDES, MissionRequest, MissionType, Posture, StartLocation, enemy_of

START_KIND_LABEL = {
    "airbase": "Airbase",
    "carrier": "Carrier",
    "supercarrier": "Supercarrier (mod)",
}
MISSION_LABEL = {
    "strike": "Strike", "cas": "CAS", "sead": "SEAD", "dead": "DEAD", "cap": "CAP",
    "intercept": "Intercept", "naval": "Naval strike",
}
POSTURE_LABEL = {
    "preemptive": "Pre-emptive strike",
    "active_war": "Active warzone",
}
START_STATE_LABEL = {"cold": "Cold start", "hot": "Hot start", "runway": "Runway start"}
SIDE_LABEL = {
    "blue": "Blue (NATO)",
    "red": "Red (Soviet / Russian)",
}


@dataclass
class FormState:
    era: str = "modern"
    map_key: str = "caucasus"
    side: str = "blue"
    mission: str = "strike"
    aircraft: str = "f16c"
    posture: str = "active_war"
    start_kind: str = "airbase"
    start_name: str = ""       # airbase name, or carrier key for carrier starts
    flights: int = 3
    flight_size: int = 2
    max_units: int = 240
    seed: int = 0
    start_state: str = "cold"
    any_aircraft: bool = False
    time_of_day: str = "day"
    season: str = "random"
    weather: str = DEFAULT_WEATHER
    ground_units: int = 80
    frontline_units: int = 80
    statics: int = 35
    defences: str = DEFAULT_DEFENCES
    awacs: bool = True
    tanker: bool = False
    player_country: str = "usa"
    enemy_country: str = "random"


# ---- what is offered --------------------------------------------------------

def _enemy_has_radar_sams(era_key, side):
    return any(s.radar_guided for s in ERAS[era_key].faction(enemy_of(side)).sam_sites)


def catalog_owned():
    from .catalog import owned_filter
    return owned_filter()


def missions_for(era_key, aircraft_key=None, side="blue", any_era=False, map_key=None):
    """Mission type keys that are possible in this era for this side (and aircraft, if given)."""
    out = []
    for m in MissionType:
        if m in (MissionType.SEAD, MissionType.DEAD) and not _enemy_has_radar_sams(era_key, side):
            continue
        if m is MissionType.NAVAL and map_key is not None and not MAPS[map_key].sea:
            continue                      # no open water on this map
        if aircraft_key is not None and not can_fly(AIRCRAFT[aircraft_key], m):
            continue
        if not available_aircraft(era_key, m, side=side, any_era=any_era):
            continue
        out.append(m.value)
    return out


def aircraft_for(era_key, mission, start_kind, side="blue", any_era=False):
    return available_aircraft(era_key, MissionType(mission), carrier=start_kind != "airbase",
                              side=side, any_era=any_era)


def carriers_for(era_key, kind, side="blue"):
    """(key, display) pairs of the carriers available to this side for this start kind."""
    if kind == "airbase":
        return []
    want_mod = kind == "supercarrier"
    return [(c.key, c.display) for c in ERAS[era_key].faction(side).carriers
            if c.needs_mod == want_mod]


def start_kinds_for(era_key, aircraft_key, side="blue"):
    kinds = ["airbase"]
    if AIRCRAFT[aircraft_key].carrier:
        for kind in ("carrier", "supercarrier"):
            if carriers_for(era_key, kind, side):
                kinds.append(kind)
    return kinds


def start_kinds_for_mission(era_key, mission, side="blue", any_era=False):
    """Start types worth offering: those at least one suitable aircraft can use.

    Offered by era, side and mission rather than by the selected aircraft, so picking a
    carrier start is always possible; `repair` swaps the aircraft if it must.
    """
    kinds = ["airbase"]
    for kind in ("carrier", "supercarrier"):
        if carriers_for(era_key, kind, side) and aircraft_for(era_key, mission, kind, side, any_era):
            kinds.append(kind)
    return kinds


def player_country_options(era_key, side):
    """[(key, display)] of countries the player can fly for; the first is the default."""
    from .countries import available
    return available(side, era_key)


def enemy_country_options(era_key, side):
    """[(key, display)]: a weighted random pick first, then the enemy side's countries."""
    from .countries import ANY, available
    return [(ANY, "Random (weighted by era)")] + available(opposite(side), era_key)


def _preferred_order(specs):
    """Stock aircraft before community mods, then by key, for choosing a replacement."""
    return [a.key for a in sorted(specs, key=lambda a: (a.mod, bool(a.note), a.key))]


# ---- keeping the form consistent -------------------------------------------

def repair(state):
    """Return (consistent_state, messages). Never mutates the input."""
    s = replace(state)
    msgs = []

    if s.era not in ERAS:
        s.era = next(iter(ERAS))
        msgs.append(f"Era reset to {ERAS[s.era].label}.")
    if s.map_key not in MAPS:
        s.map_key = next(iter(MAPS))
        msgs.append(f"Map reset to {MAPS[s.map_key].display}.")
    if s.side not in SIDES:
        s.side = "blue"
    if s.posture not in POSTURE_LABEL:
        s.posture = "active_war"
    if s.start_state not in START_STATE_LABEL:
        s.start_state = "cold"
    if s.time_of_day not in TIME_LABEL:
        s.time_of_day = "day"
    if s.season not in SEASON_LABEL:
        s.season = "random"
    if s.weather not in WEATHER_LABEL:
        s.weather = DEFAULT_WEATHER
    if s.defences not in DEFENCES_LABEL:
        s.defences = DEFAULT_DEFENCES
    if s.defences == "light" and s.mission in ("sead", "dead"):
        s.defences = "medium"
        msgs.append("Defences raised to medium: SEAD and DEAD need a SAM site to attack.")
    mine = player_country_options(s.era, s.side)
    if s.player_country not in dict(mine):
        s.player_country = mine[0][0]
    if s.enemy_country not in dict(enemy_country_options(s.era, s.side)):
        s.enemy_country = "random"
    s.awacs, s.tanker = bool(s.awacs), bool(s.tanker)
    if s.tanker and s.aircraft in AIRCRAFT and not refuel_method(s.aircraft):
        s.tanker = False
        msgs.append(f"Tanker switched off: the {AIRCRAFT[s.aircraft].display} cannot refuel in flight.")
    s.any_aircraft = bool(s.any_aircraft)
    if s.start_kind not in START_KIND_LABEL:
        s.start_kind = "airbase"

    ms = missions_for(s.era, side=s.side, any_era=s.any_aircraft, map_key=s.map_key)
    if s.mission not in ms:
        old = MISSION_LABEL.get(s.mission, s.mission)
        s.mission = ms[0]
        msgs.append(f"Mission changed to {MISSION_LABEL[s.mission]}: "
                    f"{old} is not possible for this side in {ERAS[s.era].label}.")

    choices = _preferred_order(aircraft_for(s.era, s.mission, s.start_kind, s.side, s.any_aircraft))
    if not choices:
        msgs.append(f"No carrier-capable aircraft can fly {MISSION_LABEL[s.mission]} for this "
                    f"side in {ERAS[s.era].label}; start location set to an airbase.")
        s.start_kind, s.start_name = "airbase", ""
        choices = _preferred_order(aircraft_for(s.era, s.mission, "airbase", s.side, s.any_aircraft))
    if s.aircraft not in choices:
        old_spec = AIRCRAFT.get(s.aircraft)
        old = old_spec.display if old_spec else str(s.aircraft)
        s.aircraft = choices[0]
        owned = catalog_owned()
        if old_spec and old_spec.side != s.side:
            why = f"{old} flies for the {old_spec.side} side"
        elif old_spec and owned is not None and not old_spec.mod and old_spec.key not in owned:
            why = f"{old} is not installed in your DCS"
        else:
            why = (f"{old} cannot fly {MISSION_LABEL[s.mission]} from this start in "
                   f"{ERAS[s.era].label}")
        msgs.append(f"Aircraft changed to {AIRCRAFT[s.aircraft].display}: {why}.")

    if s.start_kind not in start_kinds_for(s.era, s.aircraft, s.side):
        msgs.append(f"{AIRCRAFT[s.aircraft].display} cannot start from a "
                    f"{START_KIND_LABEL[s.start_kind].lower()} in {ERAS[s.era].label}; "
                    "start location set to an airbase.")
        s.start_kind, s.start_name = "airbase", ""

    all_carrier_keys = {c.key for e in ERAS.values() for f in (e.blue, e.red) for c in f.carriers}
    if s.start_kind == "airbase":
        if s.start_name in all_carrier_keys:
            s.start_name = ""
    else:
        keys = [k for k, _ in carriers_for(s.era, s.start_kind, s.side)]
        if s.start_name not in keys:
            s.start_name = keys[0]

    s.flights = min(3, max(1, int(s.flights)))
    s.flight_size = min(4, max(1, int(s.flight_size)))
    s.max_units = max(20, int(s.max_units))
    s.ground_units = min(100, max(60, int(s.ground_units)))
    s.statics = min(50, max(20, int(s.statics)))
    s.frontline_units = min(160, max(0, int(s.frontline_units)))
    fixed = s.flight_size + 2 * (s.flights - 1) + (1 if s.start_kind != "airbase" else 0)
    front = s.frontline_units if s.posture == "active_war" else 0
    needed = fixed + s.ground_units + front + 14   # flights, ground units, frontline and some enemy fighters
    if s.max_units < needed:
        s.max_units = needed
        msgs.append(f"Unit limit raised to {needed} to fit the ground units, frontline and flights.")
    if s.mission == "intercept":
        want = "runway" if s.start_kind == "airbase" else "hot"
        if s.start_state != want:
            s.start_state = want
            msgs.append("Intercept scrambles from the runway (hot start on a carrier).")
    return s, msgs


def to_request(state):
    return MissionRequest(
        era=state.era, map_key=state.map_key, aircraft=state.aircraft,
        mission_type=MissionType(state.mission), posture=Posture(state.posture),
        start=StartLocation(state.start_kind, state.start_name),
        seed=state.seed, flights=state.flights, flight_size=state.flight_size,
        max_units=state.max_units, side=state.side, start_state=state.start_state,
        any_aircraft=state.any_aircraft, time_of_day=state.time_of_day, season=state.season,
        weather=state.weather, ground_units=state.ground_units, frontline_units=state.frontline_units,
        statics=state.statics,
        defences=state.defences, awacs=bool(state.awacs), tanker=bool(state.tanker),
        player_country=state.player_country, enemy_country=state.enemy_country)


# ---- small helpers ----------------------------------------------------------

def unit_summary(plan):
    from collections import Counter
    by_tag = Counter()
    for g in plan.groups:
        by_tag[g.tag] += g.count
    flights = sum(f.size for f in plan.flights)
    parts = ", ".join(f"{k} {v}" for k, v in sorted(by_tag.items()))
    return (f"{plan.total_units} of {plan.request.max_units} units "
            f"(flights {flights}, {parts})")


def explain_import_error(e):
    """Plain-English text for a failure to load the pydcs-backed builder.

    Tells the difference between "not installed" and "something else is wrong",
    so a broken or wrong package is not reported as missing.
    """
    if isinstance(e, ModuleNotFoundError) and getattr(e, "name", None) == "dcs":
        return ("The pydcs library is not installed.\n\n"
                "Double-click setup.bat to install it, or run:  py -m pip install pydcs")
    return (f"The pydcs library is installed but could not be loaded:\n\n{e}\n\n"
            "Double-click setup.bat to repair it. If this message comes back, send it to me "
            "along with the output of:  py -m dcsgen diagnose")


def default_output_dir(home=None):
    """DCS's Missions folder if it exists (Windows Saved Games), otherwise the home folder."""
    from . import mods
    home = Path(home) if home else Path.home()
    saved = mods.saved_games_dir(home if home != Path.home() else None)
    if saved.is_dir():
        candidates = sorted(saved.glob("DCS*/Missions"),
                            key=lambda p: (p.parent.name != "DCS", p.parent.name))
        for c in candidates:
            if c.is_dir():
                return c
    return home


def default_filename(state):
    return f"Strike_Package_{state.era}_{state.side}_{state.mission}_{state.map_key}_{state.seed}.miz"
