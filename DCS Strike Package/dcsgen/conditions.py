"""Time of day, season and weather: the choices, the date maths and what each means in DCS.

Pure Python. Sunrise and sunset come from a standard solar formula using each map's latitude,
longitude and clock offset, so "10 minutes after sunrise" is close to right for the chosen map
and season (not exact: DCS's own sun can differ by a few minutes).
"""

import math
from datetime import datetime, timedelta

TIME_LABEL = {
    "day": "Daytime (about 11:00)",
    "night": "Night",
    "sunrise": "Sunrise (10 min after)",
    "presunrise": "Pre-sunrise (10 min before)",
    "sunset": "Sunset (25 min before)",
    "random": "Random",
}
TIME_PHRASE = {
    "day": "daylight", "night": "in the dark", "sunrise": "just after sunrise",
    "presunrise": "just before sunrise", "sunset": "shortly before sunset",
}

SEASON_LABEL = {"random": "Random", "summer": "Summer", "winter": "Winter",
                "spring": "Spring", "autumn": "Autumn"}

# (month, first day, last day) windows; winter runs across the new year
_SEASON_DATES = {
    "summer": ((6, 10), (8, 20)),
    "autumn": ((9, 20), (11, 5)),
    "winter": ((12, 5), (2, 5)),
    "spring": ((3, 25), (5, 15)),
}
# nominal outside temperature (deg C) per season for the mission
SEASON_TEMP = {"summer": 27.0, "autumn": 12.0, "winter": -3.0, "spring": 13.0}

# key -> (label, briefing text, DCS settings)
WEATHER = {
    "clear": ("Clear", "clear skies",
              dict(density=0, base=3000, thick=200, precip=0, vis=80000, fog=0, wind=3)),
    "few": ("Few clouds", "a few clouds at 8,000 ft",
            dict(density=2, base=2400, thick=300, precip=0, vis=80000, fog=0, wind=5)),
    "scattered": ("Scattered clouds", "scattered cloud at 5,000 ft",
                  dict(density=4, base=1500, thick=400, precip=0, vis=80000, fog=0, wind=6)),
    "broken": ("Broken clouds", "broken cloud at 4,000 ft",
               dict(density=7, base=1200, thick=600, precip=0, vis=60000, fog=0, wind=8)),
    "overcast": ("Overcast", "overcast at 3,000 ft",
                 dict(density=10, base=900, thick=800, precip=0, vis=40000, fog=0, wind=9)),
    "rain": ("Rain", "overcast with steady rain, low cloud and reduced visibility",
             dict(density=9, base=600, thick=700, precip=1, vis=15000, fog=0, wind=10)),
    "thunderstorm": ("Thunderstorm", "thunderstorms with heavy cloud, rain and gusty wind",
                     dict(density=10, base=700, thick=1500, precip=2, vis=10000, fog=0, wind=14)),
    "fog": ("Fog", "fog and low cloud: expect under two miles of visibility on the ground",
            dict(density=6, base=300, thick=300, precip=0, vis=8000, fog=1, wind=2)),
    "haze": ("Haze", "haze with about six miles of visibility",
             dict(density=1, base=3000, thick=200, precip=0, vis=9000, fog=0, wind=4)),
}
WEATHER_LABEL = {"random": "Random", **{k: v[0] for k, v in WEATHER.items()}}
DEFAULT_WEATHER = "scattered"


def weather_text(key):
    return WEATHER[key][1]


# ---- sun --------------------------------------------------------------------------------------

OPPOSITE = {"summer": "winter", "winter": "summer", "spring": "autumn", "autumn": "spring"}


def sun_times(lat, lon, utc_offset, day):
    """(sunrise, sunset) as naive local datetimes for `day` (a date), using the NOAA algorithm.

    Polar day or night returns (06:00, 18:00) so callers always get something usable."""
    n = day.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    lat_r = math.radians(lat)
    cos_ha = (math.cos(math.radians(90.833)) / (math.cos(lat_r) * math.cos(decl))
              - math.tan(lat_r) * math.tan(decl))
    midnight = datetime(day.year, day.month, day.day)
    if not -1 <= cos_ha <= 1:
        return midnight + timedelta(hours=6), midnight + timedelta(hours=18)
    ha = math.degrees(math.acos(cos_ha))
    rise_utc_min = 720 - 4 * (lon + ha) - eqtime
    set_utc_min = 720 - 4 * (lon - ha) - eqtime
    return (midnight + timedelta(minutes=rise_utc_min + utc_offset * 60),
            midnight + timedelta(minutes=set_utc_min + utc_offset * 60))


def pick_date(rng, year, season):
    """A date in the season (northern hemisphere), as a datetime at midnight."""
    (m0, d0), (m1, d1) = _SEASON_DATES[season]
    start = datetime(year, m0, d0)
    end = datetime(year + (1 if m1 < m0 else 0), m1, d1)
    span = (end - start).days
    pick = start + timedelta(days=rng.randint(0, span))
    return datetime(year, pick.month, pick.day)


def start_clock(tod, lat, lon, utc_offset, day):
    """Local start time (naive datetime) for a time-of-day choice on a given date."""
    rise, sset = sun_times(lat, lon, utc_offset, day)
    midnight = datetime(day.year, day.month, day.day)
    if tod == "sunrise":
        return rise + timedelta(minutes=10)
    if tod == "presunrise":
        return rise - timedelta(minutes=10)
    if tod == "sunset":
        return sset - timedelta(minutes=25)
    if tod == "night":
        return midnight + timedelta(hours=1, minutes=30)
    return midnight + timedelta(hours=11)


DEFENCES_LABEL = {
    "light": "Light - no SAMs, AAA only",
    "medium": "Medium - one or two SAM sites",
    "heavy": "Heavy - saturated, layered SAMs",
}
DEFAULT_DEFENCES = "medium"

_MISSION_DEFENCES = {
    "naval": {"light": "Light - lone target, no escort ships",
              "medium": "Medium - 1 or 2 escort ships",
              "heavy": "Heavy - 4 to 6 escort ships"},
    "intercept": {"light": "Light - 2 bombers, no escort",
                  "medium": "Medium - 3 bombers, 2 escorts",
                  "heavy": "Heavy - 4 bombers, 4 escorts"},
}


def defences_labels(mission):
    """The Enemy defences choices, worded for what that mission's defences actually are."""
    return _MISSION_DEFENCES.get(mission, DEFENCES_LABEL)
