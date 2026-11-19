"""Converts a MissionPlan into a .miz file using pydcs.

NOT TESTED against a real pydcs: it was written without pydcs available. The essentials
(mission, countries, the player's flights) fail loudly; everything else (enemy groups,
triggers, kneeboard, descriptions) goes through soft-fail helpers that record a warning and
carry on, so one API difference does not stop you getting a mission to test. Read the warnings.

Install the library with:  py -m pip install pydcs
(NOT "pip install dcs": that is a different, unrelated package with the same folder name.)
"""

import io
import math
import os
import random
import tempfile
import zipfile
from pathlib import Path
from dataclasses import dataclass, field, replace

import dcs

if not hasattr(dcs, "Mission"):
    raise ImportError(
        f"The installed 'dcs' package ({getattr(dcs, '__file__', 'unknown location')}) is not "
        "pydcs: it has no Mission class. Fix:  py -m pip uninstall dcs   then   "
        "py -m pip install pydcs   (re-running setup.bat does both).")

from dcs import countries, planes, ships, vehicles
from dcs import terrain as terrain_mod

from . import callouts, coast, conditions, effects, layouts, mods, navinfo, runways, unitnames
from .briefing import compose
from .countries import livery_ids
from .catalog import AIRCRAFT
from .eras import ERAS
from .maps import MAPS
from .models import MissionType as M
from .planner import AIRFIELD_STATICS, TARGET_STATICS, _offset

NM = 1852.0     # metres per nautical mile
FT = 0.3048
KT = 1.852      # km/h per knot


@dataclass
class BuildResult:
    path: str
    briefing: object
    warnings: list = field(default_factory=list)
    kneeboard_pages: int = 0


# ---- name resolution --------------------------------------------------------

def _vehicle_containers():
    cats = [getattr(vehicles, n) for n in
            ("AirDefence", "Armor", "Unarmed", "Artillery", "Infantry", "Fortification", "MissilesSS")
            if hasattr(vehicles, n)]
    return cats


_INDEX = {}


def _index(kind):
    if kind not in _INDEX:
        if kind == "v":
            maps = [getattr(vehicles, "vehicle_map", {})]
            _INDEX[kind] = unitnames.class_index(_vehicle_containers(), maps)
        elif kind == "p":
            maps = [getattr(planes, "plane_map", {})]
            _INDEX[kind] = unitnames.class_index([planes], maps)
        elif kind == "h":
            from dcs import helicopters
            maps = [getattr(helicopters, "helicopter_map", {})]
            _INDEX[kind] = unitnames.class_index([helicopters], maps)
        elif kind == "t":
            from dcs import statics
            conts = [getattr(statics, n) for n in ("Fortification", "Warehouse", "Cargo")
                     if hasattr(statics, n)]
            maps = [getattr(statics, n, {}) for n in ("fortification_map", "warehouse_map")]
            _INDEX[kind] = unitnames.class_index(conts, maps)
        else:
            maps = [getattr(ships, "ship_map", {})]
            _INDEX[kind] = unitnames.class_index([ships], maps)
    return _INDEX[kind]


def find_class(kind, name, extra_ids=()):
    return unitnames.find(name, _index(kind), extra_ids)


def apply_pylons(fg, plane_cls, pylons):
    """Load the chosen weapons onto every aircraft of a flight group. Returns the stations that
    could not be loaded (names this pydcs does not know), so the caller can warn."""
    bad = []
    if fg is None or not pylons:
        return bad
    for station, name in sorted(pylons.items(), key=lambda kv: int(kv[0])):
        holder = getattr(plane_cls, f"Pylon{int(station)}", None)
        weapon = getattr(holder, name, None) if holder is not None else None
        if weapon is None:
            bad.append(f"{station}:{name}")
            continue
        try:
            fg.load_pylon(weapon)
        except Exception:  # noqa: BLE001 - one bad station must not lose the rest
            bad.append(f"{station}:{name}")
    return bad


def _standin(spec, installed):
    """Make a plane class for an aircraft pydcs does not know, from a stock class."""
    base = find_class("p", spec.standin)
    if base is None:
        raise LookupError(f"Cannot build a stand-in for {spec.display}: stock aircraft "
                          f"'{spec.standin}' not found in your pydcs.")
    if spec.mod:
        type_id, source = mods.resolve_mod_type(spec, installed)
    else:
        type_id, source = spec.dcs_type, "guess"
    cls = type(spec.pydcs, (base,), {"id": type_id})
    return cls, type_id, source


def resolve_aircraft(spec_or_name, installed=None):
    """Return (plane class, note or '')."""
    spec = spec_or_name if hasattr(spec_or_name, "pydcs") else None
    name = spec.pydcs if spec else spec_or_name
    if spec is None:
        for s in AIRCRAFT.values():
            if s.pydcs == name:
                spec = s
                break
    extra = (spec.dcs_type,) if spec and spec.dcs_type else ()
    # A mod is never in pydcs even when the name matches something odd, so go via its folder.
    if spec and spec.mod:
        cls, type_id, source = _standin(spec, installed)
        real = find_class("p", name, extra)
        if real is not None and getattr(real, "flyable", False) and (
                source == "guess" or getattr(real, "id", None) == type_id):
            return real, (f"{spec.display}: community mod - it only appears in DCS if the mod is "
                          "installed (not found in Saved Games\\DCS\\Mods)." if source == "guess" else "")
        note = (f"{spec.display}: using DCS type id '{type_id}' "
                + ("(found in your Mods folder)." if source == "found" else
                   "(a guess - mod not found in Saved Games\\DCS\\Mods; install it or the slot will be empty)."))
        return cls, note
    cls = find_class("p", name, extra)
    if cls is not None:
        return cls, ""
    if spec and spec.standin:
        cls, type_id, _ = _standin(spec, installed)
        return cls, (f"{spec.display}: pydcs has no class for it, so a stand-in with DCS type id "
                     f"'{type_id}' was used. If the slot is empty, your DCS does not have this aircraft.")
    raise LookupError(f"Unknown aircraft '{name}' in your pydcs. Closest: "
                      f"{unitnames.closest(name, _index('p'))}.")


def _terrain(map_key):
    cls = MAPS[map_key].terrain_class
    if not hasattr(terrain_mod, cls):
        raise LookupError(f"Your pydcs has no terrain '{cls}' (map '{MAPS[map_key].display}').")
    return getattr(terrain_mod, cls)()


def available_map_keys():
    """Map keys whose terrain exists in the installed pydcs."""
    return [k for k, m in MAPS.items() if hasattr(terrain_mod, m.terrain_class)]


# ---- diagnostics ------------------------------------------------------------

def check_units():
    """Return a list of problems: unit names that do not resolve in the installed pydcs."""
    problems = []
    seen = set()
    for era in ERAS.values():
        for side in ("blue", "red"):
            f = era.faction(side)
            for site in f.sam_sites:
                seen.update(("v", c) for c, _ in site.components)
            seen.update(("v", c) for _, c, _ in f.aaa)
            if f.ewr:
                seen.add(("v", f.ewr))
            seen.update(("p", c) for _, c in f.fighters)
            seen.update(("v", c) for _, c, _ in f.soft_targets)
            seen.update(("v", c) for _, c, _ in f.forces)
            seen.update(("s", c.pydcs_name) for c in f.carriers)
            if not hasattr(countries, f.country):
                problems.append(f"Unknown country '{f.country}' (era {era.key}, {side})")
    seen.update(("t", n) for n in set(AIRFIELD_STATICS) | set(TARGET_STATICS))
    for a in AIRCRAFT.values():
        if not a.mod and not a.standin:
            seen.add(("p", a.pydcs))
    for kind, name in sorted(seen):
        if find_class(kind, name) is None:
            problems.append(f"Unknown {dict(v='vehicle', p='aircraft', s='ship', t='static object')[kind]} '{name}'. "
                            f"Closest: {unitnames.closest(name, _index(kind))}")
    for m in MAPS.values():
        if not hasattr(terrain_mod, m.terrain_class):
            problems.append(f"Map '{m.display}' is not in this pydcs ({m.terrain_class}); it is hidden.")
    return problems


def dump_names():
    """{'vehicles': [...], 'planes': [...], 'ships': [...]} of the class names pydcs offers."""
    return {"vehicles": sorted(_index("v")[0]), "planes": sorted(_index("p")[0]),
            "ships": sorted(_index("s")[0]), "statics": sorted(_index("t")[0])}


def airbase_names(map_key):
    return sorted(_terrain(map_key).airports)


def list_airbases(map_key):
    t = _terrain(map_key)
    return [f"{name}  [{getattr(ap, 'coalition', '?')}]" for name, ap in sorted(t.airports.items())]


def _pick_airbase(airports, wanted, default):
    """Exact name, else case-insensitive / substring match, else None."""
    for cand in (wanted, default):
        if not cand:
            continue
        if cand in airports:
            return cand, ""
        low = cand.lower()
        for n in airports:
            if n.lower() == low:
                return n, ""
        for n in sorted(airports):
            if low in n.lower() or n.lower() in low:
                return n, f"Airbase '{cand}' not found exactly; using '{n}'."
    return None, ""


# ---- building ---------------------------------------------------------------

def _country_class(choice):
    from .countries import pydcs_class
    return pydcs_class(countries, choice)


def _apply_liveries(m, rng, warnings):
    """Give every aircraft type in a country one random livery for that country, used by all
    of that country's flights of that type."""
    chosen, missing = {}, set()
    for coalition in m.coalition.values():
        for country in coalition.countries.values():
            for group in list(getattr(country, "plane_group", [])):
                for u in group.units:
                    ptype = getattr(u, "unit_type", None)
                    if ptype is None:
                        continue
                    key = (country.name, ptype.id)
                    if key not in chosen:
                        ids = livery_ids(ptype, country.name)
                        chosen[key] = rng.choice(sorted(ids)) if ids else None
                        if not ids:
                            missing.add(f"{ptype.id}/{country.name}")
                    if chosen[key]:
                        u.livery_id = chosen[key]
    if missing and len(missing) == len(chosen):
        from . import liveryscan
        where = liveryscan.install_dirs()
        warnings.append("No liveries found for: " + ", ".join(sorted(missing)[:6])
                        + ". Aircraft keep their default skins. "
                        + ("DCS was found at " + str(where[0]) + " but has no liveries for these."
                           if where else "DCS's install folder was not found: put its path (for example "
                           "C:\\Program Files\\Eagle Dynamics\\DCS World) in a text file named "
                           "dcs_path.txt next to start.bat."))


def _task(*names):
    for n in names:
        t = getattr(dcs.task, n, None)
        if t is not None:
            return t
    return None


_ROLE_TASK = {"cap": ("CAP",), "cas": ("CAS",), "strike": ("GroundAttack", "CAS"),
              "sead": ("SEAD",), "dead": ("SEAD", "GroundAttack"),
              "intercept": ("Intercept", "CAP"), "naval": ("AntishipStrike", "GroundAttack")}




def _ring_pos(ab_pos, sea_pts, rng, lo_m, hi_m, on_land=None):
    """A point lo..hi metres from an airfield, on land (checked against real coastline if we have it)."""
    near = None
    if sea_pts:
        n = min(sea_pts, key=lambda p: ab_pos.distance_to_point(p))
        if ab_pos.distance_to_point(n) < 80 * NM:
            near = n
    for attempt in range(16):
        dist = rng.uniform(lo_m, hi_m)
        if near is not None and attempt < 8:
            bearing = (near.heading_between_point(ab_pos) + rng.uniform(-80, 80)) % 360
        else:
            bearing = rng.uniform(0, 360)
        pt = ab_pos.point_from_heading(bearing, dist)
        if on_land is None or on_land(pt):
            return pt
    return ab_pos.point_from_heading(rng.uniform(0, 360), 350.0)


def _field_pos(airbase, rng, on_land, along_m, lat_lo, lat_hi, geom=None):
    """A point beside the runway: along_m either way along it, lat_lo..lat_hi metres off to one side.

    With real runway geometry (see runways.py) the spread is measured from the runway's middle and
    limited to its length. Otherwise pydcs gives only a heading, so the spread stays modest."""
    ab = airbase.position
    hdg = None
    origin = ab
    if geom is not None:
        origin, hdg = geom["mid"], geom["heading"]
        along_m = min(along_m, geom["length"] / 2 + 250.0)
    else:
        for rw in getattr(airbase, "runways", []):
            try:
                hdg = rw.main.heading % 360
                break
            except Exception:  # noqa: BLE001
                continue
    for _ in range(16):
        if hdg is None:
            pt = ab.point_from_heading(rng.uniform(0, 360), rng.uniform(300, 900))
        else:
            side = rng.choice((90, -90))
            pt = origin.point_from_heading((hdg + (180 if rng.random() < 0.5 else 0)) % 360,
                                           rng.uniform(0, along_m))
            pt = pt.point_from_heading((hdg + side) % 360, rng.uniform(lat_lo, lat_hi))
        if on_land is None or on_land(pt):
            return pt
    return ab.point_from_heading(rng.uniform(0, 360), 400.0)


def _drive(vg, points, kts):
    """Give a vehicle group a road route through `points` at about `kts` knots."""
    pa = getattr(getattr(dcs, "point", None), "PointAction", None)
    road = getattr(pa, "OnRoad", None) if pa is not None else None
    kw = {"move_formation": road} if road is not None else {}
    for p in points:
        try:
            vg.add_waypoint(p, speed=float(kts) * KT, **kw)       # pydcs wants km/h here
        except TypeError:
            vg.add_waypoint(p, **kw)


def _build_airfield_targets(m, plan, ab, country, rng, on_land, geom_of, warnings):
    """Aircraft parked on the ramp of the enemy airfield the strike is aimed at."""
    st = dcs.mission.StartType
    fighters = [c for _d, c in plan.era.faction(plan.enemy_side).fighters]
    classes = [c for c in (find_class("p", n) for n in fighters) if c is not None]
    if not classes:
        warnings.append("Airfield attack: no enemy aircraft types your pydcs knows to park there.")
        return 0
    made, no_slot = 0, 0
    for i in range(rng.randint(3, 4)):
        cls = rng.choice(classes)
        size = rng.choice([2, 2, 3])
        try:
            fg = m.flight_group_from_airport(country, f"Parked target {i + 1}", cls, ab,
                                             group_size=size, start_type=st.Cold)
        except Exception as e:  # noqa: BLE001
            if "parking" in str(e).lower() or "Parking" in type(e).__name__:
                no_slot += 1
            else:
                warnings.append(f"parked target {i + 1} failed ({type(e).__name__}: {e})")
            continue
        try:
            fg.uncontrolled = True
        except Exception:  # noqa: BLE001
            pass
        made += size
    if no_slot:
        warnings.append(f"{no_slot} parked target groups were left out: the airfield has no free parking.")
    return made


def _build_airfield_aaa(m, plan, ab, country, rng, on_land, geom_of, find_class):
    """Anti-aircraft guns beside the enemy airfield (only when the era has any and war is on)."""
    if ab is None or plan.request.posture.value != "active_war":
        return
    guns = list(plan.era.faction(plan.enemy_side).aaa)
    if not guns:
        return
    n = 1 if plan.request.defences == "light" else 2
    for i in range(n):
        disp, cname, count = rng.choice(guns)
        cls = find_class("v", cname)
        if cls is None:
            continue
        pos = _field_pos(ab, rng, on_land, 900, 250, 700, geom_of(ab, None))
        vg = m.vehicle_group(country, f"Airfield AAA {i + 1} - {disp}", cls, pos,
                             heading=int(rng.uniform(0, 360)), group_size=max(2, count))
        layouts_ok = getattr(vg, "units", None)
        if layouts_ok:
            for k, u in enumerate(vg.units):
                u.position.x = pos.x + (k % 2) * 40 - 20
                u.position.y = pos.y + (k // 2) * 40


def _from_airport_with_fallback(m, country, fp, ptype, airbase, start_type, kw, st, warnings,
                                on_runway=None):
    """Start a flight at the airfield. Small fields run out of parking, so if the full flight does
    not fit, try fewer aircraft, then a runway start, rather than stopping the whole mission."""
    attempts = [(fp.size, start_type)]
    attempts += [(n, start_type) for n in range(fp.size - 1, 0, -1)]
    if start_type != st.Runway:
        attempts += [(fp.size, st.Runway), (1, st.Runway)]
    last = None
    for size, stype in attempts:
        try:
            fg = m.flight_group_from_airport(country, fp.callsign, ptype, airbase,
                                             group_size=size, start_type=stype, **kw)
        except Exception as e:  # noqa: BLE001 - pydcs raises NoParkingSlotError
            if "parking" in str(e).lower() or "Parking" in type(e).__name__:
                last = e
                continue
            raise
        if size != fp.size or stype != start_type:
            what = []
            if size != fp.size:
                what.append(f"{size} aircraft instead of {fp.size}")
            if stype != start_type:
                what.append("a runway start")
                if on_runway is not None:
                    on_runway.add(fp.callsign)
            warnings.append(f"{fp.callsign}: {airbase.name} has no free parking for it, so it starts with "
                            + " and ".join(what) + ".")
            fp.size = size
        return fg
    raise last if last is not None else RuntimeError("could not place the flight")


def fit_flights_to_parking(plan, airbase, resolve, installed, warnings):
    """Count the airfield's free parking for each flight, in build order, and trim a flight that
    would not fit, so the briefing already shows the real numbers. A flight with no spot at all is
    left alone: the build falls back to a runway start for it."""
    used = set()
    for fp in plan.flights:
        if getattr(fp, "airborne", False):
            continue
        spec = AIRCRAFT.get(fp.aircraft_key)
        try:
            ptype, _note = resolve(spec if spec else fp.pydcs_name, installed)
            free = [s_ for s_ in airbase.free_parking_slots(ptype) if id(s_) not in used
                    and getattr(s_, "crossroad_idx", None) not in used]
        except Exception:  # noqa: BLE001 - unknown airfield data: leave the plan alone
            return
        take = free[:max(0, fp.size)]
        used.update(getattr(s_, "crossroad_idx", id(s_)) for s_ in take)
        used.update(id(s_) for s_ in take)
        if take and len(take) < fp.size:
            warnings.append(f"{fp.callsign}: {airbase.name} only has parking for {len(take)} of "
                            f"{fp.size} aircraft, so the flight is {len(take)}.")
            fp.size = len(take)


def _keep_on_land(units, anchor, on_land, terrain, margin_m=250.0):
    """Pull any vehicle that ended up in (or within margin_m of) the sea back toward the group's
    anchor. The coastline data is coarse, so land has to be a little way off the shore too.
    Returns how many units were moved."""
    moved = 0
    for u in units:
        def dry(x, y):
            if not on_land(dcs.mapping.Point(x, y, terrain)):
                return False
            dx, dy = x - anchor.x, y - anchor.y
            d = math.hypot(dx, dy) or 1.0
            return on_land(dcs.mapping.Point(x + dx / d * margin_m, y + dy / d * margin_m, terrain))
        x0, y0 = u.position.x, u.position.y
        if dry(x0, y0):
            continue
        for t in (0.8, 0.6, 0.4, 0.2, 0.0):
            x, y = anchor.x + (x0 - anchor.x) * t, anchor.y + (y0 - anchor.y) * t
            if t == 0.0 or dry(x, y):
                u.position.x, u.position.y = x, y
                moved += 1
                break
    return moved


def _inline_script(lua):
    """A 'do script' action carrying the Lua text itself. pydcs stores the text as a dictionary
    key, which DCS does not look up for scripts: it runs the key's name as code and reports
    "'=' expected near <eof>". DCS wants the source inline in the action."""
    class _InlineScript(dcs.action.DoScript):
        def dict(self):
            return {"predicate": self.predicate, "text": lua}
    return _InlineScript(dcs.translation.String(lua))


def _frontline_script(m, plan, land_place, rng):
    """Burning vehicles and the odd shell in the gap between the armies (a Lua trigger script)."""
    fl = plan.frontline
    pts = []
    for _ in range(11):
        b, d = _offset(fl.bearing_deg, fl.distance_nm, fl.heading_deg, rng.uniform(-7.5, 7.5))
        b, d = _offset(b, d, (fl.heading_deg + 90) % 360, rng.uniform(-0.6, 0.6))   # inside the 1.4 nm gap
        p = land_place(b, d)
        pts.append((p.x, p.y))
    lua = effects.frontline_lua(pts, seed=plan.request.seed % 7)
    trig = dcs.triggers.TriggerOnce(dcs.triggers.Event.NoEvent, "Frontline fires")
    trig.rules.append(dcs.condition.TimeAfter(5))
    trig.actions.append(_inline_script(lua))
    m.triggerrules.triggers.append(trig)


def _awacs_kill_calls(m, plan, me, warnings):
    """The AWACS calls our flights' kills ("Hammer one, Overlord. Splash one."), as a voice clip
    when Windows speech is available and always as on-screen text."""
    awacs = next((sa for sa in plan.support if sa.kind == "awacs"), None)
    if awacs is None:
        return
    words = awacs.callsign.split()
    name = " ".join(w for w in words if not any(ch.isdigit() for ch in w)) or awacs.callsign
    flights = [f.callsign for f in plan.flights]
    clips = callouts.plan_clips(flights, name)
    folder = tempfile.mkdtemp(prefix="dcsgen_voice_")
    made = callouts.synthesise(clips, folder)
    for fn in made:
        m.map_resource.add_resource_file(os.path.join(folder, fn))
    if not made:
        warnings.append("No Windows speech voice was available, so the AWACS kill calls are text only.")
    lua = callouts.kill_call_lua(clips, made, me)
    trig = dcs.triggers.TriggerOnce(dcs.triggers.Event.NoEvent, "AWACS kill calls")
    trig.rules.append(dcs.condition.TimeAfter(2))
    trig.actions.append(_inline_script(lua))
    m.triggerrules.triggers.append(trig)


def _first_class(kind, names):
    for n in names:
        cls = find_class(kind, n)
        if cls is not None:
            return cls
    return None


def _build_ambient(m, plan, airbase, start_pos, target_pos, side_country, rng, warnings, sea_pts=(), on_land=None, geom_of=None):
    """Add the Ambient entries. Every item is optional: one that fails is skipped, not fatal."""
    st = dcs.mission.StartType

    def _try(what, fn):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - dressing only
            warnings.append(f"{what} failed ({type(e).__name__}: {e})")
            return None

    # rear of the field = away from the target; helicopter traffic uses that side
    back = (start_pos.heading_between_point(target_pos) + 180) % 360
    missing, made, no_slot = set(), 0, 0
    _g = (lambda ab: geom_of(ab, None)) if geom_of else (lambda ab: None)
    for a in plan.ambient:
        country = side_country[a.side]
        if a.kind in ("vehicle", "aaa"):
            cls = _first_class("v", a.candidates)
            if cls is None:
                missing.add(a.candidates[0])
                continue
            if a.kind == "aaa":
                pos = _field_pos(airbase, rng, on_land, 1500, 400, 750, _g(airbase))
            elif "fuel" in a.name.lower():
                pos = _field_pos(airbase, rng, on_land, 500, 220, 320, _g(airbase))
            else:
                pos = _field_pos(airbase, rng, on_land, 1200, 250, 450, _g(airbase))
            if _try(f"airfield {a.name}", lambda: m.vehicle_group(
                    country, a.name, cls, pos, heading=a.heading_deg, group_size=a.count)) is not None:
                made += 1
        elif a.kind == "parked":
            cls = _first_class("p", a.candidates) or _first_class("h", a.candidates)
            if cls is None:
                missing.add(a.candidates[0])
                continue
            try:
                fg = m.flight_group_from_airport(country, a.name, cls, airbase, group_size=1,
                                                 start_type=st.Cold)
            except Exception as e:  # noqa: BLE001
                fg = None
                if "parking" in str(e).lower() or "Parking" in type(e).__name__:
                    no_slot += 1
                else:
                    warnings.append(f"parked {a.name} failed ({type(e).__name__}: {e})")
            if fg is not None:
                _try(f"uncontrolled {a.name}", lambda fg=fg: setattr(fg, "uncontrolled", True))
                made += 1
        elif a.kind == "heli":
            cls = _first_class("h", a.candidates)
            if cls is None:
                missing.add(a.candidates[0])
                continue
            task = (_task("CAS") if a.role == "cas" else _task("Transport", "CAS"))
            kw = {"maintask": task} if task else {}
            out_pos = airbase.position.point_from_heading(
                (back + rng.uniform(-50, 50)) % 360, rng.uniform(9, 16) * NM)

            def make(a=a, cls=cls, out_pos=out_pos, kw=kw, country=country):
                if a.role == "arrival":            # already inbound, landing shortly
                    fg = m.flight_group_inflight(country, a.name, cls, out_pos, altitude=int(600 * FT),
                                                 speed=int(95 * KT), group_size=a.count, **kw)
                    fg.add_waypoint(airbase.position, int(300 * FT), int(80 * KT))
                else:                               # takes off, flies a short leg, comes back
                    fg = m.flight_group_from_airport(country, a.name, cls, airbase, group_size=a.count,
                                                     start_type=st.Cold, **kw)
                    fg.add_waypoint(out_pos, int(500 * FT), int(95 * KT))
                    fg.start_time = a.start_min * 60
                if hasattr(fg, "land_at"):
                    fg.land_at(airbase)
                return fg
            if _try(f"helicopter {a.name}", make) is not None:
                made += 1
    if no_slot:
        warnings.append(f"{no_slot} parked aircraft were left out: this airfield has no free parking "
                        "slots for them (the player flights take priority).")
    if missing:
        warnings.append("Airfield dressing skipped these types your pydcs does not know: "
                        + ", ".join(sorted(missing)))
    return made


def _orbit_circle():
    """The circle orbit pattern; pydcs 1.0 calls the enum OrbitPattern, older versions Pattern."""
    act = dcs.task.OrbitAction
    return getattr(act, "OrbitPattern", getattr(act, "Pattern", None)).Circle


def _runway_line_up(fg, airbase, toward_pos, back_m=1200.0, geom_of=None):
    """Move a runway-start group from the middle of the runway to the departure end, facing along it.

    Picks the runway heading closest to the direction of the first leg, then lines the aircraft up
    behind the airfield reference point (pydcs gives no runway length, so the distance is an estimate
    for a typical military runway, kept short of the real threshold)."""
    want = airbase.position.heading_between_point(toward_pos)
    best = None
    for rw in getattr(airbase, "runways", []):
        for ap in (rw.main, rw.opposite):
            diff = abs((ap.heading - want + 180) % 360 - 180)
            if best is None or diff < best[0]:
                best = (diff, ap.heading)
    if best is None:
        return None
    hdg = best[1] % 360
    geom = geom_of(airbase, hdg) if geom_of else None
    thr = None
    if geom is not None and geom.get("exact"):                 # real runway: start at the threshold the heading takes off from
        ends = [(geom["a"], geom["b"]), (geom["b"], geom["a"])]
        thr, other = min(ends, key=lambda e: abs((e[0].heading_between_point(e[1]) - hdg + 180) % 360 - 180))
        hdg = thr.heading_between_point(other) % 360
    for i, u in enumerate(fg.units):
        back = back_m + 40.0 * i
        side = 0.0 if i == 0 else (9.0 if i % 2 else -9.0)
        if thr is not None:
            p = thr.point_from_heading(hdg, 80.0 + (back - 1200.0))
        else:
            p = airbase.position.point_from_heading((hdg + 180) % 360, back)
        p = p.point_from_heading((hdg + 90) % 360, side)
        u.position.x, u.position.y = p.x, p.y
        u.heading = hdg
    lead = fg.units[0]
    fg.points[0].position.x, fg.points[0].position.y = lead.position.x, lead.position.y
    return hdg


def build_mission(plan, out_path, kneeboard=True, pdf_path=None):
    """Write the .miz. Returns a BuildResult (path, final briefing, warnings)."""
    warnings = []

    def _try(what, fn):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - optional feature, report and carry on
            warnings.append(f"{what} failed ({type(e).__name__}: {e})")
            return None

    req, era = plan.request, plan.era
    me, foe = plan.player_side, plan.enemy_side
    rng = random.Random(req.seed)
    installed = mods.scan_installed_mods()
    m = dcs.Mission(_terrain(req.map_key))

    side_country = {}
    for s in ("blue", "red"):
        choice = plan.countries.get(s) if plan.countries else None
        cls = _country_class(choice) if choice else None
        if cls is None:
            if choice:
                warnings.append(f"Country '{choice.display}' is not in your pydcs; using the era's default "
                                f"{era.faction(s).adjective} country instead.")
            cls = getattr(countries, era.faction(s).country)
        m.coalition[s].add_country(cls())
        side_country[s] = m.country(cls().name)
    m.start_time = plan.start_time

    # ---- geometry
    airports = m.terrain.airports
    default_ab = MAPS[req.map_key].default_airbase
    want_name = req.start.name if req.start.kind == "airbase" else ""
    ab_name, note = _pick_airbase(airports, want_name, default_ab)
    if note:
        warnings.append(note)
    if not ab_name:
        own = [n for n, a in airports.items() if getattr(a, "coalition", "") == me]
        ab_name = sorted(own or airports)[0]
    airbase = airports[ab_name]
    start_pos = airbase.position

    sea_heading = 270
    if plan.carrier:
        near = [a for a in airports.values() if a is not airbase
                and airbase.position.distance_to_point(a.position) < 150 * NM]
        if near:
            cx = sum(a.position.x for a in near) / len(near)
            cy = sum(a.position.y for a in near) / len(near)
            sea_heading = (start_pos.heading_between_point(
                dcs.mapping.Point(cx, cy, m.terrain)) + 180) % 360
        start_pos = airbase.position.point_from_heading(sea_heading, 50 * NM)

    want = plan.start_distance_nm * NM
    others = [a for a in airports.values() if a is not airbase]
    sea_pts = []
    for lat, lng in MAPS[req.map_key].sea:
        try:
            sea_pts.append(dcs.mapping.Point.from_latlng(dcs.mapping.LatLng(lat, lng), m.terrain))
        except Exception:  # noqa: BLE001
            pass
    have_coast = coast.has(req.map_key)

    def on_land(pt):
        """Real-coastline land test; True when we have no coastline data (then other rules apply)."""
        if not have_coast:
            return True
        try:
            lat, lng = navinfo.point_latlng(pt)
            res = coast.is_land(req.map_key, lat, lng)
            return True if res is None else res
        except Exception:  # noqa: BLE001
            return True

    _geoms = {}

    def geom_of(ab, heading):
        """Real runway geometry for an airfield (None if unknown): mid point, heading, length, width, ends."""
        if not runways.available():
            return None
        if heading is None:
            for rw in getattr(ab, "runways", []):
                try:
                    heading = rw.main.heading
                    break
                except Exception:  # noqa: BLE001
                    continue
        key = (getattr(ab, "name", id(ab)), None if heading is None else round(heading) % 180)
        if key not in _geoms:
            _geoms[key] = None
            try:
                lat, lng = navinfo.point_latlng(ab.position)
                rg = runways.find(lat, lng, heading)
                if rg is None and heading is not None:
                    est = runways.find_estimate(lat, lng, heading)
                    if est is not None:          # length only: centre on the airfield point
                        _geoms[key] = {"mid": ab.position, "heading": float(heading) % 360,
                                       "length": est["length"], "width": est["width"], "exact": False}
                    elif est is None and rg is None:   # nothing known: guess from the name
                        gl = runways.guess_length(getattr(ab, "name", ""))
                        if gl is not None:
                            _geoms[key] = {"mid": ab.position, "heading": float(heading) % 360,
                                           "length": gl, "width": 45.0, "exact": False, "guess": True}
                if rg is not None:
                    LL, Pt = dcs.mapping.LatLng, dcs.mapping.Point
                    a = Pt.from_latlng(LL(*rg["a"]), m.terrain)
                    b = Pt.from_latlng(LL(*rg["b"]), m.terrain)
                    _geoms[key] = {"a": a, "b": b, "length": rg["length"], "width": rg["width"],
                                   "mid": Pt((a.x + b.x) / 2, (a.y + b.y) / 2, m.terrain),
                                   "heading": a.heading_between_point(b) % 360, "exact": True}
            except Exception:  # noqa: BLE001
                _geoms[key] = None
        return _geoms[key]

    if sea_pts and not have_coast:
        warnings.append("Coastline data is not installed, so units near a coast may be placed in the sea. "
                        "Run fetch_coast.bat once (needs internet) to fix that.")
    target_airfield = None     # set when the strike target is an enemy airfield
    inland = None          # compass heading pointing away from the sea at the target, when coastal
    if req.mission_type is M.NAVAL:
        plan.airfield_attack = False
        # the target sits on open water: pick the map's sea point whose range suits the plan
        pts = []
        for lat, lng in MAPS[req.map_key].sea:
            try:
                pts.append(dcs.mapping.Point.from_latlng(dcs.mapping.LatLng(lat, lng), m.terrain))
            except Exception as e:  # noqa: BLE001
                warnings.append(f"Sea point {lat},{lng} unusable ({type(e).__name__}: {e}).")
        if not pts:
            raise RuntimeError("No usable open-sea position on this map for a Naval strike.")
        target_pos = min(pts, key=lambda p: abs(start_pos.distance_to_point(p) - want))
        heading_out = start_pos.heading_between_point(target_pos)
        plan.start_distance_nm = start_pos.distance_to_point(target_pos) / NM
        if abs(plan.start_distance_nm * NM - want) > 0.5 * want:
            warnings.append(f"The nearest open water is {plan.start_distance_nm:.0f} nm from your start "
                            f"(planned {want / NM:.0f} nm), so the flight time will differ from the plan.")
    else:
        ranked = sorted(others, key=lambda a: abs(start_pos.distance_to_point(a.position) - want))
        pick = rng.choice(ranked[:3]) if ranked else airbase
        # Anchor the target on a real airfield (airfields are always on land) and nudge it a few
        # miles inland, so a coastal map never puts the target group in the sea.
        target_pos = pick.position
        if plan.airfield_attack and not ranked:          # nowhere else to attack: an ordinary strike
            plan.airfield_attack, plan.objective = False, plan.objective_normal
        if plan.airfield_attack:                         # the target IS the airfield
            target_airfield = pick
        else:
            away = None
            if sea_pts:
                nearest = min(sea_pts, key=lambda p: pick.position.distance_to_point(p))
                if pick.position.distance_to_point(nearest) < 120 * NM:
                    away = (nearest.heading_between_point(pick.position))
                    inland = away
            if away is None:
                away = start_pos.heading_between_point(pick.position)
            target_pos = pick.position.point_from_heading(away, 4 * NM)
            if not on_land(target_pos):
                target_pos = pick.position
        heading_out = start_pos.heading_between_point(target_pos)
        actual = start_pos.distance_to_point(target_pos)
        if abs(actual - want) > 0.35 * want:
            warnings.append(f"The nearest suitable land target is {actual / NM:.0f} nm from your start "
                            f"(planned {want / NM:.0f} nm), so the flight time will differ from the plan.")
        plan.start_distance_nm = actual / NM
    rotate = (((heading_out + 180) % 360) - plan.approach_bearing) % 360
    plan.rotation_deg = rotate
    plan.geometry_final = True

    def place(bearing, dist_nm):
        if bearing == 0 and dist_nm == 0:
            return target_pos
        return target_pos.point_from_heading((bearing + rotate) % 360, dist_nm * NM)

    def land_place(bearing, dist_nm):
        """Like place(), but on a coast a point on the sea side of the target is mirrored inland."""
        pos = place(bearing, dist_nm)
        if bearing == 0 and dist_nm == 0:
            return pos
        if have_coast:                       # real coastline: pull a wet point back toward the target
            if on_land(pos):
                return pos
            for t in (0.85, 0.7, 0.55, 0.4, 0.25, 0.1):
                q = dcs.mapping.Point(target_pos.x + (pos.x - target_pos.x) * t,
                                      target_pos.y + (pos.y - target_pos.y) * t, m.terrain)
                if on_land(q):
                    return q
            return target_pos
        if inland is None:
            return pos
        h = (bearing + rotate) % 360
        along = dist_nm * math.cos(math.radians(h - inland))     # nm toward the land (+) or sea (-)
        if along < -0.3:
            h2 = (2 * inland + 180 - h) % 360                    # mirror across the coast-parallel line
            return target_pos.point_from_heading(h2, dist_nm * NM)
        return pos

    # ---- real sun times: the map's own clock offset and the objective's real position
    try:
        tlat, tlng = navinfo.point_latlng(target_pos)
        off = getattr(m.terrain, "utc_offset", None)
        off = MAPS[req.map_key].utc_offset if off is None else off
        if hasattr(off, "utcoffset"):                      # a datetime.timezone
            off = off.utcoffset(None)
        if hasattr(off, "total_seconds"):
            off = off.total_seconds() / 3600
        plan.start_time = conditions.start_clock(plan.time_of_day, tlat, tlng, float(off),
                                                 plan.start_time)
        m.start_time = plan.start_time
    except Exception as e:  # noqa: BLE001 - keep the planner's estimate
        warnings.append(f"Could not refine the start time ({type(e).__name__}: {e}).")

    # ---- AWACS and tanker (AI racetracks); the in-game callsign goes back into the briefing
    for sa in plan.support:
        cls = find_class("p", sa.pydcs_name)
        if cls is None:
            warnings.append(f"{sa.display} is not in your pydcs, so the {sa.kind} was left out.")
            continue
        def make(sa=sa, cls=cls):
            pos = place(sa.bearing_deg, sa.distance_nm)
            common = dict(race_distance=int(sa.race_nm * NM), heading=(sa.heading_deg + rotate) % 360,
                          altitude=int(sa.altitude_ft * FT), speed=int(sa.speed_kts * KT),
                          frequency=sa.frequency)
            if sa.kind == "awacs":
                fg = m.awacs_flight(side_country[me], f"{sa.callsign} AWACS", cls, None, pos, **common)
            else:
                fg = m.refuel_flight(side_country[me], f"{sa.callsign} Tanker", cls, None, pos,
                                     tacanchannel=sa.tacan, **common)
            raw = (getattr(fg.units[0], "callsign_dict", {}) or {}).get("name", "")
            digits = "".join(ch for ch in raw if ch.isdigit())
            word = raw.rstrip("0123456789")
            if word and len(digits) >= 2:
                sa.callsign = f"{word} {digits[0]}-{digits[1]}"
            return fg
        _try(f"{sa.kind} {sa.display}", make)
    _try("AWACS kill calls", lambda: _awacs_kill_calls(m, plan, me, warnings))

    # ---- where things are, for the briefing
    try:
        nav = {"target": navinfo.point_latlng(target_pos), "base": plan.carrier.display if plan.carrier else ab_name,
               "bearing": start_pos.heading_between_point(target_pos) % 360,
               "range_nm": start_pos.distance_to_point(target_pos) / NM}
        if plan.sead_target is not None:
            nav["sead"] = navinfo.point_latlng(land_place(plan.sead_target.bearing_deg, plan.sead_target.distance_nm))
        plan.nav = nav
    except Exception as e:  # noqa: BLE001
        warnings.append(f"Could not work out target coordinates ({type(e).__name__}: {e}).")

    # ---- parking: fit the flights to what the airfield really has before the briefing is written
    if plan.carrier is None and req.start_state != "runway":
        _try("parking count", lambda: fit_flights_to_parking(plan, airbase, resolve_aircraft,
                                                           installed, warnings))

    # ---- briefing with the real geometry (headings now mean something)
    brief = compose(plan)

    # ---- carrier
    carrier_group = None
    if plan.carrier:
        ship_cls = find_class("s", plan.carrier.pydcs_name)
        if ship_cls is None:
            warnings.append(f"Carrier '{plan.carrier.pydcs_name}' not found in pydcs; starting from "
                            f"{ab_name} instead.")
            start_pos = airbase.position
        else:
            carrier_group = m.ship_group(side_country[me], plan.carrier.display, ship_cls,
                                         start_pos, heading=(sea_heading + 180) % 360)

    # ---- the package's flights
    player_fg = None
    on_runway = set()        # flights that had to start on the runway because there was no parking
    player_types = {}
    for fp in plan.flights:
        spec = AIRCRAFT.get(fp.aircraft_key)
        ptype, note = resolve_aircraft(spec if spec else fp.pydcs_name, installed)
        if note and note not in warnings:
            warnings.append(note)
        player_types[ptype.id] = ptype
        maintask = _task(*_ROLE_TASK.get(fp.role.value, ("CAP",)))
        kw = {"maintask": maintask} if maintask else {}
        st = dcs.mission.StartType
        start_type = {"cold": st.Cold, "hot": st.Warm, "runway": st.Runway}[req.start_state]
        if getattr(fp, "runway_start", False):
            start_type = st.Runway
        if carrier_group is not None and req.start_state == "runway":
            start_type = st.Warm      # a carrier has no runway start; hot is the closest
        fg = None
        if getattr(fp, "airborne", False) and len(fp.waypoints) > 1:
            def spawn_airborne(fp=fp, ptype=ptype, kw=kw):
                w1 = fp.waypoints[1]
                p1 = place(w1.bearing_deg, w1.distance_nm)
                pos = start_pos.point_from_heading(start_pos.heading_between_point(p1), 4 * NM)
                return m.flight_group_inflight(
                    side_country[me], fp.callsign, ptype, pos,
                    altitude=int(max(w1.altitude_ft, 5000) * FT), speed=int(max(w1.speed_kts, 300) * KT),
                    group_size=fp.size, **kw)
            fg = _try(f"airborne start for {fp.callsign}", spawn_airborne)
        if fg is None and carrier_group is not None:
            fg = _try(f"carrier start for {fp.callsign}", lambda: m.flight_group_from_unit(
                side_country[me], fp.callsign, ptype, carrier_group, group_size=fp.size,
                start_type=start_type, **kw))
        if fg is None:
            fg = _from_airport_with_fallback(m, side_country[me], fp, ptype, airbase, start_type,
                                             kw, st, warnings, on_runway)
        if fp.pylons:
            _bad = _try(f"loadout for {fp.callsign}", lambda: apply_pylons(fg, ptype, fp.pylons))
            if _bad:
                warnings.append(f"{fp.callsign}: could not load {', '.join(_bad)}; those stations stay empty.")
        try:
            # Only the flight you fly gets a player slot. A supporting flight with an empty player
            # slot waits for its leader and never takes off, so those stay fully AI.
            if fp.primary:
                fg.units[0].set_client()
                player_fg = fg
        except Exception as e:  # noqa: BLE001 - an AI-only type must not stop the mission
            warnings.append(f"{fp.callsign}: {ptype.id} is not human-flyable in your pydcs ({e}); "
                            "that flight runs as AI with no player slot.")
        if ((req.start_state == "runway" or fp.callsign in on_runway
             or getattr(fp, "runway_start", False)) and carrier_group is None
                and not getattr(fp, "airborne", False)):
            _try(f"runway line-up for {fp.callsign}", lambda fg=fg, fp=fp: _runway_line_up(
                fg, airbase, place(fp.waypoints[1].bearing_deg, fp.waypoints[1].distance_nm)
                if len(fp.waypoints) > 1 else target_pos, 1200.0 + 220.0 * plan.flights.index(fp), geom_of))
        for wp in fp.waypoints[1:-1]:
            fg.add_waypoint(place(wp.bearing_deg, wp.distance_nm), int(wp.altitude_ft * FT),
                            int(wp.speed_kts * KT), name=wp.name)
        fg.add_waypoint(start_pos, 0, 400, name="Land")
        if fp.start_min > 0:
            _try(f"delayed start for {fp.callsign}",
                 lambda fg=fg, fp=fp: setattr(fg, "start_time", fp.start_min * 60))
        if fp.role.value == "cap":
            def add_orbit(fg=fg, fp=fp):
                idx = next((k for k, w in enumerate(fp.waypoints) if w.name == fp.key_waypoint), None)
                if idx is None or idx >= len(fg.points):
                    idx = len(fg.points) - 2
                orbit = dcs.task.OrbitAction(altitude=int(15000 * FT), pattern=_orbit_circle())
                if fp.dwell_min > 0:         # leave the station when the briefing says to
                    try:
                        orbit = dcs.task.ControlledTask(orbit)
                        orbit.stop_after_duration(int(fp.dwell_min * 60))
                    except Exception:  # noqa: BLE001 - fall back to an open-ended orbit
                        orbit = dcs.task.OrbitAction(altitude=int(15000 * FT), pattern=_orbit_circle())
                fg.points[idx].tasks.append(orbit)
            _try(f"CAP orbit for {fp.callsign}", add_orbit)

    # ---- enemy / friendly ground and air groups
    dormant, scramblers, cap_groups = [], [], []
    enemy_ab = None
    if target_airfield is not None:
        enemy_ab = target_airfield
        _try("setting enemy airbase coalition", lambda: enemy_ab.set_coalition(foe))
    elif any(g.placement == "enemy_airbase" for g in plan.groups):
        foe_ab = [a for a in airports.values() if getattr(a, "coalition", "") == foe]
        pool = foe_ab or [a for a in airports.values() if a is not airbase]
        enemy_ab = min(pool, key=lambda a: target_pos.distance_to_point(a.position))
        _try("setting enemy airbase coalition", lambda: enemy_ab.set_coalition(foe))

    skipped = set()
    for g in plan.groups:
        country = side_country[g.side]
        if g.kind == "ship":
            cls = find_class("s", g.units[0][0])
            if cls is None:
                skipped.add(g.units[0][0])
                continue
            _try(f"ship group {g.name}", lambda: m.ship_group(
                country, g.name, cls, place(g.bearing_deg, g.distance_nm),
                heading=int(g.heading_deg) % 360, group_size=g.count))
            continue
        if g.kind == "plane":
            cls = find_class("p", g.units[0][0])
            if cls is None:
                skipped.add(g.units[0][0])
                continue
            if g.tag in ("raid", "raid_escort"):
                def make_raid(g=g, cls=cls, country=country):
                    task = (dcs.task.CAP if g.tag == "raid_escort" else
                            (_task("GroundAttack") or dcs.task.CAP))
                    fg = m.flight_group_inflight(
                        country, g.name, cls, place(g.bearing_deg, g.distance_nm),
                        altitude=int(g.alt_ft * FT), speed=int(g.speed_kts * KT),
                        maintask=task, group_size=g.count)
                    for brg, dst in g.route[1:]:
                        fg.add_waypoint(place(brg, dst), int(g.alt_ft * FT), int(g.speed_kts * KT))
                    _try(f"loadout for {g.name}", lambda: apply_pylons(fg, cls, g.pylons))
                    return fg
                _try(f"raid group {g.name}", make_raid)
                continue
            if g.placement == "enemy_airbase":
                def make_scramble(g=g, cls=cls, country=country):
                    st = dcs.mission.StartType
                    foe_abs = sorted((a for a in airports.values() if getattr(a, "coalition", "") == foe),
                                     key=lambda a: enemy_ab.position.distance_to_point(a.position))
                    for ab in [enemy_ab] + [a for a in foe_abs if a is not enemy_ab][:2]:
                        for start in (st.Warm, st.Cold, st.Runway):
                            try:
                                return m.flight_group_from_airport(country, g.name, cls, ab,
                                                                   group_size=g.count, start_type=start)
                            except Exception:  # noqa: BLE001 - usually no free parking slot
                                continue
                    warnings.append(f"{g.name}: no parking at the enemy airfield, so it starts airborne "
                                    "over the field instead.")
                    return m.flight_group_inflight(
                        country, g.name, cls, enemy_ab.position, altitude=int(3000 * FT),
                        speed=int(350 * KT), maintask=dcs.task.CAP, group_size=g.count)
                fg = _try(f"scramble group {g.name}", make_scramble)
                if fg is not None:
                    _try(f"loadout for {g.name}", lambda fg=fg, cls=cls, g=g: apply_pylons(fg, cls, g.pylons))
                    _try(f"late activation for {g.name}",
                         lambda fg=fg: setattr(fg, "late_activation", True))
                    scramblers.append(fg)
            else:
                cap_fg = _try(f"CAP group {g.name}", lambda: m.flight_group_inflight(
                    country, g.name, cls, place(g.bearing_deg, g.distance_nm),
                    altitude=int(20000 * FT), speed=int(400 * KT),
                    maintask=dcs.task.CAP, group_size=g.count))
                _try(f"loadout for {g.name}", lambda: apply_pylons(cap_fg, cls, g.pylons))
                if cap_fg is not None:
                    # Without an orbit the AI flies its one waypoint and heads home. Hold the pair
                    # back until the package is nearly there, then let them loose on station.
                    _try(f"CAP orbit for {g.name}", lambda: cap_fg.points[0].tasks.append(
                        dcs.task.OrbitAction(altitude=int(20000 * FT), speed=int(400 * KT),
                                             pattern=_orbit_circle())))
                    _try(f"late activation for {g.name}",
                         lambda: setattr(cap_fg, "late_activation", True))
                    cap_groups.append(cap_fg)
            continue

        pos = land_place(g.bearing_deg, g.distance_nm)
        if target_airfield is not None and g.tag == "target":      # stores beside the runway, not on it
            pos = _field_pos(target_airfield, rng, on_land, 700, 200, 500, geom_of(target_airfield, None))
        parts = []
        for cname, n in g.units:
            cls = find_class("v", cname)
            if cls is None:
                skipped.add(cname)
            else:
                parts.append((cls, cname, n))
        if not parts:
            continue
        first_cls, _, first_n = parts[0]
        route_pts = [land_place(b, d) for b, d in g.route[1:]] if len(g.route) > 1 else []
        if route_pts:                                   # a convoy: face along its first leg
            g = replace(g, heading_deg=pos.heading_between_point(route_pts[0]) % 360)
        vg = _try(f"ground group {g.name}", lambda: m.vehicle_group(
            country, g.name, first_cls, pos, heading=g.heading_deg, group_size=first_n))
        if vg is None:
            continue
        if route_pts:
            _try(f"convoy route for {g.name}", lambda vg=vg, g=g, route_pts=route_pts: _drive(
                vg, route_pts, g.speed_kts))
        for cls, cname, n in parts[1:]:
            def add_units(cls=cls, cname=cname, n=n, vg=vg, pos=pos, g=g):
                for i in range(n):
                    u = m.vehicle(f"{g.name} {cname} {i}", cls)    # pydcs's own helper
                    u.position.x = pos.x + rng.uniform(-120, 120)
                    u.position.y = pos.y + rng.uniform(-120, 120)
                    u.heading = 0
                    vg.add_unit(u)
            _try(f"extra units for {g.name}", add_units)
        flat = [cname for _cls, cname, n in parts for _ in range(n)]
        _try(f"layout for {g.name}", lambda vg=vg, g=g, pos=pos, flat=flat: layouts.place_metres(
            g, vg.units, pos.x, pos.y, flat))
        if have_coast:
            _try(f"shore check for {g.name}", lambda vg=vg, pos=pos: _keep_on_land(
                vg.units, pos, on_land, m.terrain))
        if g.tag == "frontline" or (g.tag == "target" and plan.frontline is not None
                                    and plan.frontline.distance_nm < 1.0):
            def fight(vg=vg):
                t = vg.points[0].tasks
                t.append(dcs.task.OptROE(dcs.task.OptROE.Values.WeaponFree))
                t.append(dcs.task.OptAlarmState(2))          # red: shoot at anything in sight
                t.append(dcs.task.OptDisparseUnderFire(False))  # stand and fight, don't scatter
            _try(f"engagement orders for {g.name}", fight)
        if g.tag == "convoy":
            # also ask DCS for an "On Road" start, which drops a vehicle onto the nearest road
            def on_road(vg=vg):
                pa = dcs.point.PointAction
                vg.points[0].action = pa.OnRoad
            _try(f"road start for {g.name}", on_road)
        if g.activation.mode == "proximity":
            _try(f"late activation for {g.name}", lambda vg=vg: setattr(vg, "late_activation", True))
            dormant.append(vg)
    if skipped:
        warnings.append("Skipped units your pydcs does not know (run  dcsgen check-units): "
                        + ", ".join(sorted(skipped)))

    # ---- static objects (dressing)
    unknown_statics, placed_statics = set(), 0
    ring_ab = {"start_airbase": airbase, "enemy_airbase": enemy_ab}
    for g in plan.statics:
        cls = find_class("t", g.units[0][0])
        if cls is None:
            unknown_statics.add(g.units[0][0])
            continue
        if g.placement == "relative":
            pos = land_place(g.bearing_deg, g.distance_nm)
        else:
            ab = ring_ab.get(g.placement)
            if ab is None:
                if g.placement == "enemy_airbase":
                    foe_ab = [a for a in airports.values() if getattr(a, "coalition", "") == foe]
                    ab = min(foe_ab or others or [airbase],
                             key=lambda a: target_pos.distance_to_point(a.position))
                    ring_ab["enemy_airbase"] = ab
                else:
                    ab = airbase
            pos = _field_pos(ab, rng, on_land, 1500, 350, 800, geom_of(ab, None))
        if _try(f"static {g.name}", lambda: m.static_group(
                side_country[g.side], g.name, cls, pos, heading=int(g.heading_deg))) is not None:
            placed_statics += 1
    if unknown_statics:
        warnings.append("Skipped static objects your pydcs does not know: "
                        + ", ".join(sorted(unknown_statics)))

    def _enemy_field():
        ab = ring_ab.get("enemy_airbase") or enemy_ab
        if ab is None:
            held = [a for a in airports.values() if getattr(a, "coalition", "") == foe]
            ab = min(held, key=lambda a: target_pos.distance_to_point(a.position)) if held else None
        return ab
    _try("airfield air defence", lambda: _build_airfield_aaa(
        m, plan, _enemy_field(), side_country[foe], rng, on_land, geom_of, find_class))

    if target_airfield is not None:
        _try("airfield targets", lambda: _build_airfield_targets(
            m, plan, target_airfield, side_country[foe], rng, on_land, geom_of, warnings))
    if plan.frontline is not None:
        _try("frontline fires", lambda: _frontline_script(m, plan, land_place, rng))

    # ---- weather, season temperature
    _try("weather", lambda: _apply_weather(m, plan, rng))

    # ---- life round the player's airfield: trucks, AA guns, parked aircraft, helicopter traffic
    _try("airbase life", lambda: _build_ambient(m, plan, airbase, start_pos, target_pos,
                                                side_country, rng, warnings, sea_pts, on_land, geom_of))

    # ---- triggers
    def make_trigger(label, radius_nm, groups_to_wake):
        zone = m.triggers.add_triggerzone(target_pos, int(radius_nm * NM), hidden=False, name=label)
        trig = dcs.triggers.TriggerOnce(dcs.triggers.Event.NoEvent, label)
        if player_fg is not None:       # your flight, not any friendly tank that happens to be near
            trig.rules.append(dcs.condition.PartOfGroupInZone(player_fg.id, zone.id))
        else:
            trig.rules.append(dcs.condition.PartOfCoalitionInZone(me, zone.id))
        for grp in groups_to_wake:
            trig.actions.append(dcs.action.ActivateGroup(grp.id))
        m.triggerrules.triggers.append(trig)

    if dormant:
        _try("defence activation trigger",
             lambda: make_trigger("Defences activate", plan.activation_radius_nm, dormant))
    if cap_groups:
        def release_cap():
            when = max(1, plan.flights[0].key_min - 6) * 60
            trig = dcs.triggers.TriggerOnce(dcs.triggers.Event.NoEvent, "Enemy CAP on station")
            trig.rules.append(dcs.condition.TimeAfter(when))
            for grp in cap_groups:
                trig.actions.append(dcs.action.ActivateGroup(grp.id))
            m.triggerrules.triggers.append(trig)
        _try("enemy CAP release", release_cap)
    if scramblers:
        _try("fighter scramble trigger",
             lambda: make_trigger("Fighters scramble", plan.scramble_radius_nm, scramblers))

    _try("liveries", lambda: _apply_liveries(m, rng, warnings))

    # ---- in-game briefing text
    text = brief.as_text()
    _try("briefing text", lambda: m.set_description_text(text))
    _try("task text", lambda: (m.set_description_bluetask_text(text) if me == "blue"
                               else m.set_description_redtask_text(text)))

    out_path, moved = _save_with_fallback(m, out_path)
    if moved:
        warnings.append(moved)
    _try("mission file check", lambda: _check_mission_file(out_path))
    # DCS's mission lists read a small 'theatre' file naming the map; pydcs does not write one,
    # and without it DCS silently hides the mission.
    _try("theatre marker", lambda: _add_theatre(out_path, getattr(m.terrain, "name", "") or
                                                MAPS[req.map_key].terrain_class))

    # ---- kneeboard pages and PDF
    pages_written = 0
    if kneeboard or pdf_path:
        try:
            from . import render
            rendered = render.render_pages(plan, brief)
            if pdf_path:
                render.save_pdf(rendered, pdf_path)
            if kneeboard:
                pages_written = _inject_kneeboard(out_path, list(player_types), render.kneeboard_files(rendered))
        except ImportError as e:
            warnings.append(f"Kneeboard/PDF skipped: {e}. Install Pillow:  py -m pip install pillow")
        except Exception as e:  # noqa: BLE001
            warnings.append(f"Kneeboard/PDF failed ({type(e).__name__}: {e})")
    return BuildResult(str(out_path), brief, warnings, pages_written)


def _apply_weather(m, plan, rng):
    from dcs.weather import Weather, Wind
    from . import conditions
    cfg = conditions.WEATHER[plan.weather_key][2]
    w = m.weather
    w.name = conditions.WEATHER[plan.weather_key][0]
    w.clouds_density = cfg["density"]
    w.clouds_base = cfg["base"]
    w.clouds_thickness = cfg["thick"]
    w.clouds_iprecptns = [Weather.Preceptions.None_, Weather.Preceptions.Rain,
                          Weather.Preceptions.Thunderstorm][cfg["precip"]]
    w.visibility_distance = cfg["vis"]
    w.enable_fog = bool(cfg["fog"])
    if cfg["fog"]:
        w.fog_visibility = 800
        w.fog_thickness = 300
    direction = rng.randint(0, 359)
    kts = cfg["wind"]
    w.wind_at_ground = Wind(direction, kts)
    w.wind_at_2000 = Wind((direction + rng.randint(-25, 25)) % 360, kts + 4)
    w.wind_at_8000 = Wind((direction + rng.randint(-40, 40)) % 360, kts + 9)
    w.season_temperature = conditions.SEASON_TEMP[plan.season] + rng.uniform(-3, 3)
    if cfg["precip"]:
        w.qnh = 745


def _save_with_fallback(m, out_path):
    """Save the mission; if Windows refuses the chosen spot (a locked file, or Controlled folder
    access blocking Python), save into Documents\\dcsgen instead and say so."""
    from pathlib import Path
    out = Path(out_path)
    try:
        m.save(str(out))
        return str(out), ""
    except PermissionError as first:
        alt_dir = Path.home() / "Documents" / "dcsgen"
        alt_dir.mkdir(parents=True, exist_ok=True)
        alt = alt_dir / out.name
        try:
            m.save(str(alt))
        except PermissionError:
            raise PermissionError(
                f"Windows would not let the program write to {out.parent} or to {alt_dir}. "
                "If Windows 'Controlled folder access' is on, allow Python through it, or close "
                f"DCS if it has the file open. ({first})") from first
        return str(alt), (f"Could not write to {out.parent} (permission denied), so the mission "
                          f"was saved to {alt}. Copy it into Saved Games\\DCS\\Missions by hand.")


def _check_mission_file(miz_path):
    """Cheap sanity check for the kind of corruption that stops DCS loading a mission."""
    import re
    with zipfile.ZipFile(miz_path) as z:
        text = z.read("mission").decode("utf-8", "replace")
    bad = re.findall(r'\["(?:unitId|groupId)"\]=\s*[^\d\s-][^,\n]*', text)
    if bad:
        raise ValueError(f"mission file has {len(bad)} malformed ids, e.g. {bad[0]!r}")
    if text.count("{") != text.count("}"):
        raise ValueError("mission file has unbalanced braces")


def _add_theatre(miz_path, theatre):
    with zipfile.ZipFile(miz_path, "a", zipfile.ZIP_DEFLATED) as z:
        if "theatre" not in z.namelist():
            z.writestr("theatre", theatre)


def _inject_kneeboard(miz_path, type_ids, files):
    """Add the briefing pages to the .miz as kneeboard images for every aircraft type used.

    DCS shows images in KNEEBOARD/<aircraft type id>/IMAGES/ on the in-game kneeboard.
    """
    with zipfile.ZipFile(miz_path, "a", zipfile.ZIP_DEFLATED) as z:
        for tid in type_ids:
            for fname, data in files:
                z.writestr(f"KNEEBOARD/{tid}/IMAGES/{fname}", data)
    return len(files)



def dump_land_probe():
    """Report whether this pydcs can tell land from water (for diagnosing coastal placement)."""
    import inspect
    import pkgutil
    out = []
    try:
        import importlib.metadata as md
        out.append(f"pydcs version: {md.version('pydcs')}")
    except Exception as e:  # noqa: BLE001
        out.append(f"pydcs version: unknown ({e})")
    words = ("land", "water", "sea", "height", "elev", "altit", "surface", "ground", "coast", "terrain",
             "is_", "contains", "inside")

    def attrs(obj, label):
        names = sorted(n for n in dir(obj) if not n.startswith("__") and any(w in n.lower() for w in words))
        out.append(f"{label}: {names}")

    out.append("")
    out.append("## pydcs modules whose names look relevant")
    try:
        names = [m.name for m in pkgutil.walk_packages(dcs.__path__, "dcs.")]
        out.append(str([n for n in names if any(w in n.lower() for w in
                                                ("land", "water", "height", "terrain", "mapping", "geo", "proj"))]))
    except Exception as e:  # noqa: BLE001
        out.append(f"could not list modules ({e})")
    out.append("")
    out.append("## data files shipped inside pydcs (not .py)")
    try:
        files = []
        for root, _d, fs in os.walk(Path(dcs.__file__).parent):
            for f in fs:
                if not f.endswith((".py", ".pyc")):
                    files.append(str(Path(root, f).relative_to(Path(dcs.__file__).parent)))
        out.append(f"{len(files)} files; sample: {sorted(files)[:40]}")
    except Exception as e:  # noqa: BLE001
        out.append(f"could not list ({e})")

    probes = ("is_land", "is_water", "is_sea", "land_type", "get_land_type", "surface_type", "get_height",
              "height_at", "get_elevation", "elevation", "altitude_at", "ground_height", "is_on_land",
              "is_on_water", "contains", "land_height", "is_land_point")
    for key in ("caucasus", "syria", "persian_gulf"):
        mp = MAPS.get(key)
        if mp is None or not hasattr(terrain_mod, mp.terrain_class):
            continue
        out.append("")
        out.append(f"## {mp.display}")
        try:
            t = getattr(terrain_mod, mp.terrain_class)()
            mm = dcs.Mission(t)
        except Exception as e:  # noqa: BLE001
            out.append(f"could not create the map ({type(e).__name__}: {e})")
            continue
        attrs(t, "terrain attributes")
        attrs(mm, "mission attributes")
        try:
            land = next(iter(t.airports.values())).position
            out.append(f"land test point: airfield {next(iter(t.airports))}")
        except Exception as e:  # noqa: BLE001
            out.append(f"no airfield position ({e})")
            continue
        sea = None
        for lat, lng in mp.sea:
            try:
                sea = dcs.mapping.Point.from_latlng(dcs.mapping.LatLng(lat, lng), t)
                break
            except Exception:  # noqa: BLE001
                continue
        out.append(f"sea test point: {'found' if sea is not None else 'none'}")
        attrs(land, "Point attributes")
        for owner_label, owner in (("terrain", t), ("mission", mm), ("terrain.__class__", t.__class__)):
            for name in probes:
                fn = getattr(owner, name, None)
                if fn is None or not callable(fn):
                    continue
                try:
                    sig = str(inspect.signature(fn))
                except Exception:  # noqa: BLE001
                    sig = "?"
                res = []
                for label, pt in (("land", land), ("sea", sea)):
                    if pt is None:
                        continue
                    for args in ((pt,), (pt.x, pt.y)):
                        try:
                            res.append(f"{label}{'(pt)' if len(args) == 1 else '(x,y)'}={fn(*args)!r}")
                            break
                        except Exception as e:  # noqa: BLE001
                            res.append(f"{label}: {type(e).__name__}")
                out.append(f"{owner_label}.{name}{sig}: " + "; ".join(res))
    return out



def dump_runway_probe():
    """Report where runway length/position data might be, in pydcs and in the DCS install."""
    import re
    out = []
    try:
        import importlib.metadata as md
        out.append(f"pydcs version: {md.version('pydcs')}")
    except Exception as e:  # noqa: BLE001
        out.append(f"pydcs version: unknown ({e})")

    def show(obj, label, depth=0):
        names = [n for n in dir(obj) if not n.startswith("__")]
        vals = []
        for n in names:
            try:
                v = getattr(obj, n)
            except Exception as e:  # noqa: BLE001
                v = f"<{type(e).__name__}>"
            if callable(v):
                continue
            vals.append(f"{n}={v!r}"[:90])
        out.append(f"{label}: " + "; ".join(vals))

    out.append("")
    out.append("## What pydcs knows about airfield runways")
    for key in ("caucasus", "germany_cw", "syria"):
        mp = MAPS.get(key)
        if mp is None or not hasattr(terrain_mod, mp.terrain_class):
            continue
        try:
            t = getattr(terrain_mod, mp.terrain_class)()
            name, ap = next(iter(t.airports.items()))
        except Exception as e:  # noqa: BLE001
            out.append(f"{key}: could not load ({e})")
            continue
        out.append(f"-- {mp.display}: {name}")
        show(ap, "airport")
        for rw in getattr(ap, "runways", [])[:2]:
            show(rw, "runway")
            for end in ("main", "opposite"):
                if hasattr(rw, end):
                    show(getattr(rw, end), f"runway.{end}")

    out.append("")
    out.append("## DCS install: terrain folders and files that may describe runways")
    from . import liveryscan
    words = re.compile(r"runway|rwy|airdrome|airfield|\bILS\b", re.I)
    shown = 0
    for inst in liveryscan.install_dirs()[:1]:
        out.append(f"install: {inst}")
        terrains = inst / "Mods" / "terrains"
        if not terrains.is_dir():
            out.append(f"no Mods\\terrains folder at {terrains}")
            continue
        for tdir in sorted(p for p in terrains.iterdir() if p.is_dir()):
            out.append(f"-- {tdir.name}")
            try:
                out.append("   top level: " + str(sorted(x.name for x in tdir.iterdir())[:40]))
            except OSError as e:
                out.append(f"   cannot list ({e})")
                continue
            hits = 0
            for root, dnames, files in os.walk(tdir):
                depth = len(Path(root).relative_to(tdir).parts)
                if depth > 4:
                    dnames[:] = []
                    continue
                for f in files:
                    low = f.lower()
                    path = Path(root) / f
                    name_hit = bool(words.search(f))
                    if not (name_hit or low.endswith((".lua", ".xml", ".json", ".cfg", ".txt", ".csv"))):
                        continue
                    try:
                        if path.stat().st_size > 4_000_000:
                            continue
                        text = path.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        continue
                    lines = [ln.strip()[:140] for ln in text.splitlines()
                             if re.search(r"runway|rwy|length|airdrome", ln, re.I)][:4]
                    if name_hit or lines:
                        hits += 1
                        if hits <= 12:
                            out.append(f"   {path.relative_to(tdir)} ({path.stat().st_size} bytes)")
                            for ln in lines:
                                out.append(f"       | {ln}")
            out.append(f"   files with runway-like content: {hits}")
    return out



def dump_runway_check():
    """One line per airfield: DCS position, runway headings, and how well the real-runway data matched."""
    out = ["Compare the flagged ones in the mission editor: right-click the airfield / runway ends for",
           "coordinates. OK = matched with real runway ends; ESTIMATE = real length known, ends not (layout",
           "centred on the DCS point); CHECK = matched but doubtful; NO MATCH = heading-only layout.",
           ""]
    if not runways.available():
        return out + ["No runway data yet: run fetch_runways.bat first, then this again."]
    names = ("OK", "ESTIMATE", "CHECK", "NO MATCH")
    rows = []
    for key, mp in MAPS.items():
        if not hasattr(terrain_mod, mp.terrain_class):
            continue
        try:
            t = getattr(terrain_mod, mp.terrain_class)()
            aps = list(t.airports.items())
        except Exception as e:  # noqa: BLE001
            rows.append((3, f"{mp.display}: could not load ({e})"))
            continue
        for name, ap in aps:
            try:
                lat, lng = navinfo.point_latlng(ap.position)
            except Exception:  # noqa: BLE001
                continue
            heads = []
            for rw in getattr(ap, "runways", []):
                try:
                    heads.append((rw.name, rw.main.heading))
                except Exception:  # noqa: BLE001
                    pass
            head_txt = ", ".join(f"{n} ({h:.0f})" for n, h in heads) or "no runway data"
            if not heads:
                rows.append((3, f"[{mp.display}] {name}  DCS {lat:.5f},{lng:.5f}  runways: none in pydcs  -> NO MATCH"))
                continue
            notes, statuses = [], []
            for rname, h in heads:
                rg = runways.find(lat, lng, h)
                if rg is not None:
                    mid = ((rg["a"][0] + rg["b"][0]) / 2, (rg["a"][1] + rg["b"][1]) / 2)
                    dist = runways._dist_m((lat, lng), mid)
                    hd = abs(((runways._bearing(rg["a"], rg["b"]) - h) + 90) % 180 - 90)
                    doubtful = hd > 15 or rg["length"] < 800
                    statuses.append(2 if doubtful else 0)
                    notes.append(f"{rname}: real {rg['length']:.0f} m x {rg['width']:.0f} m, ends "
                                 f"{rg['a'][0]:.5f},{rg['a'][1]:.5f} / {rg['b'][0]:.5f},{rg['b'][1]:.5f}, "
                                 f"{dist:.0f} m from DCS point, {hd:.0f} deg off"
                                 + ("  <-- doubtful" if doubtful else ""))
                    continue
                est = runways.find_estimate(lat, lng, h)
                if est is not None:
                    statuses.append(1)
                    notes.append(f"{rname}: real length about {est['length']:.0f} m (ends not in the data)")
                else:
                    statuses.append(3)
                    gl = runways.guess_length(name)
                    notes.append(f"{rname}: no real runway within 4 km"
                                 + (f" (layout will assume about {gl:.0f} m)" if gl else " (no strip assumed)"))
            worst = 3 if all(x == 3 for x in statuses) else max(x for x in statuses if x != 3)
            rows.append((worst, f"[{mp.display}] {name}  DCS {lat:.5f},{lng:.5f}  runways: {head_txt}  -> {names[worst]}"
                         + "".join(f"\n      {n}" for n in notes)))
    rows.sort(key=lambda r: (-r[0], r[1]))
    counts = {i: sum(1 for r in rows if r[0] == i) for i in range(4)}
    out.append("   ".join(f"{counts[i]} {names[i]}" for i in range(4)) + "   (airfields on every map your pydcs has)")
    out.append("")
    out.extend(r[1] for r in rows)
    return out


def dump_liveries():
    """Plain-text report of how this pydcs exposes countries and liveries (for diagnosing)."""
    from . import countries as cmod
    out = []
    try:
        import importlib.metadata as md
        out.append(f"pydcs version: {md.version('pydcs')}")
    except Exception as e:  # noqa: BLE001
        out.append(f"pydcs version: unknown ({e})")
    out.append("")
    out.append("## Country lookup (our key -> pydcs class found)")
    for side, table in cmod.TABLE.items():
        for key in table:
            for era in cmod.ERA_KEYS:
                ch = cmod._choice(side, key, era)
                cls = cmod.pydcs_class(countries, ch)
                out.append(f"{side}/{key}/{era}: wanted {ch.pydcs} -> "
                           f"{(cls.__name__ + ' name=' + repr(getattr(cls, 'name', ''))) if cls else 'NOT FOUND'}")
    out.append("")
    out.append("## DCS install and liveries found by dcsgen's own scan")
    from . import liveryscan
    dirs = liveryscan.install_dirs()
    out.append(f"install folders: {[str(d) for d in dirs]}")
    idx = liveryscan.scan()
    out.append(f"aircraft types with liveries: {len(idx)}; total liveries: {sum(len(v) for v in idx.values())}")
    out.append(f"sample types: {sorted(idx)[:25]}")
    out.append("")
    out.append("## Where the liveries of some aircraft really live")
    import os
    for inst in dirs[:1]:
        for want in ("f-16c_50", "fa-18c_hornet", "f-14b", "f-14a-135-gr", "f-4e-45mc", "av8bna", "su-27", "mig-29a"):
            hits = []
            for sub in ("CoreMods", "Bazar", "Mods"):
                base = inst / sub
                if not base.is_dir():
                    continue
                for root, dnames, _files in os.walk(base):
                    depth = len(Path(root).relative_to(base).parts)
                    if depth > 6:
                        dnames[:] = []
                        continue
                    for dn in dnames:
                        if dn.lower() == want:
                            p = Path(root) / dn
                            try:
                                kids = [k for k in p.iterdir()]
                            except OSError:
                                kids = []
                            with_desc = sum((k / "description.lua").is_file() for k in kids if k.is_dir())
                            hits.append(f"{p.relative_to(inst)}  [{len(kids)} entries, {with_desc} with description.lua; first: {[k.name for k in kids[:3]]}]")
            out.append(f"{want}: " + ("; ".join(hits[:6]) if hits else "no folder with this name"))
    out.append("")
    out.append("## Liveries")
    for ac_key in ("f16c", "fa18c", "f14b", "a10c", "su27", "mig29a", "mig21", "f4e", "f86f"):
        spec = AIRCRAFT.get(ac_key)
        if spec is None:
            continue
        ptype = getattr(planes, spec.pydcs, None)
        out.append(f"-- {ac_key} ({spec.pydcs}) -> {'found' if ptype else 'missing'}")
        if ptype is None:
            continue
        holder = getattr(ptype, "Liveries", None)
        out.append(f"   Liveries attribute: {type(holder).__name__ if holder is not None else 'NONE'}")
        if holder is None:
            continue
        try:
            items = list(holder)
        except Exception as e:  # noqa: BLE001
            items = []
            out.append(f"   cannot iterate: {e}")
        out.append(f"   number of liveries: {len(items)}")
        for it in items[:3]:
            try:
                out.append(f"   sample: {it!r}"[:300] + f"  attrs={sorted(vars(it))[:10] if hasattr(it, '__dict__') else dir(it)[:10]}")
            except Exception as e:  # noqa: BLE001
                out.append(f"   sample: {type(it).__name__} ({e})")
        for cname in ("USA", "Russia", "USSR", "UK", "Germany", "France", "Iran"):
            ids = livery_ids(ptype, cname)
            out.append(f"   {cname}: found_ids={len(ids)} sample={ids[:3]}")
        try:
            out.append("   countries seen on liveries: "
                       + str(sorted({str(c) for it in items for c in (getattr(it, 'countries', None) or [])})[:30]))
        except Exception as e:  # noqa: BLE001
            out.append(f"   countries seen: error {e}")
    return out
