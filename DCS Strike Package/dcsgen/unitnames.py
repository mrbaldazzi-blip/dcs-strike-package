"""Resolve our unit-name strings against whatever pydcs is installed.

pydcs names change between versions, and several of ours are educated guesses. So a
name is looked up several ways before giving up:

  1. the exact attribute / class name,
  2. the name with punctuation normalised (DCS type id style: "Hawk sr" -> "Hawk_sr"),
  3. a "squashed" comparison that ignores case, underscores and punctuation,
  4. any aliases listed below,
  5. the DCS type id as a key of pydcs's own plane/vehicle/ship maps.

The functions take the pydcs modules as arguments, so they can be tested with fakes.
"""

import re

# logical name -> alternative names to try, in order
ALIASES = {
    # ships
    "Stennis": ["CVN_74_John_C__Stennis", "CVN_74", "Stennis"],
    "KUZNECOW": ["Kuznetsov", "CV_1143_5_Admiral_Kuznetsov", "Admiral_Kuznetsov"],
    # red air defence
    "SNR_75V": ["SNR_75V_Fan_Song", "Fan_Song"],
    "S_75M_Volhov": ["S_75M", "SA_2_Volhov"],
    "p_19_s_125_sr": ["p_19_s_125_sr_Flat_Face", "P_19"],
    "snr_s_125_tr": ["snr_s_125_Low_Blow", "SNR_125"],
    "Kub_1S91_str": ["Kub_1S91", "SA_6_Kub_STR"],
    "S_300PS_40B6MD_sr": ["S_300PS_64H6E_sr"],
    # blue air defence
    "Hawk_sr": ["Hawk_SR"], "Hawk_tr": ["Hawk_TR"], "Hawk_ln": ["Hawk_LN"],
    "Patriot_str": ["Patriot_STR"], "Patriot_ln": ["Patriot_LN"], "Patriot_cp": ["Patriot_CP"],
    "FPS_117": ["FPS_117_Dome", "FPS_117_ECS"],
    "M1097_Avenger": ["Avenger"],
    # blue soft vehicles
    "M_818": ["M818", "M_818_ammo_truck", "Hummer"],
    "M978_HEMTT_Tanker": ["M978", "M_978_HEMTT_Tanker", "M_818"],
    # aircraft
    "F_100D": ["F_100D_Super_Sabre"],
}


def squash(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def normalise(name: str) -> str:
    """DCS type id style to a python identifier: 'Hawk sr' -> 'Hawk_sr', '5p73 s-125 ln' -> 'X_5p73_s_125_ln'."""
    ident = re.sub(r"[^0-9A-Za-z]+", "_", str(name)).strip("_")
    return ("X_" + ident) if ident[:1].isdigit() else ident


def _candidates(name):
    seen, out = set(), []
    for n in [name, normalise(name), *ALIASES.get(name, [])]:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def class_index(containers, maps=()):
    """Build {name: class} from pydcs modules/classes and {dcs_id: class} maps."""
    by_name, by_squash, by_id = {}, {}, {}
    for c in containers:
        for attr in dir(c):
            if attr.startswith("_"):
                continue
            obj = getattr(c, attr, None)
            if isinstance(obj, type):
                by_name.setdefault(attr, obj)
                by_squash.setdefault(squash(attr), obj)
    for mp in maps:
        for dcs_id, cls in dict(mp).items():
            by_id.setdefault(str(dcs_id), cls)
            nm = getattr(cls, "__name__", None)
            if nm:
                by_name.setdefault(nm, cls)
                by_squash.setdefault(squash(nm), cls)
    return by_name, by_squash, by_id


def find(name, index, extra_ids=()):
    """Return the class for `name` (trying aliases and DCS ids), or None."""
    by_name, by_squash, by_id = index
    for cand in _candidates(name):
        if cand in by_name:
            return by_name[cand]
    for cand in _candidates(name):
        hit = by_squash.get(squash(cand))
        if hit is not None:
            return hit
    for dcs_id in (name, *extra_ids):
        if dcs_id in by_id:
            return by_id[dcs_id]
    return None


def closest(name, index, n=5):
    import difflib
    by_name, _, _ = index
    return difflib.get_close_matches(name, list(by_name), n=n, cutoff=0.45)
