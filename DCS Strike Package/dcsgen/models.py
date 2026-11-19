"""Plain data structures shared by the planner, briefing and builder.

Positions in a plan are relative: a bearing (degrees, true) and a distance (nm)
from the package objective, which sits at the origin. The builder places that
origin on a real map, so the planner never needs any map data.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class MissionType(str, Enum):
    STRIKE = "strike"
    CAS = "cas"
    SEAD = "sead"
    DEAD = "dead"
    CAP = "cap"
    INTERCEPT = "intercept"   # scramble to meet an incoming enemy strike
    NAVAL = "naval"           # anti-ship strike


class Posture(str, Enum):
    PREEMPTIVE = "preemptive"
    ACTIVE_WAR = "active_war"


@dataclass(frozen=True)
class StartLocation:
    kind: str = "airbase"   # "airbase", "carrier" or "supercarrier"
    name: str = ""          # airbase name or carrier key; empty means the default


SIDES = ("blue", "red")


def enemy_of(side: str) -> str:
    return "red" if side == "blue" else "blue"


@dataclass
class MissionRequest:
    era: str
    map_key: str
    aircraft: str
    mission_type: MissionType
    posture: Posture = Posture.ACTIVE_WAR
    start: StartLocation = field(default_factory=StartLocation)
    seed: int = 0
    flights: int = 3          # size of the package, 1 to 3 simultaneous missions
    flight_size: int = 2      # aircraft in the primary flight
    max_units: int = 240      # performance budget for the whole mission (aircraft + ground units)
    side: str = "blue"        # the side the player flies for: "blue" or "red"
    start_state: str = "cold"     # cold | hot | runway
    any_aircraft: bool = False    # True: offer every aircraft of the side, not just historical ones
    time_of_day: str = "day"      # day | night | sunrise | presunrise | sunset | random
    season: str = "random"        # random | summer | winter | spring | autumn
    weather: str = "scattered"    # see conditions.WEATHER, or "random"
    ground_units: int = 80        # active ground units around the target (60-100)
    frontline_units: int = 80     # extra: the two armies facing each other (active war), 0-160
    statics: int = 35             # static objects to dress airfields and the target (20-50)
    awacs: bool = True            # add an AWACS orbit when one existed on that side and date
    tanker: bool = False          # add a tanker matched to the main aircraft
    defences: str = "medium"      # light | medium | heavy: how many SAM sites defend the target
    player_country: str = "default"   # "default" or a countries.py key for the player's side
    enemy_country: str = "random"     # "random" (weighted by era) or a countries.py key


@dataclass
class Waypoint:
    name: str
    bearing_deg: float
    distance_nm: float
    altitude_ft: int
    speed_kts: int
    action: str = "fly"       # fly | orbit | attack | land


@dataclass
class Activation:
    mode: str = "always"      # always | proximity | scramble
    radius_nm: float = 0.0    # trigger radius around the objective
    delay_s: int = 0


@dataclass
class Group:
    name: str
    side: str                 # "red" or "blue"
    kind: str                 # vehicle | plane | ship | static
    units: list               # [[pydcs_class_name, count], ...]; first entry is the core unit
    bearing_deg: float
    distance_nm: float
    heading_deg: float = 0.0
    tag: str = ""             # target | sam | aaa | ewr | cap | scramble | frontline | route
    priority: int = 5         # lower number = more important, trimmed last
    optional: bool = False    # the whole group may be dropped to meet the unit budget
    min_total: int = 0        # never trim below this many units
    range_nm: float = 0.0     # lethal range, for threats
    activation: Activation = field(default_factory=Activation)
    placement: str = "relative"   # relative | enemy_airbase | start_airbase
    route: list = field(default_factory=list)   # air raids: [(bearing, distance_nm), ...] after the start
    alt_ft: int = 0           # air raids: cruise altitude
    speed_kts: int = 0        # air raids: cruise speed
    pylons: dict = field(default_factory=dict)   # aircraft: {station: weapon name} chosen by loadouts

    @property
    def count(self) -> int:
        return sum(c for _, c in self.units)

    @property
    def floor(self) -> int:
        return max(len(self.units), self.min_total)


@dataclass
class FlightPlan:
    callsign: str
    role: MissionType
    aircraft_key: str
    aircraft_display: str
    pydcs_name: str
    size: int
    waypoints: list
    key_waypoint: str
    tasking: str
    loadout: str
    primary: bool = False
    start_min: int = 0        # engine start, minutes after mission start
    key_min: int = 0          # time on target / on station
    end_min: int = 0          # landing
    service: str = ""         # "USAF", "USN", "VVS"...; picks the briefing header
    dwell_min: int = 0        # minutes held on station after the key waypoint (CAP, intercept)
    pylons: dict = field(default_factory=dict)   # {station: weapon name}, see loadouts.py
    weapons: list = field(default_factory=list)  # the same in words: ['2 x AIM-9M ...', ...]
    airborne: bool = False    # supporting CAP/SEAD already in the air at mission start
    runway_start: bool = False  # supporting flight lined up on the runway while the player starts hot


@dataclass
class SupportAsset:
    """An AI support aircraft (AWACS or tanker) flying a racetrack for the package."""
    kind: str                 # "awacs" | "tanker"
    display: str              # "E-3A Sentry"
    pydcs_name: str
    callsign: str             # name used in the briefing (the builder replaces it with the in-game one)
    bearing_deg: float        # position of the racetrack start, plan coordinates (like Group)
    distance_nm: float
    heading_deg: float        # racetrack heading, plan coordinates
    altitude_ft: int
    speed_kts: int
    frequency: float          # AM, MHz
    race_nm: float = 30.0
    tacan: str = ""           # tanker only, e.g. "41X"
    method: str = ""          # tanker only: "boom", "drogue" or "both"
    note: str = ""


@dataclass
class Frontline:
    bearing_deg: float
    distance_nm: float
    heading_deg: float
    length_nm: float


@dataclass
class Ambient:
    """Life around the player's airfield: trucks, AA guns, parked aircraft, helicopter traffic."""
    name: str
    side: str
    kind: str                 # vehicle | aaa | parked | heli
    candidates: tuple         # pydcs class names, tried in order
    count: int = 1
    role: str = ""            # heli: resupply | cas | arrival
    start_min: int = 0        # heli: minutes after mission start
    heading_deg: float = 0.0


@dataclass
class MissionPlan:
    request: MissionRequest
    era: object
    map_display: str
    start_time: datetime
    weather: str
    objective: str
    flights: list
    groups: list
    approach_bearing: float
    start_distance_nm: float
    activation_radius_nm: float
    scramble_radius_nm: float
    frontline: Optional[Frontline]
    carrier: Optional[object]
    tot_min: int
    units_before_budget: int = 0
    notes: list = field(default_factory=list)
    player_side: str = "blue"
    enemy_side: str = "red"
    # Compass rotation applied to every bearing in the plan to get true bearings on the map.
    # Until the builder places the mission, this is a schematic value that points the
    # approach north (geometry_final False); the builder replaces it with the real one.
    rotation_deg: float = 0.0
    geometry_final: bool = False
    statics: list = field(default_factory=list)      # static-object groups (not counted in the budget)
    sead_target: Optional[object] = None             # the Group the SEAD flight is hunting, if any
    time_of_day: str = "day"
    season: str = "summer"
    weather_key: str = "scattered"
    support: list = field(default_factory=list)      # SupportAsset entries (not in the unit budget)
    nav: dict = field(default_factory=dict)          # target coordinates etc., filled in by the builder
    year: int = 0
    early_intercept: bool = False                    # pre-emptive: the alert fighters launch early
    flight_minutes: int = 20                         # planned airborne time of the main flight
    countries: dict = field(default_factory=dict)    # side -> countries.CountryChoice
    ambient: list = field(default_factory=list)      # Ambient airbase life (not in the unit budget)
    airfield_attack: bool = False                    # a strike on aircraft parked at an enemy airfield
    objective_normal: str = ""                        # the objective text if no suitable airfield is found

    @property
    def total_units(self) -> int:
        return (sum(f.size for f in self.flights)
                + sum(g.count for g in self.groups)
                + (1 if self.carrier else 0))
