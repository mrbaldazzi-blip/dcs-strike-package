"""Era and faction definitions: what is plausible for each side in each period.

Every DCS unit type is a *string* naming the pydcs class, so nothing here needs
pydcs installed. Names marked "verified" were confirmed against pydcs 1.0.0 by the
user's check-units report; the rest follow pydcs's naming pattern (DCS type id with
spaces and hyphens turned into underscores) and are tried through the alias
resolver in unitnames.py. Run `python -m dcsgen check-units` to see any that fail.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SamSite:
    display: str
    components: tuple          # ((pydcs_vehicle_class, count), ...), core radar/launcher first
    lethal_range_nm: float
    radar_guided: bool = True


@dataclass(frozen=True)
class CarrierSpec:
    key: str
    display: str
    pydcs_name: str
    needs_mod: bool = False    # True for the Supercarrier module


@dataclass(frozen=True)
class Faction:
    side: str                  # "blue" or "red"
    country: str               # pydcs country class name
    adjective: str             # "American", "Soviet", "Russian"
    sam_sites: tuple = ()
    aaa: tuple = ()            # (display, pydcs_vehicle_class, count)
    ewr: str = ""              # early-warning radar vehicle class, empty if none
    fighters: tuple = ()       # interceptors: (display, pydcs_plane_class)
    soft_targets: tuple = ()   # strike targets: (display, class, count)
    forces: tuple = ()  # armour and mech: (display, class, count)
    carriers: tuple = ()


@dataclass(frozen=True)
class Era:
    key: str
    label: str
    years: tuple
    ingress_alt_ft: int
    ingress_speed_kts: int
    blue: Faction
    red: Faction
    roe: str = "Weapons free on hostile forces. Avoid collateral damage."
    nav_note: str = "Navigation is by map, stopwatch and compass."
    comms_note: str = "Voice comms on the assigned radio frequencies."

    def faction(self, side: str) -> Faction:
        return self.blue if side == "blue" else self.red


def opposite(side: str) -> str:
    return "red" if side == "blue" else "blue"


# ---- red (Soviet / Russian) SAM sites ---------------------------------------
SA2 = SamSite("SA-2 Guideline",
              (("SNR_75V", 1), ("S_75M_Volhov", 3), ("p_19_s_125_sr", 1)), 25.0)
SA3 = SamSite("SA-3 Goa",
              (("snr_s_125_tr", 1), ("X_5p73_s_125_ln", 2), ("p_19_s_125_sr", 1)), 12.0)
SA6 = SamSite("SA-6 Gainful",
              (("Kub_1S91_str", 1), ("Kub_2P25_ln", 3)), 13.0)
SA8 = SamSite("SA-8 Gecko", (("Osa_9A33_ln", 1),), 7.0)
SA10 = SamSite("SA-10 Grumble",
               (("S_300PS_5H63C_30H6_tr", 1), ("S_300PS_5P85C_ln", 4), ("S_300PS_40B6MD_sr", 1)), 60.0)
SA11 = SamSite("SA-11 Gadfly",
               (("SA_11_Buk_CC_9S470M1", 1), ("SA_11_Buk_LN_9A310M1", 3), ("SA_11_Buk_SR_9S18M1", 1)), 18.0)
SA15 = SamSite("SA-15 Gauntlet", (("Tor_9A331", 2),), 8.0)

# ---- blue (NATO) SAM sites --------------------------------------------------
HAWK = SamSite("MIM-23 Hawk",
               (("Hawk_tr", 1), ("Hawk_ln", 3), ("Hawk_sr", 1)), 22.0)
RAPIER = SamSite("Rapier",
                 (("rapier_fsa_blindfire_radar", 1), ("rapier_fsa_launcher", 2)), 4.0)
ROLAND = SamSite("Roland",
                 (("Roland_Radar", 1), ("Roland_ADS", 2)), 4.0)
PATRIOT = SamSite("MIM-104 Patriot",
                  (("Patriot_str", 1), ("Patriot_ln", 3), ("Patriot_cp", 1)), 55.0)
NASAMS = SamSite("NASAMS",
                 (("NASAMS_Radar_MPQ64F1", 1), ("NASAMS_LN_B", 2), ("NASAMS_Command_Post", 1)), 14.0)

# ---- carriers ---------------------------------------------------------------
FORRESTAL = CarrierSpec("forrestal", "USS Forrestal (CV-59)", "Forrestal")
STENNIS = CarrierSpec("stennis", "USS John C. Stennis (CVN-74)", "Stennis")
CVN71 = CarrierSpec("cvn71", "USS Theodore Roosevelt (CVN-71)", "CVN_71", needs_mod=True)
CVN72 = CarrierSpec("cvn72", "USS Abraham Lincoln (CVN-72)", "CVN_72", needs_mod=True)
CVN73 = CarrierSpec("cvn73", "USS George Washington (CVN-73)", "CVN_73", needs_mod=True)
CVN75 = CarrierSpec("cvn75", "USS Harry S. Truman (CVN-75)", "CVN_75", needs_mod=True)
KUZNETSOV = CarrierSpec("kuznetsov", "Admiral Kuznetsov", "KUZNECOW")

# ---- shared pieces ----------------------------------------------------------
_SHILKA = ("ZSU-23-4 Shilka", "ZSU_23_4_Shilka", 2)
_ZU23 = ("ZU-23 AAA", "ZU_23_Emplacement_Closed", 3)
_VULCAN = ("M163 Vulcan", "Vulcan", 2)
_GEPARD = ("Gepard", "Gepard", 2)
_AVENGER = ("M1097 Avenger", "M1097_Avenger", 2)
_TUNGUSKA = ("Tunguska 2S6", "X_2S6_Tunguska", 2)

_BLUE_SOFT = (("Supply convoy", "M_818", 6), ("Fuel convoy", "M978_HEMTT_Tanker", 5))
_BLUE_SOFT_LATE = (("Ammunition convoy", "M_818", 6), ("Command post", "M_818", 4))
_RED_SOFT_EARLY = (("Supply convoy", "Ural_375", 6), ("Fuel convoy", "GAZ_66", 5))
_RED_SOFT = (("Command post", "Ural_375", 4), ("Fuel depot", "Ural_375", 5))
_RED_SOFT_MID = (("Fuel depot", "Ural_375", 5), ("Supply convoy", "Ural_375", 6))
_RED_SOFT_LATE = (("Command post", "Ural_375", 4), ("Ammunition convoy", "Ural_375", 6))

ERAS = {
    "early_cold_war": Era(
        key="early_cold_war", label="Early Cold War (1950s-60s)", years=(1955, 1967),
        ingress_alt_ft=12000, ingress_speed_kts=360,
        blue=Faction(
            "blue", "USA", "American",
            sam_sites=(HAWK,), aaa=(), ewr="",
            fighters=(("F-86F Sabre", "F_86F_Sabre"),),
            soft_targets=_BLUE_SOFT,
            forces=(("M60 platoon", "M_60", 4), ("M113 group", "M_113", 6)),
            carriers=(FORRESTAL,)),
        red=Faction(
            "red", "USSR", "Soviet",
            sam_sites=(SA2,), aaa=(_ZU23,), ewr="",
            fighters=(("MiG-15bis", "MiG_15bis"),),
            soft_targets=_RED_SOFT_EARLY,
            forces=(("T-55 armoured group", "T_55", 5), ("T-55 platoon", "T_55", 4)),
            carriers=()),
        nav_note="No navigation aids beyond compass, map and stopwatch.",
        comms_note="Basic UHF only. Keep calls short.",
    ),
    "mid_cold_war": Era(
        key="mid_cold_war", label="Mid Cold War (1970s)", years=(1970, 1979),
        ingress_alt_ft=500, ingress_speed_kts=480,
        blue=Faction(
            "blue", "USA", "American",
            sam_sites=(HAWK, RAPIER, ROLAND), aaa=(_VULCAN,), ewr="",
            fighters=(("F-4E Phantom II", "F_4E_45MC"), ("F-5E Tiger II", "F_5E_3")),
            soft_targets=_BLUE_SOFT,
            forces=(("M60 platoon", "M_60", 4), ("M113 group", "M_113", 6)),
            carriers=(FORRESTAL,)),
        red=Faction(
            "red", "USSR", "Soviet",
            sam_sites=(SA2, SA3, SA6), aaa=(_SHILKA,), ewr="X_1L13_EWR",
            fighters=(("MiG-21bis", "MiG_21Bis"),),
            soft_targets=_RED_SOFT_MID,
            forces=(("T-55 armoured group", "T_55", 5), ("BMP-1 mechanised group", "BMP_1", 6)),
            carriers=()),
        nav_note="Dead reckoning and TACAN where available.",
    ),
    "late_cold_war": Era(
        key="late_cold_war", label="Late Cold War (1980s)", years=(1982, 1989),
        ingress_alt_ft=300, ingress_speed_kts=500,
        blue=Faction(
            "blue", "USA", "American",
            sam_sites=(HAWK, ROLAND, PATRIOT), aaa=(_VULCAN, _GEPARD), ewr="FPS_117",
            fighters=(("F-14A Tomcat", "F_14A_135_GR"), ("F-15C Eagle", "F_15C"),
                      ("F-16C Fighting Falcon", "F_16C_50")),
            soft_targets=_BLUE_SOFT_LATE,
            forces=(("M1 Abrams platoon", "M_1_Abrams", 4), ("Bradley group", "M_2_Bradley", 5)),
            carriers=(FORRESTAL, CVN71, CVN72)),
        red=Faction(
            "red", "USSR", "Soviet",
            sam_sites=(SA3, SA6, SA8), aaa=(_SHILKA,), ewr="X_1L13_EWR",
            fighters=(("MiG-23MLD", "MiG_23MLD"), ("MiG-29A", "MiG_29A")),
            soft_targets=_RED_SOFT_LATE,
            forces=(("T-72 armoured group", "T_72B", 5), ("BMP-2 mechanised group", "BMP_2", 6)),
            carriers=()),
        nav_note="Inertial navigation plus TACAN. GPS is not available.",
    ),
    "nineties": Era(
        key="nineties", label="The 1990s", years=(1991, 1999),
        ingress_alt_ft=20000, ingress_speed_kts=450,
        blue=Faction(
            "blue", "USA", "American",
            sam_sites=(HAWK, PATRIOT), aaa=(_VULCAN, _AVENGER), ewr="FPS_117",
            fighters=(("F-15C Eagle", "F_15C"), ("F/A-18C Hornet", "FA_18C_hornet"),
                      ("F-14B Tomcat", "F_14B")),
            soft_targets=_BLUE_SOFT_LATE,
            forces=(("M1 Abrams platoon", "M_1_Abrams", 4), ("Bradley group", "M_2_Bradley", 5)),
            carriers=(FORRESTAL, STENNIS, CVN71, CVN72, CVN73)),
        red=Faction(
            "red", "Russia", "Russian",
            sam_sites=(SA6, SA8, SA11, SA10), aaa=(_SHILKA,), ewr="X_55G6_EWR",
            fighters=(("MiG-29S", "MiG_29S"), ("Su-27", "Su_27")),
            soft_targets=_RED_SOFT,
            forces=(("T-72 armoured group", "T_72B", 5), ("BMP-2 mechanised group", "BMP_2", 6)),
            carriers=(KUZNETSOV,)),
        nav_note="INS and GPS available. Precision weapons are authorised.",
    ),
    "modern": Era(
        key="modern", label="Modern (2010s-present)", years=(2012, 2024),
        ingress_alt_ft=25000, ingress_speed_kts=450,
        blue=Faction(
            "blue", "USA", "American",
            sam_sites=(PATRIOT, NASAMS), aaa=(_AVENGER,), ewr="FPS_117",
            fighters=(("F-15C Eagle", "F_15C"), ("F-16C Fighting Falcon", "F_16C_50"),
                      ("F/A-18C Hornet", "FA_18C_hornet")),
            soft_targets=(("Command and control node", "M_818", 4), ("Fuel depot", "M978_HEMTT_Tanker", 5)),
            forces=(("M1 Abrams platoon", "M_1_Abrams", 4), ("Bradley group", "M_2_Bradley", 5)),
            carriers=(STENNIS, CVN71, CVN72, CVN73, CVN75)),
        red=Faction(
            "red", "Russia", "Russian",
            sam_sites=(SA10, SA11, SA15), aaa=(_TUNGUSKA,), ewr="X_55G6_EWR",
            fighters=(("Su-27", "Su_27"), ("MiG-29S", "MiG_29S")),
            soft_targets=(("Command and control node", "Ural_375", 4), ("Fuel depot", "Ural_375", 5)),
            forces=(("T-90 armoured group", "T_90", 5), ("BMP-3 mechanised group", "BMP_3", 6)),
            carriers=(KUZNETSOV,)),
        nav_note="Full GPS, datalink and JDAM employment available.",
    ),
}


def get_era(key: str) -> Era:
    try:
        return ERAS[key]
    except KeyError:
        raise ValueError(f"Unknown era '{key}'. Choose from: {', '.join(ERAS)}")
