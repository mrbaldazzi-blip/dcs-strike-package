"""Real weapon loadouts for every flight, chosen from what each aircraft can actually carry.

pydcs lists, for every aircraft, the weapons each pylon accepts. The data this module needs (the
names only) is baked into data/pylons.json so the planner can pick loadouts without pydcs, and the
builder applies the same names to the real aircraft. A loadout depends on the flight's job and on
the mission year: no AMRAAMs in 1975 and no JDAMs in 1985.
"""

import json
import random
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "pylons.json"
_cache = {}


def table(path=DATA):
    key = str(path)
    if key not in _cache:
        try:
            _cache[key] = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _cache[key] = {}
    return _cache[key]


# ---- classifying a weapon by its pydcs name ---------------------------------------------------

# Things never carried: practice and marker rounds, pods, dispensers, dummies, reconnaissance.
EXCLUDE = re.compile(
    r"(?i)(BDU|Practice|_TP(_|$)|Smoke|Illum|SUU_25|LUU|TALD|ADM_141|CATM|TCTS|DATALINK|Datalink|ALQ|ECM|"
    r"ASO_2|Pod|POD|Pave_Spike|LITENING|AAQ|ATFLIR|HTS|ALE_40|Dispenser|Empty|inert|Inert|"
    r"non_functional|_WP|WP\d|Camera|Recon|MXU|TPOD|KINGAL|Sniper|Wing_Tip|Gunpod|GUNPOD|SUU_23|"
    r"M_61|MK_4_HIPEG|dummy|Dummy|Jammer|JAMMER|SPS_141|KG_600|L_081|Fantasmagoria|Vinten|PTB.*Empty|"
    r"SM$|_SM_|M156|M257|M274|Kmu|Mk_6\b)")
CATEGORIES = ("TANK", "AA_SHORT", "AA_MED", "SEAD", "ASHM", "ASM", "PGM", "GP", "ROCKET")
_CAT = [
    ("TANK", re.compile(r"(?i)(fuel|tank|ptb|drop)")),
    ("SEAD", re.compile(r"(AGM_88|AGM_45|Shrike|Kh_25MP|Kh_58|Kh_31P|ALARM|AGM_78|Standard_ARM|X_58|X_25MP|X_31P|AGM_122)")),
    ("ASHM", re.compile(r"(AGM_84D|AGM_84A|Harpoon|Kh_35|Kh_31A|Kh_22|Kh_59|Sea_Eagle|Exocet|AM39|Penguin|AGM_119|"
                         r"Kormoran|Kh_41|C_802|YJ_|X_31A|X_35|X_22|X_59|ASM_)")),
    ("AA_MED", re.compile(r"(AIM_120|AIM_7|AIM_54|R_27|R_77|R_24|R_40|Super_530|Meteor|Skyflash|MICA|"
                           r"R_3R|AA_10|AA_12|AA_9|R_33|R_37|SD_10|PL_12|PL_15)")),
    ("AA_SHORT", re.compile(r"(AIM_9|R_73|R_60|R_13|R_3S|APU_13|APU_60|Magic|ASRAAM|Python|IRIS|AA_11|AA_8|AA_2|PL_5|PL_8)")),
    ("PGM", re.compile(r"(GBU_|JDAM|KAB_|Paveway|BOLT|AGM_154|JSOW|AGM_130|SPICE|LGB|AASM|Kh_38|Kh_29|Kh_66|"
                        r"X_29|X_38|GB_)")),
    ("ASM", re.compile(r"(AGM_65|AGM_114|Kh_25ML|Kh_25M_|Vikhr|Ataka|AGM_12|Bullpup|AGM_123|Kh_23|Sidearm|X_25ML|X_23)")),
    ("GP", re.compile(r"(Mk_8[234]|MK_8[234]|M117|AN_M6|FAB_|OFAB|BetAB|RBK|BL_755|CBU|Rockeye|Durandal|"
                       r"BLU|BR_|SAMP|ZAB|KMGU|Mk_20|M_117|Belouga|Matra_F4|Type_)")),
    ("ROCKET", re.compile(r"(Hydra|Zuni|FFAR|UB_|B_8|B_13|S_24|S_25|S_5|S_8|SNEB|LAU_|LAU3|S_13|Rkts|UnGd|ORO|"
                           r"RS_82|ARAKM|Matra_|APU_68|Rocket)")),
]


def classify(name):
    """The category of a weapon by its pydcs attribute name, or None if it should never be loaded."""
    if EXCLUDE.search(name):
        return None
    for cat, rx in _CAT:
        if rx.search(name):
            return cat
    return None


# Preferred weapons per category, best first: (name pattern, year it entered service).
PREFS = {
    "AA_MED": [(r"AIM_120C", 1996), (r"AIM_120B", 1991), (r"R_77", 1994), (r"Meteor", 2016),
               (r"AIM_54C", 1986), (r"AIM_54A", 1974), (r"AIM_7P", 1987), (r"AIM_7MH", 1984), (r"AIM_7M", 1982),
               (r"R_27ER", 1983), (r"R_27R", 1983), (r"Super_530D", 1988),
               (r"AIM_7F", 1976), (r"Super_530F", 1979), (r"Skyflash", 1978), (r"R_24", 1975),
               (r"AIM_7E_2", 1969), (r"AIM_7E", 1963), (r"R_3R", 1962)],
    "AA_SHORT": [(r"AIM_9X", 2003), (r"ASRAAM", 2002), (r"R_73", 1985), (r"AIM_9M", 1983),
                 (r"R_60M", 1982), (r"AIM_9L", 1978), (r"AIM_9P5", 1978), (r"AIM_9P3", 1975),
                 (r"AIM_9P(_|$)", 1970), (r"Magic_2", 1986), (r"Magic", 1976), (r"R_60", 1974),
                 (r"AIM_9JULI|AIM_9J", 1972), (r"R_13M", 1966), (r"AIM_9E", 1967), (r"AIM_9B", 1956),
                 (r"R_3S", 1962)],
    "SEAD": [(r"AGM_88", 1985), (r"Kh_58", 1989), (r"Kh_31P", 1989), (r"Kh_25MP", 1975),
             (r"AGM_45B", 1966), (r"AGM_45A", 1966), (r"AGM_78", 1968), (r"Shrike", 1966)],
    "ASHM": [(r"AGM_84D", 1984), (r"Harpoon", 1977), (r"Kh_35", 2003), (r"Kh_31A", 1995),
             (r"Kh_22", 1962), (r"Kh_59", 1990), (r"Exocet|AM39", 1979), (r"Sea_Eagle", 1985)],
    "ASM": [(r"AGM_65K", 2002), (r"AGM_65G", 1989), (r"AGM_65D", 1983), (r"AGM_65B", 1980),
            (r"AGM_65A", 1972), (r"Vikhr", 1990), (r"Ataka", 1985), (r"Kh_25ML", 1975),
            (r"Kh_29", 1980), (r"AGM_12", 1959), (r"Bullpup", 1959)],
    "PGM": [(r"GBU_31|GBU_32|GBU_38|JDAM", 1999), (r"AGM_154", 1999), (r"GBU_24", 1988),
            (r"GBU_10", 1976), (r"GBU_16", 1976), (r"GBU_12", 1976), (r"KAB_1500", 1985),
            (r"KAB_500", 1980), (r"BOLT", 1968), (r"Kh_29", 1980)],
    "GP": [(r"^Mk_84(_|$)", 1950), (r"^Mk_83(_|$)", 1950), (r"^M117", 1950), (r"^AN_M65", 1950),
           (r"^Mk_82(_|$)", 1950), (r"^FAB_500", 1950), (r"^FAB_250", 1950), (r"^OFAB", 1950),
           (r"^BetAB", 1950), (r"BL_755", 1970), (r"^CBU", 1950), (r"Rockeye", 1968), (r"^Mk_20", 1968),
           (r"^FAB_", 1950), (r"^AN_M64", 1950)],
    "ROCKET": [(r"Hydra", 1960), (r"^S_8|B_8", 1971), (r"^S_5|UB_", 1955), (r"Zuni", 1957),
               (r"FFAR", 1950), (r"LAU", 1950)],
    "TANK": [(r"(?i)600|800|370|330|300|275|1150|1400", 1950)],
}
# A weapon no list above knows is only used from these years on (so an odd old or new store is not
# handed to the wrong era); categories not listed accept it in any year.
UNKNOWN_FROM = {"PGM": 1990, "ASM": 1985, "SEAD": 1985, "AA_MED": 1980, "AA_SHORT": 1975, "ASHM": 1985}
HEAVY = re.compile(r"(Mk_84|GBU_10|GBU_24|GBU_31|GBU_9|FAB_1500|KAB_1500|BetAB)")
HEAVY_LIMIT = 4

# Airfield attacks and general area targets prefer these over precision weapons.
GP_AREA = [(r"BetAB", 1950), (r"Durandal", 1970), (r"BL_755", 1970), (r"^CBU", 1950), (r"Rockeye", 1968),
           (r"^OFAB", 1950), (r"^FAB_250", 1950), (r"^Mk_82(_|$)", 1950), (r"^Mk_83(_|$)", 1950),
           (r"^FAB_500", 1950), (r"^Mk_84(_|$)", 1950)]

# What each job carries: (category, how many pylons, which pylons first, rule). "outer" fills from
# the wing tips inwards, "inner" from the middle outwards, "centre" the centreline first.
PROFILES = {
    "cap": [("TANK", 1, "centre", None), ("AA_SHORT", 2, "outer", None), ("AA_MED", 6, "inner", None),
            ("AA_SHORT", 2, "outer", None)],
    "strike": [("AA_SHORT", 2, "outer", None), ("TANK", 1, "centre", None), ("PGM", 4, "inner", None),
               ("GP", 6, "inner", "no:PGM"), ("ROCKET", 2, "inner", "no:PGM,GP")],
    "airfield": [("AA_SHORT", 2, "outer", None), ("TANK", 1, "centre", None), ("GP", 6, "inner", None),
                 ("ROCKET", 2, "inner", "no:GP")],
    "sead": [("AA_SHORT", 2, "outer", None), ("TANK", 1, "centre", None), ("SEAD", 4, "inner", None),
             ("AA_MED", 2, "inner", None), ("GP", 4, "inner", "no:SEAD")],
    "cas": [("AA_SHORT", 2, "outer", None), ("ASM", 4, "inner", None), ("ROCKET", 2, "inner", None),
            ("GP", 4, "inner", "no:ASM"), ("TANK", 1, "centre", None)],
    "antiship": [("AA_SHORT", 2, "outer", None), ("ASHM", 4, "inner", None), ("TANK", 1, "centre", None),
                 ("ASM", 2, "inner", "no:ASHM"), ("GP", 4, "inner", "no:ASHM,ASM")],
}
ROLE_PROFILE = {"cap": "cap", "intercept": "cap", "strike": "strike", "sead": "sead", "dead": "sead",
                "cas": "cas", "naval": "antiship", "airfield": "airfield"}


def _prefs_for(cat, profile):
    return GP_AREA if (cat == "GP" and profile == "airfield") else PREFS.get(cat, [])


def _pick(options, cat, year, profile):
    """The best allowed option of this category, or None. Older weapons are used when nothing newer
    is in service yet; an option no list knows about is allowed in any year."""
    prefs = _prefs_for(cat, profile)
    members = [o for o in options if classify(o) == cat]
    if not members:
        return None
    ranked = []
    for o in members:
        rank, born = len(prefs), UNKNOWN_FROM.get(cat, 0)
        for i, (pat, y) in enumerate(prefs):
            if re.search(pat, o):
                rank, born = i, y
                break
        ranked.append((rank, born, len(o), o))
    ok = [r for r in ranked if r[1] <= year]
    if not ok:
        return None
    # single stores before multiple racks of the same weapon: shorter names first as a tie-break
    ok.sort(key=lambda r: (r[0], r[2], r[3]))
    return ok[0][3]


def choose(pylons, role, year, max_aa=None):
    """{station number: option name} for one aircraft.

    `pylons` is {station: [option names]} (station keys may be ints or strings)."""
    profile = ROLE_PROFILE.get(role, role)
    if profile not in PROFILES:
        profile = "cap"
    st = {int(k): list(v) for k, v in pylons.items()}
    usable = sorted(k for k, v in st.items() if any(classify(o) for o in v))
    if not usable:
        return {}
    mid = (usable[0] + usable[-1]) / 2.0
    groups = {}
    for k in usable:
        groups.setdefault(abs(k - mid), []).append(k)
    counts = {}
    out = {}
    for cat, limit, order, rule in PROFILES[profile]:
        if rule and rule.startswith("no:"):
            if any(counts.get(c, 0) for c in rule[3:].split(",")):
                continue
        keys = sorted(groups, reverse=(order == "outer"))
        placed = counts.get(cat, 0)
        for d in keys:
            members = [k for k in sorted(groups[d]) if k not in out]
            if not members:
                continue
            # a symmetrical pair or nothing: do not leave one wing heavier than the other
            if placed + len(members) > limit:
                if placed + 1 > limit or len(members) == 1:
                    continue
                members = members[:max(0, limit - placed)] if limit - placed >= len(members) else []
                if not members:
                    continue
            free = [k for k in usable if k not in out]
            best = _pick(sorted({o for k in free for o in st[k]}), cat, year, profile)
            choices = {k: (best if best in st[k] else _pick(st[k], cat, year, profile)) for k in members}
            if any(v is None for v in choices.values()):
                continue
            if cat in ("PGM", "GP") and any(HEAVY.search(v) for v in choices.values()):
                heavy_now = sum(1 for v in out.values() if HEAVY.search(v))
                if heavy_now + len(members) > HEAVY_LIMIT:
                    continue                      # heavy bombs: four at most
            for k, v in choices.items():
                out[k] = v
            placed += len(members)
            counts[cat] = placed
            if placed >= limit:
                break
    if max_aa is not None:
        out = _limit_missiles(out, max_aa, mid)
    return dict(sorted(out.items()))


def _limit_missiles(out, max_aa, mid):
    """Keep at most `max_aa` air-to-air missiles: heat-seekers on the outer pylons first."""
    aa = [(k, v) for k, v in out.items() if classify(v) in ("AA_SHORT", "AA_MED")]
    if len(aa) <= max_aa:
        return out
    aa.sort(key=lambda kv: (classify(kv[1]) != "AA_SHORT", -abs(kv[0] - mid), kv[0]))
    drop = {k for k, _ in aa[max_aa:]}
    return {k: v for k, v in out.items() if k not in drop}


def for_aircraft(plane_class_name, role, year, max_aa=None, path=DATA):
    """choose() for a pydcs plane class name using the baked table ({} when it is not in the table)."""
    pylons = table(path).get(plane_class_name)
    return choose(pylons, role, year, max_aa) if pylons else {}


# ---- describing a loadout in words -----------------------------------------------------------

def pretty(name):
    """'AIM_120C_AMRAAM___Active_Radar_AAM' -> 'AIM-120C AMRAAM'."""
    s = name.split("___")[0]
    s = re.sub(r"_+", " ", s).strip()
    s = re.sub(r"(?<=[A-Za-z]) (?=\d)", "-", s)
    s = re.sub(r"(?<=\d) (?=[A-Z]\b)", "", s)
    return s[:44]


def describe(loadout):
    """['2 x AIM-9M Sidewinder IR AAM', ...] in a stable order; tanks come last."""
    counts, cats = {}, {}
    for name in loadout.values():
        label = pretty(name)
        counts[label] = counts.get(label, 0) + 1
        cats[label] = classify(name)
    items = sorted(counts.items(), key=lambda kv: (cats[kv[0]] == "TANK", kv[0]))
    return [f"{n} x {label}" for label, n in items]
