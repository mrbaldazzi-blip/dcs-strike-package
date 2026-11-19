"""Ships, and the enemy air raids used by the Intercept mission, by side and era.

Ship names are pydcs class names (checked by `check-units`). DCS has a limited fleet, so a few ships
appear slightly outside their real service dates; each era just uses the nearest plausible hulls.
"""

# (display, pydcs class, SAM or gun reach in nm)
CARGO = (("Dry cargo ship", "Dry_cargo_ship_1", 0.0), ("Dry cargo ship", "Dry_cargo_ship_2", 0.0),
         ("Fleet tanker", "ELNYA", 0.0))

WARSHIPS = {
    ("blue", "early_cold_war"): (("Essex-class carrier", "Essex", 5.0),),
    ("blue", "mid_cold_war"): (("Oliver Hazard Perry frigate", "PERRY", 22.0),),
    ("blue", "late_cold_war"): (("Oliver Hazard Perry frigate", "PERRY", 22.0),
                                ("Ticonderoga cruiser", "TICONDEROG", 60.0)),
    ("blue", "nineties"): (("Oliver Hazard Perry frigate", "PERRY", 22.0),
                           ("Ticonderoga cruiser", "TICONDEROG", 60.0)),
    ("blue", "modern"): (("Arleigh Burke destroyer", "USS_Arleigh_Burke_IIa", 80.0),
                         ("Ticonderoga cruiser", "TICONDEROG", 60.0)),
    ("red", "early_cold_war"): (("Albatros corvette", "ALBATROS", 6.0),),
    ("red", "mid_cold_war"): (("Rezky frigate", "REZKY", 8.0), ("Molniya missile boat", "MOLNIYA", 5.0)),
    ("red", "late_cold_war"): (("Moskva cruiser", "MOSCOW", 40.0), ("Rezky frigate", "REZKY", 8.0)),
    ("red", "nineties"): (("Moskva cruiser", "MOSCOW", 40.0), ("Neustrashimy frigate", "NEUSTRASH", 12.0)),
    ("red", "modern"): (("Neustrashimy frigate", "NEUSTRASH", 12.0), ("Piotr Velikiy cruiser", "PIOTR", 60.0)),
}

# the escorts that defend a target at sea, by era (a subset of the warships above)
ESCORTS = {key: tuple(v) for key, v in WARSHIPS.items()}
ESCORTS[("blue", "early_cold_war")] = (("Oliver Hazard Perry frigate", "PERRY", 22.0),)

CARRIERS = {
    ("blue", "early_cold_war"): (("Essex-class carrier", "Essex", 5.0),),
    ("blue", "mid_cold_war"): (("USS Forrestal", "Forrestal", 5.0),),
    ("blue", "late_cold_war"): (("USS Forrestal", "Forrestal", 5.0),),
    ("blue", "nineties"): (("USS John C. Stennis", "Stennis", 5.0),),
    ("blue", "modern"): (("USS John C. Stennis", "Stennis", 5.0),),
    ("red", "nineties"): (("Admiral Kuznetsov", "KUZNECOW", 8.0),),
    ("red", "modern"): (("Admiral Kuznetsov", "KUZNECOW", 8.0),),
}

# Intercept: the aircraft in the enemy raid. (display, pydcs class)
RAIDERS = {
    ("blue", "early_cold_war"): (("F-86F Sabre", "F_86F_Sabre"),),
    ("blue", "mid_cold_war"): (("F-4E Phantom II", "F_4E_45MC"),),
    ("blue", "late_cold_war"): (("F-4E Phantom II", "F_4E_45MC"), ("F-16C Fighting Falcon", "F_16C_50")),
    ("blue", "nineties"): (("F-16C Fighting Falcon", "F_16C_50"), ("F/A-18C Hornet", "FA_18C_hornet")),
    ("blue", "modern"): (("F-15E Strike Eagle", "F_15E"), ("F-16C Fighting Falcon", "F_16C_50")),
    ("red", "early_cold_war"): (("MiG-15bis", "MiG_15bis"),),
    ("red", "mid_cold_war"): (("Su-17M4 Fitter", "Su_17M4"), ("MiG-21bis", "MiG_21Bis")),
    ("red", "late_cold_war"): (("Su-24M Fencer", "Su_24M"), ("Su-25 Frogfoot", "Su_25")),
    ("red", "nineties"): (("Su-24M Fencer", "Su_24M"), ("Su-25T Frogfoot", "Su_25T")),
    ("red", "modern"): (("Su-34 Fullback", "Su_34"), ("Su-24M Fencer", "Su_24M")),
}
RAID_SPEED_KTS = {"early_cold_war": 340, "mid_cold_war": 400, "late_cold_war": 420,
                  "nineties": 430, "modern": 440}
RAID_ALT_FT = {"early_cold_war": 15000, "mid_cold_war": 8000, "late_cold_war": 6000,
               "nineties": 15000, "modern": 20000}


def pick_target(rng, side, era_key):
    """(kind, display, class, reach_nm) for the ship being attacked."""
    carriers = CARRIERS.get((side, era_key), ())
    warships = WARSHIPS.get((side, era_key), ())
    roll = rng.random()
    if carriers and roll < 0.2:
        kind, pool = "carrier", carriers
    elif warships and roll < 0.6:
        kind, pool = "warship", warships
    else:
        kind, pool = "cargo", CARGO
    d, c, r = rng.choice(pool)
    return kind, d, c, r


def escort_count(rng, defences):
    return {"light": 0, "medium": rng.choice([1, 2]), "heavy": rng.randint(4, 6)}[defences]
