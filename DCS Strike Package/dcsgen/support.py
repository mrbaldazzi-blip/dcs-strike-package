"""AWACS and tanker choices, by side, date and the aircraft that needs fuel."""

from .catalog import refuel_method

NAMES = {
    ("blue", "awacs"): ["Overlord", "Magic", "Focus"],
    ("red", "awacs"): ["Rook", "Moscow Control", "Sentinel"],
    ("blue", "tanker"): ["Texaco", "Shell", "Arco"],
    ("red", "tanker"): ["Baton", "Bear", "Anchor"],
}

METHOD_TEXT = {"boom": "flying boom", "drogue": "probe and drogue",
               "both": "flying boom and probe-and-drogue"}


def pick_awacs(side, year, carrier):
    """(display, pydcs name, altitude ft, speed kts) or None if none existed then."""
    if side == "blue":
        if carrier and year >= 1973:
            return "E-2C Hawkeye", "E_2C", 25000, 280
        if year >= 1977:
            return "E-3A Sentry", "E_3A", 30000, 400
        return None
    if year >= 1984:
        return "A-50 Mainstay", "A_50", 30000, 400
    return None


def pick_tanker(side, year, era_key, aircraft_key):
    """(display, pydcs name, altitude ft, speed kts, method) for this aircraft, or (None, reason)."""
    need = refuel_method(aircraft_key)
    if not need:
        return None, "cannot take fuel in flight"
    if side == "blue":
        if need == "boom":
            return ("KC-135 Stratotanker", "KC_135", 24000, 420, "boom"), ""
        if year >= 1991:
            return ("KC-135 MPRS", "KC135MPRS", 22000, 400, "both"), ""
        return ("KC-130 Hercules", "KC130", 14000, 260, "drogue"), ""
    if year >= 1987 and need == "drogue":
        return ("Il-78M Midas", "IL_78M", 20000, 380, "drogue"), ""
    return None, "has no tanker in service for that date"
