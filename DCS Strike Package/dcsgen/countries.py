"""Countries the player and the enemy can belong to, with era-aware weighting.

A country changes the flag, the callsign/livery set and the wording in the briefing. The
equipment (SAMs, tanks, fighters) still follows the era's Blue and Red factions, so an
"Iranian" enemy in the modern era fields the modern Red kit.

Keys are stable names stored in saved settings. "russia" means the Soviet Union before
1992 and Russia after; "yugoslavia" means Yugoslavia, then Serbia.
"""

import random
import re
from dataclasses import dataclass

ERA_KEYS = ("early_cold_war", "mid_cold_war", "late_cold_war", "nineties", "modern")
ALL = frozenset(ERA_KEYS)
ANY = "random"
DEFAULT = "default"


@dataclass(frozen=True)
class CountryChoice:
    key: str
    display: str
    adjective: str
    pydcs: tuple            # candidate pydcs country names, best first


def _e(*keys):
    return frozenset(keys)


# key: (display, adjective, pydcs names, eras)
BLUE = {
    "usa": ("United States", "American", ("USA",), ALL),
    "uk": ("United Kingdom", "British", ("UK", "United Kingdom"), ALL),
    "france": ("France", "French", ("France",), ALL),
    "germany": ("Germany", "German", ("Germany",), ALL),
    "canada": ("Canada", "Canadian", ("Canada",), ALL),
    "australia": ("Australia", "Australian", ("Australia",), ALL),
    "netherlands": ("Netherlands", "Dutch", ("The Netherlands", "Netherlands"), ALL),
    "belgium": ("Belgium", "Belgian", ("Belgium",), ALL),
    "norway": ("Norway", "Norwegian", ("Norway",), ALL),
    "denmark": ("Denmark", "Danish", ("Denmark",), ALL),
    "italy": ("Italy", "Italian", ("Italy",), ALL),
    "spain": ("Spain", "Spanish", ("Spain",), _e("late_cold_war", "nineties", "modern")),
    "turkey": ("Turkey", "Turkish", ("Turkey",), ALL),
    "israel": ("Israel", "Israeli", ("Israel",), ALL),
    "south_korea": ("South Korea", "South Korean", ("South Korea",), ALL),
    "japan": ("Japan", "Japanese", ("Japan",), _e("mid_cold_war", "late_cold_war", "nineties", "modern")),
    "poland": ("Poland", "Polish", ("Poland",), _e("nineties", "modern")),
}
RED = {
    "russia": ("Russia", "Russian", ("Russia",), ALL),          # USSR before 1992, see _soviet
    "china": ("China", "Chinese", ("China",), ALL),
    "north_korea": ("North Korea", "North Korean", ("North Korea",), ALL),
    "cuba": ("Cuba", "Cuban", ("Cuba",), ALL),
    "egypt": ("Egypt", "Egyptian", ("Egypt",), _e("early_cold_war", "mid_cold_war", "late_cold_war")),
    "syria": ("Syria", "Syrian", ("Syria",), ALL),
    "iraq": ("Iraq", "Iraqi", ("Iraq",), _e("mid_cold_war", "late_cold_war", "nineties")),
    "libya": ("Libya", "Libyan", ("Libya",), _e("mid_cold_war", "late_cold_war", "nineties")),
    "iran": ("Iran", "Iranian", ("Iran",), _e("late_cold_war", "nineties", "modern")),
    "vietnam": ("Vietnam", "Vietnamese", ("Vietnam",), _e("early_cold_war", "mid_cold_war", "late_cold_war")),
    "yugoslavia": ("Yugoslavia", "Yugoslav", ("Yugoslavia", "Serbia"), ALL),
    "belarus": ("Belarus", "Belarusian", ("Belarus",), _e("nineties", "modern")),
}
TABLE = {"blue": BLUE, "red": RED}

# Chance (percent) of each country when the enemy is "random". Russia/USSR is 40% against a
# blue player and the USA is 70% against a red player; the rest is split by era.
FIXED_SHARE = {"red": ("russia", 40), "blue": ("usa", 70)}
ENEMY_WEIGHTS = {
    "red": {
        "early_cold_war": {"china": 18, "north_korea": 14, "egypt": 10, "syria": 6, "cuba": 6,
                            "yugoslavia": 6, "vietnam": 0},
        "mid_cold_war": {"china": 8, "north_korea": 12, "vietnam": 10, "egypt": 8, "syria": 10,
                          "iraq": 5, "libya": 4, "cuba": 3},
        "late_cold_war": {"libya": 8, "iraq": 12, "syria": 10, "north_korea": 10, "iran": 8,
                           "cuba": 4, "china": 4, "vietnam": 4},
        "nineties": {"iraq": 15, "yugoslavia": 15, "north_korea": 8, "iran": 8, "libya": 4,
                      "china": 4, "syria": 4, "cuba": 2},
        "modern": {"iran": 15, "china": 13, "syria": 10, "north_korea": 8, "belarus": 8,
                    "yugoslavia": 6},
    },
    "blue": {
        "early_cold_war": {"uk": 25, "france": 15, "canada": 15, "turkey": 15, "australia": 15,
                            "israel": 5, "south_korea": 10},
        "mid_cold_war": {"uk": 22, "france": 15, "germany": 12, "canada": 8, "israel": 15,
                          "turkey": 8, "australia": 8, "south_korea": 6, "japan": 6},
        "late_cold_war": {"uk": 22, "france": 14, "germany": 12, "israel": 14, "canada": 7,
                           "turkey": 7, "italy": 6, "spain": 5, "south_korea": 6, "japan": 7},
        "nineties": {"uk": 22, "france": 14, "germany": 12, "canada": 8, "israel": 12,
                      "turkey": 8, "italy": 8, "spain": 6, "poland": 5, "south_korea": 5},
        "modern": {"uk": 22, "france": 14, "germany": 10, "israel": 12, "poland": 8,
                    "canada": 7, "turkey": 7, "italy": 6, "japan": 6, "south_korea": 8},
    },
}


def _norm(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _soviet(era_key):
    return era_key in ("early_cold_war", "mid_cold_war", "late_cold_war")


def _choice(side, key, era_key):
    display, adj, names, _eras = TABLE[side][key]
    if side == "red" and key == "russia" and _soviet(era_key):
        return CountryChoice("russia", "Soviet Union", "Soviet", ("USSR",))
    if side == "red" and key == "yugoslavia" and era_key in ("nineties", "modern"):
        return CountryChoice(key, "Serbia", "Serbian", ("Serbia", "Yugoslavia"))
    if side == "blue" and key == "germany" and era_key in ("early_cold_war", "mid_cold_war", "late_cold_war"):
        return CountryChoice(key, "West Germany", "West German", ("Germany",))
    return CountryChoice(key, display, adj, names)


def available(side, era_key):
    """[(key, display)] of the countries offered for a side in an era, default first."""
    out = [(k, _choice(side, k, era_key).display) for k, v in TABLE[side].items() if era_key in v[3]]
    first = "usa" if side == "blue" else "russia"
    out.sort(key=lambda kv: (kv[0] != first, kv[1]))
    return out


def valid_player(side, era_key, key):
    return key == DEFAULT or key in dict(available(side, era_key))


def choose_enemy(side_of_enemy, era_key, key, rng):
    """Resolve the enemy's country key. `key` is DEFAULT/"random" or a specific country."""
    if key not in (ANY, DEFAULT) and key in dict(available(side_of_enemy, era_key)):
        return key
    fixed, share = FIXED_SHARE[side_of_enemy]
    if key == DEFAULT:
        return fixed
    if rng.random() * 100 < share:
        return fixed
    w = {k: v for k, v in ENEMY_WEIGHTS[side_of_enemy].get(era_key, {}).items()
         if v > 0 and era_key in TABLE[side_of_enemy][k][3]}
    if not w:
        return fixed
    return rng.choices(list(w), weights=list(w.values()))[0]


def resolve(request, era_key, player_side):
    """-> {"blue": CountryChoice, "red": CountryChoice}. Uses its own random stream so it
    never disturbs the layout that a given seed produced before countries existed."""
    rng = random.Random(f"country|{request.seed}|{era_key}")
    enemy_side = "red" if player_side == "blue" else "blue"
    pkey = getattr(request, "player_country", DEFAULT)
    default_player = "usa" if player_side == "blue" else "russia"
    if pkey == DEFAULT or not valid_player(player_side, era_key, pkey):
        pkey = default_player
    ekey = choose_enemy(enemy_side, era_key, getattr(request, "enemy_country", ANY), rng)
    return {player_side: _choice(player_side, pkey, era_key),
            enemy_side: _choice(enemy_side, ekey, era_key)}


def pydcs_class(countries_module, choice):
    """Find the pydcs country class for a choice, tolerating spelling differences."""
    wanted = [_norm(n) for n in choice.pydcs]
    found = {}
    for attr in dir(countries_module):
        cls = getattr(countries_module, attr)
        if not isinstance(cls, type):
            continue
        for label in (attr, getattr(cls, "name", "")):
            if isinstance(label, str) and label:
                found.setdefault(_norm(label), cls)
    for w in wanted:
        if w in found:
            return found[w]
    return None


# Extra spellings DCS livery files use for a country (3-letter codes and short names).
_CODES = {
    "USA": "USA", "Russia": "RUS RUSSIA", "USSR": "USSR SUN SOVIET RUS", "UK": "GBR UK GB",
    "France": "FRA", "Germany": "DEU GER GERMANY", "Canada": "CAN", "Australia": "AUS",
    "The Netherlands": "NLD HOL NETHERLANDS", "Belgium": "BEL", "Norway": "NOR", "Denmark": "DNK DEN",
    "Italy": "ITA", "Spain": "ESP SPN", "Turkey": "TUR", "Israel": "ISR", "South Korea": "KOR",
    "Japan": "JPN", "Poland": "POL", "China": "CHN", "North Korea": "PRK NKR", "Cuba": "CUB",
    "Egypt": "EGY", "Syria": "SYR", "Iraq": "IRQ", "Libya": "LBY", "Iran": "IRN", "Vietnam": "VNM",
    "Yugoslavia": "YUG", "Serbia": "SRB SER", "Belarus": "BLR",
}


def _country_tokens(country_name):
    toks = {_norm(country_name)}
    for t in _CODES.get(country_name, "").split():
        toks.add(_norm(t))
    return toks


def livery_ids(ptype, country_name):
    """Livery ids pydcs lists for this aircraft type and country (empty if it has none).

    pydcs 1.0 keeps `Aircraft.Liveries` as a set of Livery objects (id, name, countries) read
    from the DCS install. Older layouts (per-country enum classes) are still accepted.
    """
    wanted = _country_tokens(country_name)
    from . import liveryscan
    found = liveryscan.ids_for(getattr(ptype, "id", ""), wanted)
    if found:
        return found
    holder = getattr(ptype, "Liveries", None)
    if holder is None:
        return []
    specific, generic = [], []
    try:
        items = list(holder)
    except TypeError:
        items = []
    for it in items:
        lid = it if isinstance(it, str) else getattr(it, "id", None)
        if not isinstance(lid, str) or not lid:
            continue
        cs = getattr(it, "countries", None)
        if cs:
            try:
                toks = {_norm(str(x)) for x in cs}
            except TypeError:
                toks = set()
            if toks & wanted:
                specific.append(lid)
        else:
            generic.append(lid)
    if specific:
        return list(dict.fromkeys(specific))
    if items:
        return []                       # liveries exist, but none are for this country
    # older pydcs: Liveries.<Country> enum
    sub = None
    for n in {country_name, country_name.replace(" ", "_"), country_name.replace(" ", "")}:
        sub = getattr(holder, n, None)
        if sub is not None:
            break
    if sub is None:
        return []
    ids = []
    try:
        for mem in sub:
            v = getattr(mem, "value", mem)
            for cand in (v, getattr(v, "id", None), getattr(mem, "id", None)):
                if isinstance(cand, str) and cand:
                    ids.append(cand)
                    break
    except TypeError:
        return []
    return list(dict.fromkeys(ids))
