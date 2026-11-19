"""Aircraft the player can fly (and the AI flies in the supporting flights).

`side` is the coalition the aircraft belongs to, `eras` where it is historically plausible,
`years` its service window (used to pick a believable mission date), and `roles` the mission
types it can sensibly perform. `kind` is where it comes from:

  module  a DCS module (including early-access ones)
  fc3     Flaming Cliffs 3 (the nine FC3 aircraft)
  mod     a community mod; it only works if you have installed it

`pydcs` is the python class name in pydcs. If your pydcs does not know an aircraft (brand-new
modules and community mods often are not), the builder creates a stand-in class from `standin`
that carries the real DCS type id `dcs_type`, so the mission still saves. For mods, mods.py
looks in your Saved Games\\DCS\\Mods folder (using `search`) for the id the mod really declares.
`service` picks the briefing header (see render.SERVICES).
"""

from dataclasses import dataclass

from .models import MissionType as M

E, MID, LATE, N90, MOD = "early_cold_war", "mid_cold_war", "late_cold_war", "nineties", "modern"
ERA_ORDER = (E, MID, LATE, N90, MOD)
ALL_ROLES = frozenset(M)
A2G = frozenset({M.CAS, M.STRIKE})
CAP_ONLY = frozenset({M.CAP})


@dataclass(frozen=True)
class AircraftSpec:
    key: str
    display: str
    pydcs: str
    side: str
    years: tuple
    eras: tuple
    roles: frozenset
    service: str = "USAF"
    carrier: bool = False
    kind: str = "module"
    note: str = ""
    dcs_type: str = ""        # DCS type id; the stand-in class carries it, mods match against it
    standin: str = ""         # python name of a stock pydcs aircraft to copy if pydcs lacks this one
    search: tuple = ()        # lower-case words that identify the mod's folder or type id

    @property
    def mod(self):
        return self.kind == "mod"

    @property
    def label(self):
        tags = []
        if self.kind == "fc3":
            tags.append("FC3")
        elif self.kind == "mod":
            tags.append("mod")
        if self.note:
            tags.append(self.note)
        return self.display + (f" [{', '.join(tags)}]" if tags else "")


AIRCRAFT = {a.key: a for a in [
    # ---- blue -----------------------------------------------------------------
    AircraftSpec("f86f", "F-86F Sabre", "F_86F_Sabre", "blue", (1950, 1970), (E,),
                 frozenset({M.CAS, M.STRIKE, M.CAP})),
    AircraftSpec("f86f_fc", "F-86F Sabre", "F_86F_FC", "blue", (1950, 1970), (E,),
                 frozenset({M.CAS, M.STRIKE, M.CAP}), note="FC"),
    AircraftSpec("f100d", "F-100D Super Sabre", "F_100D", "blue", (1956, 1979), (E, MID),
                 frozenset({M.CAP, M.CAS, M.STRIKE}), note="early access", dcs_type="F-100D", standin="F_86F_Sabre"),
    AircraftSpec("a4e", "A-4E-C Skyhawk", "A_4E_C", "blue", (1962, 1979), (E, MID), A2G,
                 service="USN", carrier=True, kind="mod", dcs_type="A-4E-C",
                 standin="F_86F_Sabre", search=("a-4e", "a4e", "skyhawk")),
    AircraftSpec("ov10a", "OV-10A Bronco", "Bronco_OV_10A", "blue", (1965, 1979), (E, MID), A2G,
                 kind="mod", dcs_type="Bronco-OV-10A", standin="F_86F_Sabre",
                 search=("ov-10", "ov10", "bronco")),
    AircraftSpec("f5e", "F-5E-3 Tiger II", "F_5E_3", "blue", (1972, 1995), (MID, LATE),
                 frozenset({M.CAP, M.CAS, M.STRIKE})),
    AircraftSpec("f5e_fc", "F-5E-3 Tiger II", "F_5E_3_FC", "blue", (1972, 1995), (MID, LATE),
                 frozenset({M.CAP, M.CAS, M.STRIKE}), note="FC"),
    AircraftSpec("f4e", "F-4E Phantom II", "F_4E_45MC", "blue", (1967, 1990), (MID, LATE), ALL_ROLES),
    AircraftSpec("a10a", "A-10A Thunderbolt II", "A_10A", "blue", (1977, 1999), (MID, LATE, N90),
                 A2G, kind="fc3"),
    AircraftSpec("f14a", "F-14A Tomcat", "F_14A_135_GR", "blue", (1974, 2006), (MID, LATE, N90),
                 CAP_ONLY, service="USN", carrier=True),
    AircraftSpec("f14b", "F-14B Tomcat", "F_14B", "blue", (1987, 2006), (LATE, N90),
                 frozenset({M.CAP, M.STRIKE}), service="USN", carrier=True),
    AircraftSpec("fa18c", "F/A-18C Hornet", "FA_18C_hornet", "blue", (1983, 2030), (LATE, N90, MOD),
                 ALL_ROLES, service="USN", carrier=True),
    AircraftSpec("f16c", "F-16C Fighting Falcon", "F_16C_50", "blue", (1984, 2030),
                 (LATE, N90, MOD), ALL_ROLES),
    AircraftSpec("f15c", "F-15C Eagle", "F_15C", "blue", (1979, 2030), (LATE, N90, MOD),
                 CAP_ONLY, kind="fc3"),
    AircraftSpec("f15e", "F-15E Strike Eagle", "F_15E", "blue", (1988, 2030), (LATE, N90, MOD),
                 frozenset({M.STRIKE, M.CAS, M.SEAD, M.DEAD})),
    AircraftSpec("av8b", "AV-8B Harrier II", "AV8BNA", "blue", (1985, 2030), (LATE, N90, MOD), A2G,
                 service="USMC", carrier=True),
    AircraftSpec("a10c", "A-10C Thunderbolt II", "A_10C", "blue", (2005, 2030), (MOD,),
                 A2G | {M.DEAD}),
    AircraftSpec("a10c2", "A-10C II Thunderbolt II", "A_10C_2", "blue", (2010, 2030), (MOD,),
                 A2G | {M.DEAD}),
    # ---- red ------------------------------------------------------------------
    AircraftSpec("mig15bis", "MiG-15bis", "MiG_15bis", "red", (1950, 1970), (E,),
                 frozenset({M.CAP, M.CAS, M.STRIKE}), service="VVS"),
    AircraftSpec("mig15bis_fc", "MiG-15bis", "MiG_15bis_FC", "red", (1950, 1970), (E,),
                 frozenset({M.CAP, M.CAS, M.STRIKE}), service="VVS", note="FC"),
    AircraftSpec("mig21bis", "MiG-21bis", "MiG_21Bis", "red", (1972, 1995), (E, MID, LATE),
                 frozenset({M.CAP, M.CAS, M.STRIKE}), service="VVS"),
    AircraftSpec("su25", "Su-25 Frogfoot", "Su_25", "red", (1981, 2030), (LATE, N90),
                 frozenset({M.CAS, M.STRIKE, M.SEAD, M.DEAD}), service="VVS", kind="fc3"),
    AircraftSpec("su25t", "Su-25T Frogfoot", "Su_25T", "red", (1990, 2030), (N90, MOD),
                 frozenset({M.CAS, M.STRIKE, M.SEAD, M.DEAD}), service="VVS", kind="fc3"),
    AircraftSpec("mig29a", "MiG-29A Fulcrum", "MiG_29A", "red", (1983, 2000), (LATE, N90),
                 frozenset({M.CAP, M.CAS, M.STRIKE}), service="VVS", kind="fc3"),
    AircraftSpec("mig29s", "MiG-29S Fulcrum", "MiG_29S", "red", (1990, 2030), (N90, MOD),
                 frozenset({M.CAP, M.CAS, M.STRIKE}), service="VVS", kind="fc3"),
    AircraftSpec("su27", "Su-27 Flanker", "Su_27", "red", (1985, 2030), (LATE, N90, MOD),
                 frozenset({M.CAP, M.CAS, M.STRIKE}), service="VVS", kind="fc3"),
    AircraftSpec("su33", "Su-33 Flanker-D", "Su_33", "red", (1995, 2030), (N90, MOD),
                 frozenset({M.CAP, M.STRIKE}), service="VVS", carrier=True, kind="fc3"),
    AircraftSpec("j11a", "J-11A", "J_11A", "red", (2000, 2030), (MOD,),
                 frozenset({M.CAP, M.CAS, M.STRIKE}),
                 service="PLAAF", kind="fc3"),
    AircraftSpec("mig19p", "MiG-19P Farmer", "MiG_19P", "red", (1955, 1975), (E, MID),
                 frozenset({M.CAP, M.CAS, M.STRIKE}), service="VVS", dcs_type="MiG-19P",
                 note="early access"),
    AircraftSpec("l39c", "L-39C Albatros", "L_39C", "red", (1974, 2030), (MID, LATE, N90, MOD),
                 frozenset({M.CAS, M.STRIKE}), service="VVS", dcs_type="L-39C"),
    AircraftSpec("l39za", "L-39ZA Albatros", "L_39ZA", "red", (1974, 2030), (MID, LATE, N90, MOD),
                 frozenset({M.CAS, M.STRIKE}), service="VVS", dcs_type="L-39ZA"),
    AircraftSpec("jf17", "JF-17 Thunder", "JF_17", "red", (2010, 2030), (MOD,),
                 frozenset({M.CAP, M.CAS, M.STRIKE, M.SEAD}), service="PLAAF", dcs_type="JF-17"),
    # community mods: pydcs knows the class, DCS needs the mod installed
    AircraftSpec("mig23mld", "MiG-23MLD Flogger", "MiG_23MLD", "red", (1976, 1995), (MID, LATE),
                 frozenset({M.CAP, M.CAS, M.STRIKE}), service="VVS", kind="mod",
                 dcs_type="MiG-23MLD", standin="MiG_21Bis", search=("mig-23", "mig23")),
    AircraftSpec("mig25pd", "MiG-25PD Foxbat", "MiG_25PD", "red", (1978, 1995), (MID, LATE),
                 CAP_ONLY, service="VVS", kind="mod", dcs_type="MiG-25PD",
                 standin="MiG_21Bis", search=("mig-25", "mig25")),
    AircraftSpec("mig27k", "MiG-27K Flogger-J", "MiG_27K", "red", (1975, 1995), (MID, LATE),
                 A2G, service="VVS", kind="mod", dcs_type="MiG-27K",
                 standin="MiG_21Bis", search=("mig-27", "mig27")),
    AircraftSpec("su17m4", "Su-17M4 Fitter-K", "Su_17M4", "red", (1981, 1998), (MID, LATE, N90),
                 A2G, service="VVS", kind="mod", dcs_type="Su-17M4",
                 standin="MiG_21Bis", search=("su-17", "su17")),
    AircraftSpec("su24m", "Su-24M Fencer-D", "Su_24M", "red", (1986, 2030), (LATE, N90, MOD),
                 frozenset({M.STRIKE, M.CAS}), service="VVS", kind="mod", dcs_type="Su-24M",
                 standin="MiG_21Bis", search=("su-24", "su24")),
    AircraftSpec("su30", "Su-30 Flanker-C", "Su_30", "red", (1996, 2030), (N90, MOD),
                 frozenset({M.CAP, M.CAS, M.STRIKE}), service="VVS", kind="mod",
                 dcs_type="Su-30", standin="MiG_21Bis", search=("su-30", "su30")),
    AircraftSpec("su34", "Su-34 Fullback", "Su_34", "red", (2014, 2030), (MOD,),
                 frozenset({M.STRIKE, M.CAS, M.SEAD}), service="VVS", kind="mod",
                 dcs_type="Su-34", standin="MiG_21Bis", search=("su-34", "su34")),
    AircraftSpec("mig31", "MiG-31 Foxhound", "MiG_31", "red", (1983, 2030), (LATE, N90, MOD),
                 CAP_ONLY, service="VVS", kind="mod", dcs_type="MiG-31",
                 standin="MiG_21Bis", search=("mig-31", "mig31")),
]}

FC3_KEYS = ("a10a", "f15c", "su25", "su25t", "mig29a", "mig29s", "su27", "su33", "j11a")


# Missions that borrow another mission's aircraft requirement.
ROLE_NEED = {M.INTERCEPT: M.CAP, M.NAVAL: M.STRIKE}


def can_fly(spec, role):
    """True if the aircraft can fly this mission type (intercepts need a fighter, naval strikes a striker)."""
    return ROLE_NEED.get(role, role) in spec.roles


def flies_in(spec, era_key):
    """True if the aircraft suits this era: its own eras, plus the one era after each
    (a jet is usually still around a generation after it arrived)."""
    if era_key not in ERA_ORDER:
        return era_key in spec.eras
    i = ERA_ORDER.index(era_key)
    return era_key in spec.eras or (i > 0 and ERA_ORDER[i - 1] in spec.eras)


_OWNED = None        # None = offer everything; otherwise the set of aircraft keys the user owns


def set_owned(keys):
    """Limit what available_aircraft offers to these keys (and any mods). None removes the limit."""
    global _OWNED
    _OWNED = None if keys is None else set(keys)


def owned_filter():
    return _OWNED


def available_aircraft(era_key, role=None, side=None, carrier=False, include_mods=True,
                       any_era=False, strict=False):
    """Aircraft for an era. any_era=True ignores the era (the 'all aircraft' option).

    When an ownership filter is set, only owned aircraft are returned. If that would leave
    nothing, the unfiltered list is returned so the form never ends up empty."""
    out = [a for a in AIRCRAFT.values()
           if (any_era or (era_key in a.eras if strict else flies_in(a, era_key)))
           and (role is None or can_fly(a, role))
           and (side is None or a.side == side)
           and (not carrier or a.carrier)
           and (include_mods or not a.mod)]
    if _OWNED is not None:
        mine = [a for a in out if a.mod or a.key in _OWNED]
        if mine:
            out = mine
    return sorted(out, key=lambda a: a.key)


# How each aircraft takes fuel in flight in DCS: "boom" (receptacle), "drogue" (probe) or "" (cannot).
REFUEL = {
    "f4e": "boom", "a10a": "boom", "a10c": "boom", "a10c2": "boom", "f16c": "boom", "f15c": "boom",
    "f15e": "boom", "a4e": "drogue", "f14a": "drogue", "f14b": "drogue", "fa18c": "drogue",
    "av8b": "drogue", "su25t": "drogue", "su33": "drogue", "j11a": "drogue", "jf17": "drogue",
    "su24m": "drogue", "su30": "drogue", "su34": "drogue", "mig31": "drogue",
}


def refuel_method(spec_or_key):
    key = getattr(spec_or_key, "key", spec_or_key)
    return REFUEL.get(key, "")
