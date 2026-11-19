"""Briefing generator: the plan, told the way a flight lead would tell it.

`compose(plan)` returns a Briefing: one overview / situation-report page plus one page per
flight. The same pages feed the GUI tabs, the printable PDF, the DCS kneeboard and the plain-text
mission description. Pure Python, no pydcs needed.

Positions are described relative to the inbound track ("at your 3 o'clock", "20 nm short of the
target, left of track") because the plan is map-independent until the builder places it.
"""

import math
import random
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional

from . import navinfo
from .models import MissionType as M, Posture

ROLE_LABEL = {M.STRIKE: "Strike", M.CAS: "CAS", M.SEAD: "SEAD", M.DEAD: "DEAD", M.CAP: "CAP",
              M.INTERCEPT: "Intercept", M.NAVAL: "Naval strike"}
ROLE_LONG = {M.STRIKE: "Strike", M.CAS: "Close air support", M.SEAD: "SEAD", M.DEAD: "DEAD",
             M.CAP: "Combat air patrol", M.INTERCEPT: "Intercept", M.NAVAL: "Anti-ship strike"}

ERA_FLAVOUR = {
    "early_cold_war": "No fancy kit today. It's a map, a compass, a stopwatch and good eyeballs.",
    "mid_cold_war": "Your threat warning gear is your best friend, and their crews are good.",
    "late_cold_war": "We've got decent kit, but so do they, so don't get cocky.",
    "nineties": "GPS and precision weapons are on the table. Use them, but don't get lazy.",
    "modern": "The datalink is up. Share your picture and keep the chatter short.",
}


@dataclass
class Page:
    tab: str                      # GUI tab label, e.g. "Strike - Dagger 1"
    title: str                    # heading printed on the page
    kind: str                     # "overview" or "flight"
    facts: list                   # [(label, value)] for the info box under the header
    sections: list                # [(heading, [lines])]; a line starting "- " is a bullet
    flight: Optional[object] = None
    route: list = field(default_factory=list)   # flight pages: table rows
    route_header: tuple = ()
    target: Optional[object] = None      # imagery pages: the Group being photographed
    age_hours: int = 0                   # imagery pages: how old the pictures are

    def as_text(self):
        out = ["=" * 60, self.title.upper(), "=" * 60]
        out.extend(f"{k}: {v}" for k, v in self.facts)
        if self.route:
            out.append("")
            out.append("ROUTE")
            out.append("  " + "  ".join(f"{h:<12}" for h in self.route_header))
            for row in self.route:
                out.append("  " + "  ".join(f"{str(c):<12}" for c in row))
        for heading, lines in self.sections:
            out.append("")
            out.append(heading.upper())
            out.extend(lines)
        out.append("")
        return "\n".join(out)


@dataclass
class Briefing:
    code: str                     # operation name, e.g. "OPERATION DAGGER 417"
    pages: list

    def as_text(self):
        return "\n".join(p.as_text() for p in self.pages)


# ---- helpers ----------------------------------------------------------------------------------

def _clock(plan, minutes):
    return (plan.start_time + timedelta(minutes=minutes)).strftime("%H:%M")


def _inbound(plan):
    return (plan.approach_bearing + 180) % 360


def _where(plan, g):
    """Where a group sits, from the point of view of a pilot running in to the objective."""
    d = g.distance_nm
    if d < 1.0:
        return "right on the target"
    ang = (g.bearing_deg - _inbound(plan)) % 360
    if d <= 12:
        hour = int(round(ang / 30)) % 12 or 12
        return f"{d:.0f} nm from the target, at your {hour} o'clock on the run-in"
    fwd, right = d * math.cos(math.radians(ang)), d * math.sin(math.radians(ang))
    parts = [f"{abs(fwd):.0f} nm {'beyond' if fwd > 0 else 'short of'} the target"]
    if abs(right) >= 2:
        parts.append(f"{abs(right):.0f} nm {'right' if right > 0 else 'left'} of your track")
    return ", ".join(parts)


def _art(text):
    """'a' or 'an' for the phrase that follows ('an ammunition convoy', 'an SA-6 site')."""
    w = text.split()[0] if text.split() else "x"
    if w[0].lower() in "aeiou":
        return "an"
    acronym = len(w) > 1 and (w[:2].isupper() or w[1] in "-0123456789")
    return "an" if acronym and w[0] in "FHLMNRSX" else "a"


def _short(name):
    """'SAM - SA-6 Gainful' -> 'SA-6 Gainful'."""
    return name.split(" - ", 1)[1] if " - " in name else name


def _hdg(plan, a, b):
    """True heading from waypoint a to waypoint b, using the plan's rotation to the map."""
    def xy(wp):
        r = math.radians(wp.bearing_deg + plan.rotation_deg)
        return wp.distance_nm * math.sin(r), wp.distance_nm * math.cos(r)
    ax, ay = xy(a)
    bx, by = xy(b)
    return int(round(math.degrees(math.atan2(bx - ax, by - ay)) % 360)) or 360


def route_table(plan, f):
    """Rows for a flight's route: waypoint, altitude, speed, ETA, and heading once the map is real."""
    from .planner import _leg
    show_hdg = plan.geometry_final
    header = ("#", "Waypoint", "Alt ft", "Kts", "ETA") + (("HDG",) if show_hdg else ())
    spd = max((w.speed_kts for w in f.waypoints), default=400) or 400
    t, rows = f.start_min + 12.0, []
    dwell = f.dwell_min
    for i, wp in enumerate(f.waypoints):
        if i == 0:
            rows.append((1, wp.name, "-", "-", _clock(plan, f.start_min)) + (("-",) if show_hdg else ()))
            continue
        t += _leg(f.waypoints[i - 1], wp) / (wp.speed_kts or spd) * 60
        if wp.name == f.key_waypoint:
            t_show = f.key_min
            t = f.key_min + dwell
        elif i == len(f.waypoints) - 1:
            t_show = f.end_min          # same landing time as the page header
        else:
            t_show = t
        alt = f"{wp.altitude_ft:,}" if wp.altitude_ft else "-"
        kts = wp.speed_kts or "-"
        hdg = (f"{_hdg(plan, f.waypoints[i - 1], wp):03d}",) if show_hdg else ()
        rows.append((i + 1, wp.name, alt, kts, _clock(plan, int(round(t_show)))) + hdg)
    return header, rows


def _threat_lines(plan, limit=6):
    foe_adj = (plan.countries[plan.enemy_side].adjective if plan.countries
               else plan.era.faction(plan.enemy_side).adjective)
    items = []
    alert = [g for g in plan.groups if g.tag == "scramble"]
    if alert:                                   # one line for all the fighters on alert
        kinds = sorted({_short(g.name) for g in alert})
        items.append((1, 0, f"- {sum(g.count for g in alert)}x {' / '.join(kinds)} sitting alert at "
                            f"{_art(foe_adj)} {foe_adj} airfield, ready to scramble when they pick us up"))
    for g in plan.groups:
        if g.tag in ("sam", "aaa") or (g.tag == "target" and g.range_nm and g.kind != "ship") or (
                g.tag == "target" and g.kind == "ship" and g.range_nm):
            nm = _short(g.name)
            if g.name.startswith("Route AAA"):
                nm = f"AAA ({nm})"
            mark = " - that's your target" if g.tag == "target" else ""
            items.append((0 if g.tag != "aaa" else 2, -g.range_nm,
                          f"- {nm}: about {g.range_nm:.0f} nm reach, {_where(plan, g)}{mark}"))
        elif g.tag == "escort":
            items.append((0, -g.range_nm, f"- {_short(g.name)}: about {g.range_nm:.0f} nm missile and "
                                          f"gun reach, {_where(plan, g)}"))
        elif g.tag == "cap":
            items.append((1, 0, f"- {g.count}x {_short(g.name)} on CAP, {_where(plan, g)}"))
        elif g.tag == "ewr":
            items.append((3, 0, f"- Early-warning radar, {_where(plan, g)}. It's how they'll see "
                                "us coming."))
    items.sort(key=lambda x: (x[0], x[1]))
    return [t for _, _, t in items][:limit]


def _others(plan, flight):
    return [f for f in plan.flights if f is not flight]


def _delta(a, b):
    d = b - a
    return f"{abs(d)} min {'after' if d > 0 else 'before'}" if d else "at the same time as"


# ---- overview page ----------------------------------------------------------------------------

def _raid_lines(plan):
    """The intercept picture: what is coming, from where, and when it reaches the merge point."""
    from types import SimpleNamespace as NS
    bombers = next((g for g in plan.groups if g.tag == "raid"), None)
    if bombers is None:
        return []
    escort = next((g for g in plan.groups if g.tag == "raid_escort"), None)
    base = NS(bearing_deg=plan.approach_bearing, distance_nm=plan.start_distance_nm)
    dx, dy = _xy_nm(bombers.bearing_deg, bombers.distance_nm, base)
    brg = (math.degrees(math.atan2(dx, dy)) + plan.rotation_deg) % 360
    rng_nm = math.hypot(dx, dy)
    heading = (bombers.bearing_deg + 180 + plan.rotation_deg) % 360
    out = [f"- {bombers.count}x {_short(bombers.name)} (bombers)"
           + (f", escorted by {escort.count}x {_short(escort.name)}." if escort else ", no escort.")]
    out.append(f"- Picture when you launch: bearing {brg:03.0f} true from {'the ship' if plan.carrier else 'the field'}, "
               f"{rng_nm:.0f} nm, heading {heading:03.0f}, about {bombers.alt_ft:,} ft at "
               f"{bombers.speed_kts} kts.")
    out.append(f"- They reach the Intercept point at about {_clock(plan, plan.flights[0].key_min)}. "
               "Be there first and be high.")
    return out


def _overview(plan, rng):
    req, era = plan.request, plan.era
    me, foe = era.faction(plan.player_side), era.faction(plan.enemy_side)
    foe_adj = plan.countries[plan.enemy_side].adjective if plan.countries else foe.adjective
    primary = plan.flights[0]
    posture = ("a pre-emptive strike" if req.posture is Posture.PREEMPTIVE
               else "an active warzone")
    base = plan.carrier.display if plan.carrier else "home plate"
    facts = [
        ("Date", f"{plan.start_time:%d %B %Y}, {plan.start_time:%H:%M} local"),
        ("Theatre", plan.map_display),
        ("Weather", plan.weather),
        ("Posture", "Pre-emptive strike" if req.posture is Posture.PREEMPTIVE else "Active warzone"),
        ("Launching from", plan.carrier.display if plan.carrier else "Airbase"),
    ]

    opener = rng.choice(["Alright, listen up.", "Settle in, folks.", "Okay, gather round.",
                         "Right, eyes up front.", "Morning, everybody. Pay attention.",
                         "Good, you're all here. Let's get into it."])
    mt = req.mission_type
    raid = []
    obj, art = plan.objective, _art(plan.objective)
    kw = dict(opener=opener, posture=posture, foe=foe_adj, obj=obj, art=art, base=base,
              dist=f"{plan.start_distance_nm:.0f}", act=f"{plan.activation_radius_nm:.0f}")
    if mt is M.INTERCEPT:
        facts = [f for f in facts if f[0] not in ("Posture", "Launching from")]
        facts.append(("Scenario", "Scramble: enemy raid inbound"))
        facts.append(("Start", "Hot start on the carrier" if plan.carrier else "Runway scramble"))
        home = "the carrier group" if plan.carrier else "our field"
        kw["home"] = home
        situation = [
            rng.choice([
                "Scramble, scramble! {opener} Our radars have picked up a {foe} strike package heading "
                "for {home}. It's a raid, and it'll be on us in minutes.",
                "{opener} We have a problem. Radar shows a {foe} strike package inbound for {home}, "
                "closing fast. Bombers and escorts, and we're the only ones who can stop them.",
                "Heads up, this is not a drill. A {foe} raid has just popped up on the scope, "
                "tracking toward {home}. {opener}",
            ]).format(**kw),
            rng.choice([
                "There's no time for a long brief. Get airborne, get up high, and meet them at the "
                "Intercept point before they can drop.",
                "You won't get a second chance at this. Launch, climb, and be at the Intercept point "
                "before the bombers are in range of anything we care about.",
                "Every minute on the ground is a minute the raid gets closer. Get off the deck and "
                "set up at the Intercept point.",
            ]),
        ]
        mission = [rng.choice([
            "Intercept and destroy the inbound raid. {cs} (that's you if you picked the primary slot) "
            "is the lead scramble; the other flights follow you off the runway and support the intercept.",
            "Your job is simple: stop that raid. {cs} leads the intercept (that's you if you picked the "
            "primary slot) and the rest of the alert flights follow you up.",
            "Kill the bombers before they reach their release point. {cs} is the lead (you, if you "
            "picked the primary slot); everyone else backs you up.",
        ]).format(cs=primary.callsign)]
        raid = _raid_lines(plan)
    elif req.posture is Posture.PREEMPTIVE:
        situation = [
            rng.choice([
                "{opener} Today is {posture}. The {foe} forces aren't expecting us, and I'd like to keep "
                "it that way. They've got {art} {obj} sitting out there on a {dist}-mile run from {base}, "
                "and it needs to go away.",
                "{opener} This is {posture}. Nobody over there knows we're coming. {art} {obj} is "
                "{dist} miles out from {base}, and today we remove it.",
                "{opener} We're going first today: {posture}. The {foe} side thinks it's still at peace. "
                "Their {obj} is a {dist}-mile flight from {base}, and we're going to take it off "
                "the board before they can react.",
                "{opener} It's {posture}, and surprise is the whole plan. {art} {obj} sits {dist} "
                "miles from {base}. Get in unseen, hit it, get out.",
            ]).format(**kw),
            rng.choice([
                "Their air defences are on standby: expect them to wake up when we're around {act} nm "
                "from the objective. Their fighters are on the ground and will scramble once they spot "
                "us. With luck they get airborne only as we reach the target, so the fight comes after "
                "the strike. So: quiet in, hard hit, and out again before they get organised.",
                "The radars are cold for now. They come alive about {act} nm from the objective, and "
                "their alert fighters launch once we're spotted. Plan on the strike going in first and "
                "the dogfight coming on the way home.",
                "Don't expect a warm welcome until we're about {act} nm out; then the SAMs wake up and "
                "the interceptors start rolling. If we're quick, they're still climbing when we're "
                "already off the target.",
            ]).format(**kw),
        ]
    elif plan.frontline is None:             # active war with no land front: a naval strike
        situation = [
            rng.choice([
                "{opener} The fleet is at sea and the shooting has started. The {foe} side has "
                "fighters up already, and the {obj} is our problem: it's a {dist}-mile run from {base}.",
                "{opener} It's a shooting war at sea. The {foe} navy is out there, their fighters are "
                "airborne, and the {obj} is the one we're after, {dist} miles from {base}.",
                "{opener} Naval war today. The {obj} has to go, it's {dist} miles from {base}, and the "
                "{foe} air arm is already up looking for us.",
            ]).format(**kw),
            rng.choice([
                "Everything is live from the first minute. If their radar picks us up early, somebody "
                "will come to say hello, so keep your eyes outside and your wingman close.",
                "There's no quiet phase out there. Radars are on, missiles are armed, and nobody is "
                "going to give us a free ride in.",
            ]),
        ]
    else:
        f = plan.frontline
        where = ("right at the objective" if req.mission_type is M.CAS
                 else f"about {f.distance_nm:.0f} nm short of the objective")
        kw["where"] = where
        situation = [
            rng.choice([
                "{opener} Today is {posture}. There's a front line {where}, with both armies slugging "
                "it out, and the {foe} side has fighters up already. The {obj} is our problem: it's a "
                "{dist}-mile run from {base}.",
                "{opener} The ground war is hot. The front line sits {where}, and the {foe} side is "
                "pushing hard with fighters airborne. The {obj} is what we've been sent to deal with, "
                "{dist} miles from {base}.",
                "{opener} It's a busy day over there. Front line {where}, {foe} fighters already up, "
                "and {art} {obj} still standing. It's a {dist}-mile trip from {base}. Let's fix it.",
                "{opener} Intel has the {foe} forces under pressure but still dangerous. The front "
                "line is {where}, and the {obj} is part of what's keeping them in the fight, {dist} "
                "miles from {base}.",
            ]).format(**kw),
            rng.choice([
                "Everything is live from the first minute. If their radar picks us up early, somebody "
                "will come to say hello, so keep your eyes outside and your wingman close.",
                "No quiet phase today: radars are on and fighters are looking for us from the start. "
                "Stay tight, stay aware, and don't get drawn into a fight you don't need.",
                "Assume everything is awake. When you hear the first bandit call, don't wait to be "
                "told twice.",
            ]),
        ]
    situation.append(ERA_FLAVOUR[req.era])

    if mt is not M.INTERCEPT:
        cs = primary.callsign
        mission = [rng.choice([
            "The package objective is the {obj}. {cs} (that's you if you picked the primary slot) is "
            "the main effort; everyone else is here to make {cs} successful and get everyone home.",
            "Objective: the {obj}. {cs} (you, if you picked the primary slot) delivers the hit. The "
            "rest of the package opens the door, covers the strike and brings everyone home.",
            "Here's the job. The {obj} has to be destroyed, and {cs} (that's you if you picked the "
            "primary slot) is the one doing it. Everyone else is working to get {cs} there and back.",
            "Target: the {obj}. {cs} (that's you, if you picked the primary slot) is the main effort. "
            "The other flights are support, so use them.",
        ]).format(obj=plan.objective, cs=cs)]

    package = []
    for fl in plan.flights:
        station = ("on station" if fl.role is M.CAP else
                   "intercept" if fl.role is M.INTERCEPT else "time on target")
        package.append(f"- {fl.callsign} ({ROLE_LONG[fl.role]}): {fl.size}x {fl.aircraft_display}. " + (
            f"Already airborne at start, {station} {_clock(plan, fl.key_min)}." if fl.airborne else
            f"Engines {_clock(plan, fl.start_min)}, {station} {_clock(plan, fl.key_min)}."))
    package.append("You fly the first flight. The others are AI and run to this "
                   "schedule whether you are ready or not.")

    enemy = _threat_lines(plan, limit=5)
    if any(g.tag == "convoy" and g.side != plan.player_side for g in plan.groups):
        enemy.append("- An enemy supply convoy is on the road toward the objective. It is moving, "
                     "so it will not be where you last saw it.")
    if plan.airfield_attack:
        enemy.append("- Aircraft are parked in the open on the ramp. Pick them off before they can launch.")
    friends = []
    if plan.frontline:
        friends.append(f"- Friendly armour holds the near side of the front line, "
                       f"{plan.frontline.distance_nm:.0f} nm short of the objective.")
    if plan.frontline:
        friends.append("- The front is lively: expect fires and the odd shell landing between the armies.")
    if any(g.tag == "convoy" and g.side == plan.player_side for g in plan.groups):
        friends.append("- A friendly supply convoy is on the road to the front. Don't hit it.")
    friends.append(f"- {len(plan.flights)} flight{'s' if len(plan.flights) > 1 else ''} in the "
                   "package, all working to the same clock.")
    if plan.carrier:
        friends.append(f"- We recover on {plan.carrier.display}.")

    notes = [era.roe, era.nav_note, era.comms_note]
    support = _support_lines(plan)
    closer = rng.choice(["Questions? No? Good. Fly safe and bring everybody home.",
                         "That's it from me. Check your wingman, check your fuel, and let's go.",
                         "If it goes sideways, stay calm and fly the plan. See you on the ground.",
                         "Brief's done. Walk to the jet like you mean it, and bring it back in one piece.",
                         "You know the plan. Trust your training, trust your wingman, and good hunting.",
                         "Last thing: nobody is a hero today. Do the job, come home, and the beer's on me.",
                         "Make every weapon count and every call clear. Good luck, and I'll see you back here.",
                         "That's the picture. Stay sharp out there, and call it early if something looks wrong."])

    sections = [("Situation", situation), ("Mission", mission), ("Package", package), ("The raid", raid),
                ("Navigation to the intercept point" if mt is M.INTERCEPT else "Navigation to the target", _nav_lines(plan)), ("Support", support),
                ("What's out there", enemy or ["- No significant air defences reported."]),
                ("Friendlies", friends), ("Rules and kit", notes), ("", [closer])]
    return Page(tab="Overview", title="Overview and situation report", kind="overview",
                facts=facts, sections=[s for s in sections if s[1]])


# ---- flight pages -----------------------------------------------------------------------------

def _job(plan, f, rng):
    """The tasking paragraph, per role."""
    era = plan.era
    modern = plan.request.era in ("nineties", "modern")
    low = plan.request.era in ("mid_cold_war", "late_cold_war")
    cs, obj = f.callsign, plan.objective
    if f.role is M.STRIKE:
        how = ("You can stand off and use precision weapons from altitude. Make the first pass count."
               if modern else
               "Stay low, stay fast, and hit it on the first pass. We won't get a second look."
               if low else
               "Get in, put your ordnance on it and get out. No heroics.")
        if plan.airfield_attack:
            return [rng.choice([
                f"{cs}, you're the hammer. The {obj} is the target: hit the aircraft on the ramp first, "
                f"then the fuel and stores. {how}",
                f"{cs}, we want those jets destroyed on the ground before they ever get airborne. "
                f"Work the ramp, then the fuel and stores. {how}",
                f"{cs}, today's target is the {obj}. Parked aircraft are the priority, fuel and "
                f"stores second. {how}",
            ])]
        return [rng.choice([
            f"{cs}, you're the hammer today. We're going after the {obj}. {how}",
            f"{cs}, the {obj} is yours. Get your weapons on it, check the damage, and get out. {how}",
            f"{cs}, you carry the strike. Find the {obj}, put your ordnance on it and don't linger. {how}",
        ])]
    if f.role is M.CAS:
        return [rng.choice([
            f"{cs}, you're the cavalry. The {obj} is the problem, so find it, hit it and keep our guys "
            "on the ground out of trouble. Positively identify before you shoot: there are friendlies "
            "close by.",
            f"{cs}, our troops are pinned and the {obj} is the reason. Work with what you can see, "
            "identify before you fire, and remember there's friendly armour nearby.",
            f"{cs}, close air support today. The {obj} needs to stop, and the guys on the ground "
            "are counting on you. Confirm your target and keep your passes tight.",
        ])]
    if f.role is M.SEAD:
        sam = next((g for g in plan.groups if g.tag == "sam"), None)
        sam_name = _short(sam.name) if sam else "the SAM site"
        return [rng.choice([
            f"{cs}, you're the door-kickers. Take out the {sam_name} so the strikers can get in. "
            "Shoot from the Launch point, then press on or turn away depending on how things look. "
            "The strike is behind you, so make the hole before they arrive.",
            f"{cs}, the strikers can't go in until the {sam_name} is blinded. Launch from the Launch "
            "point, watch the radar, and keep that site busy until the hole is open.",
            f"{cs}, SEAD tasking: suppress the {sam_name}. Shoot early, shoot from standoff, and "
            "clear the way before the strike package reaches it.",
        ])]
    if f.role is M.DEAD:
        return [rng.choice([
            f"{cs}, your target is the {obj} itself. Don't just scare it into switching off: kill it, "
            "then clean up whatever is left.",
            f"{cs}, we need that site dead, not just quiet. Hit the {obj}, confirm it's down, and "
            "finish whatever is still standing.",
            f"{cs}, destroy the {obj}. Take it apart, radar and launchers both, and don't leave "
            "anything that can come back to life.",
        ])]
    if f.role is M.INTERCEPT:
        return [rng.choice([
            f"{cs}, you're the alert fighter. A raid is inbound and it's heading for our field. "
            "Scramble, get to the Intercept point and kill the bombers before they can drop. Shoot "
            "the escorts only if they stop you getting to the bombers.",
            f"{cs}, you're on alert. Get off the ground, climb, and take the bombers out before "
            "they release. Escorts are second priority unless they block you.",
            f"{cs}, scramble and intercept. The bombers are the threat, so go through the escorts "
            "only if you have to and kill the strikers before they reach their target.",
        ])]
    if f.role is M.NAVAL:
        return [rng.choice([
            f"{cs}, you're the ship killer. The target is the {obj}. Find it on the radar, identify "
            "it, and put your weapons on it. Watch out for the escorts: they have teeth.",
            f"{cs}, your target is the {obj}. Locate it, make sure you've got the right ship, then "
            "launch. The escorts will shoot back, so don't hang around.",
            f"{cs}, anti-ship strike on the {obj}. Get a good picture on the radar, pick your "
            "moment and hit it hard. Keep clear of the escorts' missile envelopes.",
        ])]
    return [rng.choice([
        f"{cs}, you're the shield. Hold the CAP station, keep the bandits off the strikers' necks and "
        "shoot anything hostile in the air. Stay between the threat and the package.",
        f"{cs}, you're the top cover. Hold station, watch the radar, and make sure nothing reaches "
        "the strikers. Engage anything hostile that comes our way.",
        f"{cs}, CAP tasking: keep the air clear. Stay between the bandits and the package, and "
        "don't chase anything out of the area.",
    ])]


def _together(plan, f):
    lines = []
    for o in _others(plan, f):
        if f.role is M.CAP:
            lines.append(f"- {o.callsign} ({ROLE_LABEL[o.role]}) is the package you're covering, "
                         f"on target {_clock(plan, o.key_min)}.")
        elif o.role is M.CAP:
            lines.append(f"- {o.callsign} (CAP) is up top, on station at {_clock(plan, o.key_min)}. "
                         "Call it if you see something they might miss.")
        elif o.role is M.SEAD and f.role in (M.STRIKE, M.CAS, M.DEAD):
            lines.append(f"- {o.callsign} (SEAD) goes {_delta(f.key_min, o.key_min)} you. "
                         "Don't cross the IP before they've done their work unless you're "
                         "being shot at.")
        elif o.role is M.STRIKE and f.role in (M.SEAD, M.DEAD):
            lines.append(f"- {o.callsign} (strike) is {_delta(f.key_min, o.key_min)} you. "
                         "They're counting on you to open the door.")
        else:
            lines.append(f"- {o.callsign} ({ROLE_LABEL[o.role]}) works the same area, "
                         f"on target {_clock(plan, o.key_min)}.")
    return lines or ["- You're on your own for this one, so watch your own six."]


def _contingency(plan, f):
    req = plan.request
    out = []
    crng = random.Random(f"cont|{req.seed}|{req.mission_type.value}|{f.role.value}")
    if req.mission_type is M.INTERCEPT:
        return ["- Check in with AWACS for the picture before you merge, if one is up.",
                "- The bombers are the priority. Don't let the escorts drag you into a fight that "
                "lets the strikers through.",
                "- If you're low on fuel or out of missiles, break off, but not before the "
                "bombers are dealt with. Then home you go."]
    if req.mission_type is M.NAVAL:
        return ["- Ships shoot back with serious missiles. Keep your approach low or fast, and "
                "don't loiter inside their reach.",
                "- Make sure you've got the right ship before you launch: look at the picture, "
                "and the cargo ships are not the ones shooting at you.",
                "- If you're hit, losing a wingman, or low on fuel: abort to the Egress and "
                "head home."]
    if req.posture is Posture.PREEMPTIVE:
        out.append(f"- Their radars stay cold until we're about {plan.activation_radius_nm:.0f} nm "
                   "out, then everything lights up at once.")
        out.append("- Their alert fighters launch when we're spotted. Normally that's late enough that "
                   "we're off the target before they reach us, but no plan survives contact: "
                   "check your six on the way out, and keep an eye out on the way in.")
    else:
        out.append(crng.choice([
            "- Everything is already live. If you hear a bandit call, drop what you're "
            "doing and sort it out.",
            "- Expect company from the first minute. A bandit call overrides everything else on the plan.",
            "- There's no cold phase today. Treat every contact as hostile until you know better, "
            "and keep your head on a swivel."]))
    out.append(crng.choice([
        "- If you're hit, losing a wingman, or low on fuel: abort to the Egress and "
        "head home. Nobody gets a medal for staying.",
        "- Damaged, short on fuel or missing a wingman? Turn for the Egress and get home. "
        "The mission isn't worth a lost aircraft.",
        "- Make the call early if something goes wrong. Aborting to the Egress is always "
        "an option, and a good one."]))
    if f.role is not M.CAP:
        out.append(crng.choice([
            "- If the target is already gone when you get there, hit your secondary or "
            "bring the ordnance home. Don't waste it.",
            "- Nothing left at the target? Don't drop on empty ground. Look for something nearby "
            "worth hitting, or take the weapons home.",
            "- If someone beat you to it, confirm it visually before you release, then move on or "
            "come home with your ordnance."]))
    return out


def _flight_page(plan, f, rng):
    era = plan.era
    station = ("On station" if f.role is M.CAP else
               "Intercept time" if f.role is M.INTERCEPT else "Time on target")
    facts = [
        ("Callsign", f"{f.callsign}-1"),
        ("Aircraft", f"{f.size}x {f.aircraft_display}"),
        ("Role", ROLE_LONG[f.role]),
        ("Engines", "Already airborne at mission start" if f.airborne
         else f"{_clock(plan, f.start_min)} (T+{f.start_min:02d})"),
        (station, f"{_clock(plan, f.key_min)} (T+{f.key_min:02d})"),
        ("Land", f"about {_clock(plan, f.end_min)}"),
    ]
    if plan.nav and f.role is not M.CAP:
        use_sam = f.role is M.SEAD and "sead" in plan.nav
        facts.append(("SAM site" if use_sam else _target_label(plan),
                      _position_text(plan, plan.nav["sead" if use_sam else "target"])))
    header, rows = route_table(plan, f)
    threats = _threat_lines(plan, limit=4 if f.role is not M.CAP else 3)
    sections = [
        ("Your job", _job(plan, f, rng)),
        ("Working together", _together(plan, f)),
        ("What's out there", threats or ["- Nothing significant reported."]),
        ("If it goes wrong", _contingency(plan, f)),
        ("Loadout", ([f"- {w}" for w in f.weapons] + [f"Plus guns. ({f.loadout})"]) if f.weapons
                    else [f"Think {f.loadout}."]),
    ]
    role = ROLE_LABEL[f.role]
    return Page(tab=f"{role} - {f.callsign}", title=f"{ROLE_LONG[f.role]} flight: {f.callsign}",
                kind="flight", facts=facts, sections=sections, flight=f, route=rows,
                route_header=header)


# ---- entry points -----------------------------------------------------------------------------

RECON = {
    ("blue", "early_cold_war"): "an RF-86F reconnaissance sortie",
    ("blue", "mid_cold_war"): "an RF-4C Phantom photo-recon pass",
    ("blue", "late_cold_war"): "an RF-4C low-level pass, backed by a high-altitude U-2 run",
    ("blue", "nineties"): "a TR-1 high-altitude pass and national imagery",
    ("blue", "modern"): "an MQ-9 Reaper orbit and satellite imagery",
    ("red", "early_cold_war"): "a MiG-15 reconnaissance sortie",
    ("red", "mid_cold_war"): "a MiG-25R high-speed recon pass",
    ("red", "late_cold_war"): "a MiG-25RB and Su-24MR reconnaissance sortie",
    ("red", "nineties"): "an Su-24MR reconnaissance pass",
    ("red", "modern"): "a drone orbit and satellite imagery",
}


def _target_label(plan):
    return {M.INTERCEPT: "Intercept point", M.NAVAL: "Target ship"}.get(plan.request.mission_type, "Target")


def _position_text(plan, ll):
    """One line for a map position, in the format the era's navigation kit uses."""
    lat, lng = ll
    if plan.request.era == "modern":
        return f"{navinfo.dm(lat, lng, 3)}   MGRS {navinfo.mgrs(lat, lng)}"
    if plan.request.era == "nineties":
        return navinfo.dm(lat, lng, 3)
    return navinfo.dm(lat, lng, 1)


def _nav_lines(plan):
    nav = plan.nav
    if not nav:
        return ["- Target coordinates are added when the mission is built."]
    era = plan.request.era
    lines = [f"- {_target_label(plan)}: {_position_text(plan, nav['target'])}"]
    if "sead" in nav and any(f.role.value in ("sead", "dead") for f in plan.flights):
        lines.append(f"- SAM site: {_position_text(plan, nav['sead'])}")
    lines.append(f"- From {nav['base']}: bearing {nav['bearing']:03.0f} true, {nav['range_nm']:.0f} nm "
                 f"to the {'intercept point' if plan.request.mission_type is M.INTERCEPT else 'target'}.")
    if plan.request.mission_type is M.NAVAL:
        lines.append("- Ships move: this is where the intel puts it, so confirm it on radar or by eye.")
    how = {
        "early_cold_war": "No GPS in these days: plot the position on your chart, fly the heading "
                          "and time your legs.",
        "mid_cold_war": "Plot it on your chart and cross-check with TACAN where it reaches. "
                        "Dead reckoning is still the backbone.",
        "late_cold_war": "Punch the position into the INS if you have one, and keep the "
                         "bearing and range as your cross-check.",
        "nineties": "Enter it as a GPS waypoint, but keep the bearing and range handy "
                    "in case the satellites let you down.",
        "modern": "Enter it as a waypoint or steerpoint (lat/long or MGRS, whichever your jet likes) "
                  "and confirm it against the picture.",
    }[era]
    lines.append(f"- {how}")
    return lines


def _support_lines(plan):
    out = []
    for s in plan.support:
        if s.kind == "awacs":
            out.append(f"- AWACS: {s.callsign} ({s.display}), {s.frequency:.3f} AM, on a racetrack "
                       f"behind the ingress at about {s.altitude_ft // 1000},000 ft.")
        else:
            how = {"boom": "flying boom", "drogue": "probe and drogue",
                   "both": "flying boom and probe-and-drogue"}[s.method]
            out.append(f"- Tanker: {s.callsign} ({s.display}, {how}), {s.frequency:.3f} AM, "
                       f"TACAN {s.tacan}, racetrack at about {s.altitude_ft // 1000},000 ft near "
                       "the ingress route.")
    return out


def _imagery_page(plan, rng, group, tab, label):
    """A page of two aerial photos (wide and close-up) of one target, with an intel cover story."""
    what = group.name.split(" - ", 1)[-1]
    hours = rng.randint(12, 72)
    taken = plan.start_time - timedelta(hours=hours)
    source = RECON.get((plan.player_side, plan.request.era), "a reconnaissance sortie")
    nearby = [g for g in plan.groups if g is not group and g.kind in ("vehicle", "ship")
              and math.hypot(*_xy_nm(g.bearing_deg, g.distance_nm, group)) < 3.0]
    notes = [f"- Imagery from {source}, taken about {hours} hours before takeoff "
             f"({taken:%d %b}, around {taken:%H%M} local).",
             "- Photo 1 is the wide view, about 3 nm across. Photo 2 is the close-up of the "
             f"{what}. North is up.",
             "- It's already a day or more old: fixed structures will be where we show them, but "
             "anything with wheels or tracks may have moved, and air defences can be shifted overnight."]
    if nearby:
        kinds = sorted({g.name.split(" - ", 1)[-1] for g in nearby})[:4]
        notes.append(f"- Also in frame: {', '.join(kinds)}.")
    statics = [g for g in plan.statics if g.placement == "relative" and g.side == plan.enemy_side]
    if group.kind == "ship":
        notes[2] = ("- It's already a day or more old: ships move, so treat this as where the target "
                    "was, not where it will be. Expect the escorts to have shifted too.")
    if statics and group.tag == "target":
        notes.append(f"- Buildings, tanks and stores ({len(statics)} structures) surround the area.")
    facts = [("Target", what), ("Source", source), ("Image age", f"about {hours} hours")]
    if plan.nav:
        pos = plan.nav["sead"] if group is plan.sead_target and "sead" in plan.nav else plan.nav["target"]
        facts.append(("Position", _position_text(plan, pos)))
    return Page(tab=tab, title=f"{label}: {what}", kind="imagery", facts=facts,
                sections=[("Imagery notes", notes)], flight=None, target=group, age_hours=hours)


def _xy_nm(bearing, dist, ref):
    ax = ref.distance_nm * math.sin(math.radians(ref.bearing_deg))
    ay = ref.distance_nm * math.cos(math.radians(ref.bearing_deg))
    bx = dist * math.sin(math.radians(bearing))
    by = dist * math.cos(math.radians(bearing))
    return bx - ax, by - ay


def compose(plan):
    """Build the full briefing (overview + one page per flight) for a plan."""
    rng = random.Random(f"brief|{plan.request.seed}|{plan.request.era}|{plan.request.mission_type.value}")
    lead = plan.flights[0].callsign.split()[0].upper()
    code = f"OPERATION {lead} {100 + plan.request.seed % 900}"
    pages = [_overview(plan, rng)]
    target = next((g for g in plan.groups if g.tag == "target"), None)
    if target is not None:
        pages.append(_imagery_page(plan, rng, target, "Target Photos", "Target imagery"))
    sead = plan.sead_target
    if sead is not None and sead is not target and any(f.role.value == "sead" for f in plan.flights):
        pages.append(_imagery_page(plan, rng, sead, "SAM Photos", "SAM site imagery"))
    pages += [_flight_page(plan, f, rng) for f in plan.flights]
    return Briefing(code=code, pages=pages)


def build_briefing(plan):
    """The whole briefing as plain text (used for the DCS mission description and --dry-run)."""
    return compose(plan).as_text()
