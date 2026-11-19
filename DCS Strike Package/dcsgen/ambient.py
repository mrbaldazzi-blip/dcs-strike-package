"""Airbase atmosphere: trucks, AA guns, parked aircraft and helicopter traffic.

Everything here is dressing. It is planned with its own random stream so that adding or
changing it never moves the rest of a mission's layout, and it is not part of the unit budget
(a handful of units, none of them armed to matter).
"""

import random

from .models import Ambient

# class names are resolved against pydcs by the builder; the first one found is used
_TRUCKS = {"blue": ("M_818", "Hummer"), "red": ("Ural_375", "GAZ_66")}
_FUEL = {"blue": ("M978_HEMTT_Tanker", "M_818"), "red": ("ATZ_5", "Ural_375")}
_EARLY_AAA = {"blue": ("Bofors40", "M45_Quadmount"), "red": ("ZU_23_Emplacement", "KS_19")}

_TRANSPORT = {
    "blue": {"early_cold_war": ("UH_1H",), "mid_cold_war": ("UH_1H",),
             "late_cold_war": ("UH_60A", "UH_1H"), "nineties": ("UH_60A", "UH_1H"),
             "modern": ("UH_60A", "CH_47F", "UH_1H")},
    "red": {"early_cold_war": ("Mi_8MT",), "mid_cold_war": ("Mi_8MT",),
            "late_cold_war": ("Mi_8MT",), "nineties": ("Mi_8MT",),
            "modern": ("Mi_8MT", "Mi_26")},
}
_ATTACK = {
    "blue": {"early_cold_war": ("UH_1H",), "mid_cold_war": ("UH_1H",),
             "late_cold_war": ("OH_58D", "UH_1H"), "nineties": ("AH_64A", "OH_58D", "UH_1H"),
             "modern": ("AH_64D", "AH_64A", "OH_58D", "UH_1H")},
    "red": {"early_cold_war": ("Mi_8MT",), "mid_cold_war": ("Mi_24V", "Mi_8MT"),
            "late_cold_war": ("Mi_24V", "Mi_8MT"), "nineties": ("Mi_24V", "Mi_8MT"),
            "modern": ("Mi_28N", "Ka_50", "Mi_24V", "Mi_8MT")},
}


def plan_ambient(req, era, side, active, carrier_start, key_seed):
    """Return a list of Ambient entries for the player's side."""
    if carrier_start:
        return []                       # a carrier deck is crowded enough; no airfield to dress
    rng = random.Random(f"ambient|{key_seed}|{era.key}|{side}")
    fac = era.faction(side)
    out = []

    # AA guns: the era's own gun systems, two or three positions round the field
    for i in range(rng.randint(2, 3)):
        if fac.aaa:
            disp, cls, n = rng.choice(fac.aaa)
            cands = (cls,)
        else:
            disp, cands, n = "AA gun", _EARLY_AAA[side], 2
        out.append(Ambient(f"Airfield AAA {i + 1} - {disp}", side, "aaa", cands, max(1, min(n, 3)),
                           heading_deg=rng.uniform(0, 360)))

    # trucks and a fuel bowser
    for i in range(rng.randint(2, 3)):
        out.append(Ambient(f"Airfield trucks {i + 1}", side, "vehicle", _TRUCKS[side],
                           rng.randint(1, 3), heading_deg=rng.uniform(0, 360)))
    out.append(Ambient("Airfield fuel truck", side, "vehicle", _FUEL[side], 1,
                       heading_deg=rng.uniform(0, 360)))

    # parked aircraft (uncontrolled, cold): the era's fighters and a transport helicopter
    fighters = [c for _d, c in fac.fighters]
    for i in range(rng.randint(2, 4) if fighters else 0):
        out.append(Ambient(f"Parked aircraft {i + 1}", side, "parked", (rng.choice(fighters),), 1))
    for i in range(rng.randint(1, 2)):
        out.append(Ambient(f"Parked helicopter {i + 1}", side, "parked",
                           _TRANSPORT[side][era.key], 1))

    # helicopters coming and going: only where there is a war on
    if active and rng.random() < 0.85:
        for i in range(rng.randint(1, 3)):
            role = rng.choice(["resupply", "resupply", "cas", "arrival"])
            table = _ATTACK if role == "cas" else _TRANSPORT
            out.append(Ambient(f"Heli traffic {i + 1}", side, "heli", table[side][era.key],
                               rng.choice([1, 1, 2]) if role == "cas" else 1, role=role,
                               start_min=rng.randint(1, 18)))
    return out
