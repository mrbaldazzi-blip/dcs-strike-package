"""Mission planner.

Turns a MissionRequest into a MissionPlan: a package of 1-3 simultaneous flights with timed
on-target times, plus the enemy and friendly units around the objective. Pure Python and
map-independent; positions are bearing/distance (nm) from the objective, which the builder
places on a real map. Everything is side-aware: the player flies for `req.side`, the enemy is
the other coalition, and each side fields its own era-appropriate units.
"""

import math
import random
from dataclasses import replace
from datetime import datetime

from .budget import apply_budget
from .catalog import AIRCRAFT, available_aircraft, can_fly, flies_in
from . import ambient as ambient_mod
from . import countries, conditions
from . import loadouts
from . import naval
from . import support as support_mod
from .eras import ERAS
from .maps import MAPS
from .models import (SIDES, Activation, FlightPlan, SupportAsset, Frontline, Group, MissionPlan,
                     MissionType as M, Posture, Waypoint, enemy_of)

CALLSIGNS = {
    "blue": {
        M.STRIKE: ["Dagger", "Anvil", "Hammer"],
        M.CAS: ["Hawg", "Pig", "Axe"],
        M.SEAD: ["Magnum", "Wasp", "Shadow"],
        M.DEAD: ["Rifle", "Titan", "Lancer"],
        M.CAP: ["Viper", "Falcon", "Ghost"],
        M.INTERCEPT: ["Rampage", "Bandit", "Cobra"],
        M.NAVAL: ["Harpoon", "Trident", "Neptune"],
    },
    "red": {
        M.STRIKE: ["Molot", "Strela", "Kinzhal"],
        M.CAS: ["Grach", "Shturm", "Bizon"],
        M.SEAD: ["Yastreb", "Skorpion", "Gadyuka"],
        M.DEAD: ["Grom", "Bulat", "Taran"],
        M.CAP: ["Sokol", "Orel", "Berkut"],
        M.INTERCEPT: ["Burya", "Grozny", "Vityaz"],
        M.NAVAL: ["Kortik", "Akula", "Skat"],
    },
}

# The primary flight comes first; supporting flights follow in this order.
TEMPLATES = {
    M.STRIKE: [M.STRIKE, M.SEAD, M.CAP],
    M.SEAD: [M.SEAD, M.STRIKE, M.CAP],
    M.CAP: [M.CAP, M.STRIKE, M.SEAD],
    M.DEAD: [M.DEAD, M.CAP, M.STRIKE],
    M.CAS: [M.CAS, M.CAP, M.SEAD],
    M.INTERCEPT: [M.INTERCEPT, M.INTERCEPT, M.CAP],
    M.NAVAL: [M.NAVAL, M.CAP, M.NAVAL],
}

# Minutes relative to the primary time on target.
TOT_OFFSET = {M.STRIKE: 0, M.CAS: 0, M.DEAD: 0, M.SEAD: -3, M.CAP: -8, M.INTERCEPT: 0, M.NAVAL: 0}
FOLLOW_ON_STRIKE_OFFSET = 8   # a strike that follows a DEAD flight

LOADOUT = {
    M.STRIKE: "air-to-ground ordnance for a point target, plus a couple of missiles for self-defence",
    M.CAS: "guns, rockets and bombs or missiles suited to armour",
    M.SEAD: "anti-radiation missiles if your jet has them, otherwise bombs or rockets",
    M.DEAD: "heavy air-to-ground ordnance, plus anti-radiation missiles if you can carry them",
    M.CAP: "air-to-air missiles and guns",
    M.INTERCEPT: "a full air-to-air load: radar missiles for the first shots, heat-seekers and guns after",
    M.NAVAL: "anti-ship missiles if your jet has them, otherwise bombs, rockets or guided weapons for a ship",
}

def _assign_loadouts(plan, defences):
    """Real weapon loads per aircraft, chosen for the mission year. Light defences keep the enemy
    fighters to two missiles."""
    year = plan.year
    for f in plan.flights:
        role = getattr(f.role, "value", f.role)
        if role == "strike" and plan.airfield_attack:
            role = "airfield"
        f.pylons = loadouts.for_aircraft(f.pydcs_name, role, year)
        f.weapons = loadouts.describe(f.pylons)
    cap = 2 if defences == "light" else None
    for g in plan.groups:
        if g.kind != "plane":
            continue
        role = {"cap": "cap", "scramble": "cap", "raid_escort": "cap", "raid": "strike"}.get(g.tag)
        if role is None or not g.units:
            continue
        g.pylons = loadouts.for_aircraft(g.units[0][0], role, year,
                                         max_aa=cap if role == "cap" else None)


# Frontline infantry (pydcs class names): eight to a platoon
INFANTRY = {"blue": ("Soldier_M4", "Soldier_M249"), "red": ("Soldier_AK", "Soldier_RPG")}


def _infantry(side, n):
    """A platoon of n soldiers: mostly riflemen with some machine-gunners / RPGs."""
    rifle, support = INFANTRY[side]
    heavy = n // 4
    return [[rifle, n - heavy]] + ([[support, heavy]] if heavy else [])


def _split(total, biggest):
    """total units in as few equal-ish groups of at most `biggest` as possible."""
    if total <= 0:
        return []
    groups = -(-total // biggest)
    base, extra = divmod(total, groups)
    return [base + (1 if i < extra else 0) for i in range(groups)]


START_MINUTES = {"cold": 12, "hot": 6, "runway": 3}   # engine start, taxi and takeoff

# static objects (resolved against pydcs by name): dressing for airfields and the target area
AIRFIELD_STATICS = ["Hangar_A", "Hangar_B", "Shelter", "Garage_A", "Fuel_tank", "Barracks_2",
                    "Container_20ft", "Tent01", "Oil_Barrel", "Warehouse", "Tech_hangar_A",
                    "Comms_tower_M", "Revetment_x4", "Small_werehouse_1", "Boiler_house_A"]
TARGET_STATICS = ["Small_werehouse_1", "Small_werehouse_2", "Fuel_tank", "Container_red_1",
                  "Container_20ft", "Cargo01", "Tent02", "Haystack_1", "Garage_small_A",
                  "Shelter", "Warehouse", "Camouflage01", "Pile_of_Woods", "Oil_Barrel"]


# ---- geometry helpers (bearing degrees, distance nm) -----------------------

def _xy(bearing, dist):
    r = math.radians(bearing)
    return dist * math.sin(r), dist * math.cos(r)


def _polar(x, y):
    return math.degrees(math.atan2(x, y)) % 360, math.hypot(x, y)


def _offset(bearing, dist, heading, d):
    """Move the point (bearing, dist) by d nm along heading; return (bearing, dist)."""
    x, y = _xy(bearing, dist)
    dx, dy = _xy(heading, d)
    return _polar(x + dx, y + dy)


def _leg(a, b):
    ax, ay = _xy(a.bearing_deg, a.distance_nm)
    bx, by = _xy(b.bearing_deg, b.distance_nm)
    return math.hypot(ax - bx, ay - by)


def _route_len(wps):
    return sum(_leg(a, b) for a, b in zip(wps, wps[1:]))


# ---- request checks ---------------------------------------------------------

def _radar_sites(faction):
    return [s for s in faction.sam_sites if s.radar_guided]


def _pick_carrier(era, start, side):
    want_mod = start.kind == "supercarrier"
    cands = [c for c in era.faction(side).carriers if c.needs_mod == want_mod]
    if start.name:
        cands = [c for c in cands if c.key == start.name]
    return cands[0] if cands else None


def _can_fly(spec, role):
    return can_fly(spec, role)


def _role_feasible(era, role, carrier_start, side, any_era=False):
    if role in (M.SEAD, M.DEAD) and not _radar_sites(era.faction(enemy_of(side))):
        return False
    return bool(available_aircraft(era.key, role, carrier=carrier_start, side=side, include_mods=False,
                                      any_era=any_era))


def validate(req):
    """Return a list of problems with the request; empty means it is valid."""
    problems = []
    era = ERAS.get(req.era)
    spec = AIRCRAFT.get(req.aircraft)
    if era is None:
        problems.append(f"Unknown era '{req.era}'")
    if req.map_key not in MAPS:
        problems.append(f"Unknown map '{req.map_key}'")
    if spec is None:
        problems.append(f"Unknown aircraft '{req.aircraft}'")
    if req.side not in SIDES:
        problems.append(f"Unknown side '{req.side}'")
    if not 1 <= req.flights <= 3:
        problems.append("flights must be 1, 2 or 3")
    if not 1 <= req.flight_size <= 4:
        problems.append("flight size must be between 1 and 4")
    if req.max_units < 20:
        problems.append("max units must be at least 20")
    if req.start_state not in START_MINUTES:
        problems.append(f"Unknown start state '{req.start_state}'")
    if not 20 <= req.statics <= 50:
        problems.append("static objects must be between 20 and 50")
    if not 0 <= req.frontline_units <= 200:
        problems.append("frontline units must be between 0 and 200")
    if not 20 <= req.ground_units <= 140:
        problems.append("ground units must be between 20 and 140")
    if req.start.kind not in ("airbase", "carrier", "supercarrier"):
        problems.append(f"Unknown start kind '{req.start.kind}'")

    if spec and req.side in SIDES and spec.side != req.side:
        problems.append(f"{spec.display} flies for the {spec.side} side, not {req.side}")
    if era and spec:
        if not req.any_aircraft and not flies_in(spec, era.key):
            problems.append(f"{spec.display} is not available in {era.label}")
        if not can_fly(spec, req.mission_type):
            problems.append(f"{spec.display} cannot fly {req.mission_type.value.upper()} missions here")
        if req.start.kind != "airbase" and not spec.carrier:
            problems.append(f"{spec.display} cannot operate from a carrier")
    if req.mission_type is M.NAVAL and req.map_key in MAPS and not MAPS[req.map_key].sea:
        problems.append(f"{MAPS[req.map_key].display} has no open sea, so Naval strike is not possible there")
    if era and req.side in SIDES:
        if req.mission_type in (M.SEAD, M.DEAD) and not _radar_sites(era.faction(enemy_of(req.side))):
            problems.append(f"The {req.side} side faces no radar-guided SAMs in {era.label}, so "
                            f"{req.mission_type.value.upper()} missions are not possible")
        if req.start.kind in ("carrier", "supercarrier") and _pick_carrier(
                era, req.start, req.side) is None:
            problems.append(f"No {req.start.kind} {req.start.name!r} is available to the "
                            f"{req.side} side in {era.label}".replace(" ''", ""))
    return problems


# ---- group builders ---------------------------------------------------------

def _sam_group(site, side, bearing, dist, tag, priority, activation, suffix=""):
    return Group(
        name=f"SAM - {site.display}{suffix}", side=side, kind="vehicle",
        units=[[cls, n] for cls, n in site.components],
        bearing_deg=bearing, distance_nm=dist, tag=tag, priority=priority,
        range_nm=site.lethal_range_nm, activation=activation)


def _build_flight(rng, era, role, fspec, size, callsign, a, D, sead_pos, objective, sead_name,
                  primary, preemptive, start_min=12, T=None):
    alt, spd = era.ingress_alt_ft, era.ingress_speed_kts
    if role is M.CAP:
        spd, alt = min(spd, 420), max(alt, 15000)
    if role is M.INTERCEPT:
        spd, alt = max(spd, 480), max(alt, 25000)

    start = Waypoint("Start", a, D, 0, 0)
    ingress = Waypoint("Ingress", (a + rng.uniform(-8, 8)) % 360, rng.uniform(.55, .68) * D, alt, spd)
    ip = Waypoint("IP", (a + rng.uniform(-5, 5)) % 360, rng.uniform(.17, .24) * D, alt, spd)
    egress = Waypoint("Egress", (a + rng.choice([-1, 1]) * rng.uniform(70, 110)) % 360,
                      rng.uniform(.24, .33) * D, alt, spd)
    land = Waypoint("Land", a, D, 0, 0, "land")

    dwell = 0
    if role is M.INTERCEPT:
        vector = Waypoint("Vector", (a + rng.uniform(-6, 6)) % 360, 0.5 * D, alt, spd)
        key = Waypoint("Intercept point", 0.0, 0.0, alt, spd, "attack")
        route = [start, vector, key, land]
        dwell = 6
        tasking = ("Scramble, climb to the raid's altitude and meet the incoming strike at the "
                   "Intercept point. Kill the bombers before they reach the field.")
    elif role is M.CAP:
        key = Waypoint("CAP station", (a + rng.uniform(-20, 20)) % 360, rng.uniform(.12, .18) * D,
                       alt, spd, "orbit")
        route = [start, ingress, key, egress, land]
        transit = _route_len(route) / spd * 60 + 3
        dwell = max(4, int(round((T if T else transit + 22) - transit)))
        tasking = "Hold the CAP station, protect the package and engage any hostile fighters."
    elif role is M.SEAD:
        sb, sd = sead_pos
        lb, ld = _offset(sb, sd, a, max(7.0, 0.16 * D))
        launch = Waypoint("Launch point", lb, ld, alt, spd)
        key = Waypoint("SAM site", sb, sd, alt, spd, "attack")
        route = [start, ingress, ip, launch, key, egress, land]
        tasking = (f"Suppress the {sead_name} so the strike can reach the target. "
                   "Engage from the Launch point.")
    elif role is M.NAVAL:
        key = Waypoint("Ship", 0.0, 0.0, 200 if alt < 5000 else alt, spd, "attack")
        route = [start, ingress, ip, key, egress, land]
        tasking = f"Find and sink the {objective}. Expect any escorts to shoot back."
    elif role is M.DEAD:
        key = Waypoint("SAM site", 0.0, 0.0, alt, spd, "attack")
        route = [start, ingress, ip, key, egress, land]
        tasking = f"Destroy the {objective}, then clear the area."
    else:
        key = Waypoint("Target", 0.0, 0.0, max(alt, 500), spd, "attack")
        route = [start, ingress, ip, key, egress, land]
        if role is M.CAS:
            tasking = (f"Destroy the {objective} before it advances." if preemptive
                       else f"Attack the {objective} in contact with friendly forces.")
        else:
            tasking = f"Destroy the {objective} at the target."

    idx = route.index(key)
    t_key = start_min + _route_len(route[:idx + 1]) / spd * 60   # engine start, taxi, takeoff
    tail = dwell + _route_len(route[idx:]) / spd * 60 + 3    # 3 min to land

    flight = FlightPlan(
        callsign=callsign, role=role, aircraft_key=fspec.key, aircraft_display=fspec.display,
        pydcs_name=fspec.pydcs, size=size, waypoints=route, key_waypoint=key.name,
        tasking=tasking, loadout=LOADOUT[role], primary=primary, service=fspec.service,
        dwell_min=dwell)
    return flight, t_key, tail


# ---- main entry point -------------------------------------------------------

def generate_plan(req):
    problems = validate(req)
    if problems:
        raise ValueError("; ".join(problems))

    if req.mission_type is M.INTERCEPT:      # a scramble: runway start (hot on a carrier)
        req = replace(req, start_state="hot" if req.start.kind != "airbase" else "runway")
    era = ERAS[req.era]
    mp = MAPS[req.map_key]
    spec = AIRCRAFT[req.aircraft]
    mt = req.mission_type
    side = req.side
    foe = enemy_of(side)
    friend_f, enemy_f = era.faction(side), era.faction(foe)
    active = req.posture is Posture.ACTIVE_WAR
    carrier_start = req.start.kind != "airbase"
    carrier = _pick_carrier(era, req.start, side) if carrier_start else None

    rng = random.Random("|".join([
        req.era, req.map_key, req.aircraft, mt.value, req.posture.value, side,
        f"{req.start.kind}:{req.start.name}", str(req.seed)]))

    lo, hi = max(era.years[0], spec.years[0]), min(era.years[1], spec.years[1])
    if lo > hi:                                  # aircraft and era barely overlap: use the era
        lo, hi = era.years
    year = rng.randint(lo, hi)
    season = req.season if req.season in conditions.SEASON_LABEL and req.season != "random" \
        else rng.choice(["summer", "winter", "spring", "autumn"])
    tod = req.time_of_day if req.time_of_day in conditions.TIME_LABEL and req.time_of_day != "random" \
        else rng.choice(["day", "night", "sunrise", "presunrise", "sunset"])
    wkey = req.weather if req.weather in conditions.WEATHER else rng.choice(
        [k for k in conditions.WEATHER if k not in ("thunderstorm", "fog")])
    day = conditions.pick_date(rng, year, season if mp.lat >= 0 else conditions.OPPOSITE[season])
    start_time = conditions.start_clock(tod, mp.lat, mp.lon, mp.utc_offset, day)
    a = rng.uniform(0, 360)                  # bearing from the objective back to the base
    # airborne time of 15-35 minutes, averaging about 20; the base distance follows from it
    T = 15 + 20 * rng.betavariate(1.6, 5.5)
    cruise = era.ingress_speed_kts
    transit_T = T * (0.55 if mt is M.CAP else 1.0)
    if mt is M.INTERCEPT:                    # out to the merge, a short fight, and home again
        cruise = max(cruise, 480)
        D = max(28.0, (T - 3 - 6) * cruise / 60 / 1.5)
    else:
        D = max(28.0, (transit_T - 3) * cruise / 60 / 2.34)   # base distance from the objective
    K = max(0.4, D / 110.0)                  # scales the enemy layout to the shorter distances
    activation_radius = round(rng.uniform(5, 10), 1)
    # Pre-emptive: the alert fighters normally launch as we reach the target, so the fight comes
    # after the strike. About one time in seven they are already up and meet us on the way in.
    early_intercept = (req.posture is Posture.PREEMPTIVE) and rng.random() < 0.15
    scramble_radius = round(D * 0.95, 1) if early_intercept else round(rng.uniform(10, 16), 1)
    defence_activation = (Activation("always") if active
                          else Activation("proximity", activation_radius))

    groups = []
    defences = req.defences if req.defences in conditions.DEFENCES_LABEL else "medium"
    notes = []
    if defences == "light" and mt in (M.SEAD, M.DEAD):
        defences = "medium"
        notes.append(f"{mt.value.upper()} needs a SAM to hunt, so the defences were raised from light "
                     "to medium.")

    # --- the objective
    land_target = mt not in (M.NAVAL, M.INTERCEPT)
    if mt is M.NAVAL:
        kind, tname, tcls, treach = naval.pick_target(rng, foe, era.key)
        objective = tname[0].lower() + tname[1:] if tname[1:2].islower() else tname
        if kind == "carrier":
            objective = f"enemy carrier, {tname}"
        elif kind == "warship":
            objective = f"enemy {objective}"
        groups.append(Group(f"Target - {tname}", foe, "ship", [[tcls, 1]], 0.0, 0.0,
                            heading_deg=rng.uniform(0, 360), tag="target", priority=0,
                            range_nm=treach))
        for i in range(naval.escort_count(rng, defences)):
            edisp, ecls, ereach = rng.choice(naval.ESCORTS[(foe, era.key)])
            groups.append(Group(f"Escort {i + 1} - {edisp}", foe, "ship", [[ecls, 1]],
                                rng.uniform(0, 360), rng.uniform(1.5, 4.5),
                                heading_deg=rng.uniform(0, 360), tag="escort", priority=2,
                                optional=True, range_nm=ereach))
        sam_pool, n_sites, site_dist = [], 0, (2, 5)
    elif mt is M.INTERCEPT:
        objective = "inbound enemy raid"
        sam_pool, n_sites, site_dist = [], 0, (2, 5)
    elif mt is M.DEAD:
        pool = [s for s in _radar_sites(enemy_f) if s.lethal_range_nm >= 10] or _radar_sites(enemy_f)
        obj_site = rng.choice(pool)
        objective = f"{obj_site.display} site"
        groups.append(_sam_group(obj_site, foe, 0.0, 0.0, "target", 0, defence_activation))
        sam_pool = [s for s in enemy_f.sam_sites if s is not obj_site]
        n_sites = {"light": 0, "medium": rng.choice([0, 1]), "heavy": rng.randint(5, 7)}[defences]
        site_dist = (6, 12) if defences == "heavy" else (7, 11)
    else:
        if mt is M.CAS:
            name, cls, n = rng.choice(enemy_f.forces)
        else:
            name, cls, n = rng.choice(enemy_f.soft_targets)
        objective = name[0].lower() + name[1:] if name[1:2].islower() else name   # keep "T-72"
        groups.append(Group(f"Target - {name}", foe, "vehicle", [[cls, n]], 0.0, 0.0,
                            heading_deg=rng.uniform(0, 360), tag="target", priority=0,
                            min_total=max(2, n // 2)))
        sam_pool = list(enemy_f.sam_sites)
        n_sites = {"light": 0, "medium": rng.choice([1, 2]), "heavy": rng.randint(5, 7)}[defences]
        site_dist = (2, 9) if defences == "heavy" else (3, 7)

    airfield_attack, objective_normal = False, ""
    if mt is M.STRIKE and random.Random(f"afatk|{req.seed}|{req.era}|{req.map_key}").random() < 0.25:
        airfield_attack, objective_normal = True, objective       # builder falls back if no airfield fits
        objective = "enemy airfield and the aircraft parked on it"

    # --- SAM sites, kept off the ingress axis
    placed = []
    if not sam_pool:
        sam_pool = list(enemy_f.sam_sites)
    picks = rng.sample(sam_pool, min(n_sites, len(sam_pool)))
    while len(picks) < n_sites and sam_pool:        # heavy: the same systems repeat in layers
        picks.append(rng.choice(sam_pool))
    seen = {}
    for site in picks:
        b = (a + rng.uniform(40, 320)) % 360
        seen[site.display] = seen.get(site.display, 0) + 1
        suffix = f" #{seen[site.display]}" if seen[site.display] > 1 else ""
        g = _sam_group(site, foe, b, rng.uniform(*site_dist), "sam", 1, defence_activation, suffix)
        groups.append(g)
        placed.append((site, g))

    # --- AAA at the objective
    if enemy_f.aaa and land_target:
        disp, cls, n = rng.choice(enemy_f.aaa)
        groups.append(Group(f"AAA - {disp}", foe, "vehicle", [[cls, n]], rng.uniform(0, 360),
                            rng.uniform(1, 3), tag="aaa", priority=3, optional=True,
                            range_nm=2.0, activation=defence_activation))

    if defences == "heavy" and enemy_f.aaa and land_target:        # a thick AAA belt on top of the missiles
        for i in range(3):
            disp, cls, n = rng.choice(enemy_f.aaa)
            groups.append(Group(f"AAA ring {i + 1} - {disp}", foe, "vehicle", [[cls, n]],
                                rng.uniform(0, 360), rng.uniform(1.5, 5), tag="aaa", priority=3,
                                optional=True, range_nm=2.0, activation=defence_activation))

    # --- enemy fighters (an intercept brings its own with the raid)
    if mt is M.INTERCEPT:
        pass
    elif active:
        for i in range(2):
            disp, cls = rng.choice(enemy_f.fighters)
            d = (rng.uniform(12, 25) if mt is M.CAS else rng.uniform(20, 38)) * K
            groups.append(Group(f"{foe.title()} CAP {i + 1} - {disp}", foe, "plane", [[cls, 2]],
                                (a + rng.uniform(-40, 40)) % 360, d,
                                heading_deg=rng.uniform(0, 360), tag="cap", priority=2,
                                optional=(i == 1)))
        if enemy_f.ewr and land_target:
            groups.append(Group("EWR", foe, "vehicle", [[enemy_f.ewr, 1]], rng.uniform(0, 360),
                                rng.uniform(6, 12), tag="ewr", priority=3, optional=True))
    else:
        for i in range(2):
            disp, cls = rng.choice(enemy_f.fighters)
            groups.append(Group(
                f"Scramble {i + 1} - {disp}", foe, "plane", [[cls, 2]],
                (a + rng.uniform(-30, 30)) % 360, rng.uniform(30, 50) * K, tag="scramble",
                priority=2, optional=(i == 1), placement="enemy_airbase",
                activation=Activation("scramble", scramble_radius, rng.randint(60, 180))))

    # --- frontline (active warzone only): its own count, separate from the garrison
    frontline = None
    if active and land_target and req.frontline_units > 0:
        F = rng.uniform(1.5, 3.5) if mt is M.CAS else rng.uniform(22, 36) * K
        # Most CAS missions (about 78%) hit the enemy line itself, so the objective sits on the front.
        front_target = (mt is M.CAS and objective
                        and random.Random(f"fronttgt|{req.seed}|{req.era}|{req.map_key}").random() < 0.78)
        if front_target:
            F = 0.55                  # the enemy line runs through the objective
            objective = f"{objective} on the front line"
            for g in groups:
                if g.tag == "target":
                    g.heading_deg = a             # dug in facing our side
        line_heading = (a + 90) % 360
        frontline = Frontline(a, F, line_heading, 22.0)
        per_side = max(2, req.frontline_units // 2)
        armour = round(per_side * 0.2)                        # 20% armour, 80% infantry
        infantry = per_side - armour
        specs = []                                            # (kind, size) in line order
        a_sizes = _split(armour, 4)
        i_sizes = _split(infantry, 8)
        for kind, sizes in (("armour", a_sizes), ("infantry", i_sizes)):
            for k, n_ in enumerate(sizes):
                specs.append(((k + 0.5) / len(sizes), kind, n_))
        specs.sort(key=lambda t: (t[0], t[1]))                # spread the armour between the platoons
        alongs = [-10 + 20 * (i - 0.5) / len(specs) for i in range(1, len(specs) + 1)]
        target_i = None
        tgt = next((g for g in groups if g.tag == "target"), None)
        if front_target and tgt is not None:
            armour_at = [i for i, sp in enumerate(specs) if sp[1] == "armour"]
            if armour_at:                 # the objective IS one of the enemy's frontline armour groups
                target_i = min(armour_at, key=lambda i: abs(alongs[i]))
                shift = alongs[target_i]
                alongs = [x - shift for x in alongs]
                tgt.units = [[tgt.units[0][0], specs[target_i][2]]]
                tgt.min_total = max(2, specs[target_i][2] // 2)
            else:                         # no armour at all: just leave a gap on the line for it
                alongs = [x * 0.91 + (0.9 if x >= 0 else -0.9) for x in alongs]
        for i, (_f, kind, size) in enumerate(specs, 1):
            along = alongs[i - 1]
            cb, cd = _offset(a, F, line_heading, along)
            rb, rd = _offset(cb, cd, (a + 180) % 360, 0.55)       # about 2 km between the lines,
            bb, bd = _offset(cb, cd, a, 0.55)                    # inside tank gun range
            if kind == "armour":
                rname, rcls, _rn = rng.choice(enemy_f.forces)
                bname, bcls, _bn = rng.choice(friend_f.forces)
                red_units, blue_units = [[rcls, size]], [[bcls, size]]
                red_label, blue_label = rname, bname
            else:
                red_units, blue_units = _infantry(foe, size), _infantry(side, size)
                red_label = blue_label = "Infantry platoon"
            if i - 1 != target_i:             # the target group stands in for this one
                groups.append(Group(f"Frontline {foe} {i} - {red_label}", foe, "vehicle",
                                    red_units, rb, rd, heading_deg=a,
                                    tag="frontline", priority=4, optional=True))
            groups.append(Group(f"Frontline {side} {i} - {blue_label}", side, "vehicle",
                                blue_units, bb, bd, heading_deg=(a + 180) % 360,
                                tag="frontline", priority=4, optional=True))

    # --- convoys that drive: an enemy one running for the objective, a friendly one for the front
    if land_target:
        crng = random.Random(f"convoy|{req.seed}|{req.era}|{req.map_key}")
        if active or crng.random() < 0.4:
            sname, scls, sn = crng.choice(enemy_f.soft_targets)
            sb = (a + crng.choice([-1, 1]) * crng.uniform(60, 120)) % 360
            sd = crng.uniform(11, 16) * K
            mid = _offset(sb, sd, (sb + 180) % 360, sd * 0.5)
            end = _offset(sb, sd, (sb + 180) % 360, max(0.0, sd - 2.5))
            groups.append(Group(f"Enemy convoy - {sname}", foe, "vehicle", [[scls, max(4, min(sn, 6))]],
                                sb, sd, heading_deg=(sb + 180) % 360, tag="convoy", priority=4,
                                optional=True, route=[(sb, sd), mid, end], speed_kts=22.0))
        if frontline is not None:
            fname, fcls, fn = crng.choice(friend_f.soft_targets)
            # the friendly side is toward the player's start (bearing a from the objective)
            fb, fd = _offset(frontline.bearing_deg, frontline.distance_nm, a, 9.0)
            fe = _offset(frontline.bearing_deg, frontline.distance_nm, a, 2.5)
            groups.append(Group(f"Friendly convoy - {fname}", side, "vehicle", [[fcls, max(3, min(fn, 5))]],
                                fb, fd, heading_deg=(a + 180) % 360, tag="convoy", priority=4, optional=True,
                                route=[(fb, fd), fe], speed_kts=22.0))

    if land_target:
        # --- assets along the route
        rb0 = (a + rng.uniform(-10, 10)) % 360
        side_off = rng.choice([-1, 1]) * rng.uniform(3, 5)
        pb, pd = _offset(rb0, rng.uniform(38, 55) * K, (a + 90) % 360, side_off)
        sname, scls, sn = rng.choice(enemy_f.soft_targets)
        groups.append(Group(f"Route - {sname}", foe, "vehicle", [[scls, min(sn, 4)]], pb, pd,
                            tag="route", priority=5, optional=True))
        if active and enemy_f.aaa:
            disp, cls, n = rng.choice(enemy_f.aaa)
            ab, ad = _offset(pb, pd, a, 1.0)
            groups.append(Group(f"Route AAA - {disp}", foe, "vehicle", [[cls, n]], ab, ad,
                                tag="aaa", priority=5, optional=True, range_nm=2.0))

        # --- garrison: bring the active ground units up to the requested number
        def vehicles_now():
            return sum(g.count for g in groups if g.kind == "vehicle" and g.tag != "frontline")

        pool_f = [(n, c, k) for n, c, k in enemy_f.forces] + [(n, c, k) for n, c, k in enemy_f.soft_targets]
        guard = 0
        while vehicles_now() < req.ground_units and guard < 60:
            guard += 1
            gap = req.ground_units - vehicles_now()
            if enemy_f.aaa and guard % 4 == 0:
                disp, cls, n = rng.choice(enemy_f.aaa)
                name = f"Garrison AAA - {disp}"
                n = min(n + 1, gap)
                rng_nm = 2.0
            else:
                disp, cls, n = rng.choice(pool_f)
                name = f"Garrison - {disp}"
                n = min(max(n, 3), 6, gap)
                rng_nm = 0.0
            groups.append(Group(name, foe, "vehicle", [[cls, max(1, n)]], rng.uniform(0, 360),
                                rng.uniform(0.4, 4.5), heading_deg=rng.uniform(0, 360),
                                tag="garrison", priority=4 if guard % 4 else 3, optional=True,
                                range_nm=rng_nm))

    # --- static objects: dress the airfields and the target area
    statics = []
    n_air = 0 if carrier_start else int(round(req.statics * 0.3))
    n_enemy = int(round(req.statics * 0.2)) if mt is not M.INTERCEPT else 0
    n_target = req.statics - n_air - n_enemy if land_target else 0
    for i in range(n_air):
        statics.append(Group(f"Static airfield {i + 1}", side, "static",
                             [[rng.choice(AIRFIELD_STATICS), 1]], 0.0, 0.0,
                             heading_deg=rng.uniform(0, 360), tag="static",
                             placement="start_airbase"))
    for i in range(n_enemy):
        statics.append(Group(f"Static enemy airfield {i + 1}", foe, "static",
                             [[rng.choice(AIRFIELD_STATICS), 1]], 0.0, 0.0,
                             heading_deg=rng.uniform(0, 360), tag="static",
                             placement="enemy_airbase"))
    for i in range(n_target):
        b, d = rng.uniform(0, 360), rng.uniform(0.05, 0.6)
        statics.append(Group(f"Static target {i + 1}", foe, "static",
                             [[rng.choice(TARGET_STATICS), 1]], b, d,
                             heading_deg=rng.uniform(0, 360), tag="static"))

    # --- the package
    sead_group = None
    radar_placed = [(s, g) for s, g in placed if s.radar_guided]
    if radar_placed:
        sead_group = max(radar_placed, key=lambda sg: sg[0].lethal_range_nm)[1]
    for _site, g in placed:                  # only the SEAD flight's site must survive trimming
        if g is not sead_group:
            g.optional = True

    roles = [mt]
    for r in TEMPLATES[mt][1:]:
        if r is M.SEAD and sead_group is None:
            continue
        if _role_feasible(era, r, carrier_start, side, req.any_aircraft) or (
                _can_fly(spec, r) and (r not in (M.SEAD, M.DEAD) or _radar_sites(enemy_f))):
            roles.append(r)
    roles = roles[:req.flights]

    used, built = set(), []
    for idx, role in enumerate(roles):
        primary = idx == 0
        if primary or _can_fly(spec, role):
            fspec = spec                      # same aircraft as the player's, whenever it suits the role
        else:
            # supporting flights fly what the era is known for, not last decade's leftovers
            fspec = rng.choice(
                available_aircraft(era.key, role, carrier=carrier_start, side=side, include_mods=False,
                                   any_era=req.any_aircraft, strict=True)
                or available_aircraft(era.key, role, carrier=carrier_start, side=side,
                                      any_era=req.any_aircraft, strict=True)
                or available_aircraft(era.key, role, carrier=carrier_start, side=side, include_mods=False,
                                      any_era=req.any_aircraft)
                or available_aircraft(era.key, role, carrier=carrier_start, side=side,
                                      any_era=req.any_aircraft))
        pool = [c for c in CALLSIGNS[side][role] if c not in used] or CALLSIGNS[side][role]
        cs = rng.choice(pool)
        used.add(cs)
        flight, t_key, tail = _build_flight(
            rng, era, role, fspec, req.flight_size if primary else 2, f"{cs} {idx + 1}", a, D,
            (sead_group.bearing_deg, sead_group.distance_nm) if sead_group else (0.0, 0.0),
            objective, sead_group.name.replace("SAM - ", "") if sead_group else "",
            primary, not active, START_MINUTES[req.start_state], T)
        offset = TOT_OFFSET[role]
        if mt is M.INTERCEPT:
            offset = 0                    # everyone meets the raid together
        if role is M.STRIKE and mt is M.DEAD:
            offset = FOLLOW_ON_STRIKE_OFFSET
        built.append((flight, offset, t_key, tail))

    # The player's flight starts at once and its wingman with it. A supporting CAP starts at once too,
    # and a supporting SEAD one minute after it (earlier if it would otherwise reach the target
    # less than 3 minutes ahead of the player). Anything else keeps its planned time on target.
    _p_flight, p_off, p_tkey, _p_tail = built[0]
    shift = p_tkey - p_off                      # minutes from mission start to the package TOT
    p_key = p_tkey
    cap_start = 0
    flights = []
    for i, (flight, off, t_key, tail) in enumerate(built):
        start = max(0.0, off - t_key + shift)
        if i == 0:
            start = 0.0
        elif flight.role is M.CAP and mt is not M.INTERCEPT:
            start = 0.0
        elif flight.role is M.SEAD and mt is not M.INTERCEPT and any(f.role is M.CAP for f, *_ in built[1:]):
            start = max(0.0, min(cap_start + 1.0, p_key - 3.0 - t_key))
        lead = 0.0
        if i > 0 and mt is not M.INTERCEPT and flight.role in (M.CAP, M.SEAD):
            if req.start_state == "runway":
                flight.airborne = True        # already flying when a runway-start player lines up
                lead = float(START_MINUTES["runway"])     # no taxi or take-off roll to fly
            elif req.start_state == "hot" and mt in (M.CAS, M.STRIKE) and not carrier_start:
                # Hot start: the first supporting flight (SEAD if there is one) is already airborne
                # and the other is lined up on the runway, so both reach the area sooner.
                first_support = next(k for k, (f, *_r) in enumerate(built)
                                     if k > 0 and f.role in (M.CAP, M.SEAD)
                                     and (f.role is M.SEAD or not any(
                                         g.role is M.SEAD for g, *_x in built[1:])))
                if i == first_support:
                    flight.airborne = True
                    lead = float(START_MINUTES["hot"])
                else:
                    flight.runway_start = True
                    lead = float(START_MINUTES["hot"] - START_MINUTES["runway"])
            if flight.role is M.SEAD and lead:
                start = 0.0                   # no reason to hold it back once it skips the ramp
        if i > 0 and flight.role is M.CAP and mt is not M.INTERCEPT:
            # stay on station until the player has had time to hit the target and get clear
            hold = int(round(p_key + 8 - (start + t_key - lead)))
            if hold > flight.dwell_min:
                tail += hold - flight.dwell_min
                flight.dwell_min = hold
        flight.start_min = int(round(start))
        flight.key_min = int(round(start + t_key - lead))
        flight.end_min = int(round(start + t_key - lead + tail))
        flights.append(flight)

    if mt is M.INTERCEPT:
        # The raid spawns when the mission starts and reaches the merge point as the player does.
        v = naval.RAID_SPEED_KTS[era.key]
        E = v * flights[0].key_min / 60.0
        bb = (a + 180 + rng.uniform(-25, 25)) % 360
        rdisp, rcls = rng.choice(naval.RAIDERS[(foe, era.key)])
        n_b, n_e = {"light": (2, 0), "medium": (3, 2), "heavy": (4, 4)}[defences]
        path = [(0.0, 0.0), (a, D)]
        groups.append(Group(f"Raid - {rdisp}", foe, "plane", [[rcls, n_b]], bb, E, tag="raid",
                            priority=1, route=path, alt_ft=naval.RAID_ALT_FT[era.key], speed_kts=v))
        if n_e:
            edisp, ecls = rng.choice(enemy_f.fighters)
            groups.append(Group(f"Raid escort - {edisp}", foe, "plane", [[ecls, n_e]], bb,
                                max(1.0, E - 2.0), tag="raid_escort", priority=2, optional=True,
                                route=path, alt_ft=naval.RAID_ALT_FT[era.key] + 2000, speed_kts=v))

    support = []
    srng = random.Random(f"support|{req.seed}|{req.era}|{req.map_key}")
    if req.awacs:
        aw = support_mod.pick_awacs(side, year, carrier_start)
        if aw:
            nb, nd = _offset(a, D * 0.55, (a + 90) % 360, -srng.uniform(6, 12))
            support.append(SupportAsset(
                "awacs", aw[0], aw[1], srng.choice(support_mod.NAMES[(side, "awacs")]), nb, nd,
                (a + 90) % 360, aw[2], aw[3], 251.0 if side == "blue" else 250.0, race_nm=30.0))
        else:
            notes.append("No AWACS was in service for that side and date, so none was added.")
    if req.tanker:
        got, why = support_mod.pick_tanker(side, year, era.key, spec.key)
        if got:
            tb, td = _offset(a, D * 0.78, (a + 90) % 360, srng.uniform(10, 16))
            support.append(SupportAsset(
                "tanker", got[0], got[1], srng.choice(support_mod.NAMES[(side, "tanker")]), tb, td,
                (a + 90) % 360, got[2], got[3], 254.0 if side == "blue" else 252.0, race_nm=28.0,
                tacan="41X" if side == "blue" else "61X", method=got[4]))
        else:
            notes.append(f"No tanker added: the {spec.display} {why}.")

    plan = MissionPlan(
        request=req, era=era, map_display=mp.display, start_time=start_time,
        weather=conditions.weather_text(wkey), objective=objective, flights=flights, groups=groups,
        approach_bearing=a, start_distance_nm=D, activation_radius_nm=activation_radius,
        scramble_radius_nm=scramble_radius, frontline=frontline, carrier=carrier,
        tot_min=int(round(shift)), player_side=side, enemy_side=foe,
        rotation_deg=(180.0 - a) % 360, geometry_final=False, statics=statics,
        sead_target=sead_group, time_of_day=tod, season=season, weather_key=wkey, notes=notes,
        support=support, year=year, early_intercept=early_intercept, flight_minutes=int(round(T)))
    plan.countries = countries.resolve(req, era.key, side)
    plan.airfield_attack, plan.objective_normal = airfield_attack, objective_normal
    _assign_loadouts(plan, defences)
    plan.ambient = ambient_mod.plan_ambient(req, era, side, active, carrier_start,
                                            f"{req.map_key}|{req.seed}")
    if sead_group is None and M.SEAD in TEMPLATES[mt][1:]:
        plan.notes.append("No SEAD flight in this package: there are no radar-guided SAMs at this "
                          "defence level for it to hunt. Choose Medium or Heavy defences to add one.")
    apply_budget(plan, req.max_units)
    return plan
