"""Community aircraft mods (A-4E-C, OV-10A Bronco): find the real DCS type id on this PC.

pydcs does not know about mods, and a mod's DCS type id is not published anywhere reliable. But
every mod installed under  Saved Games\\DCS\\Mods\\aircraft\\<name>\\entry.lua  declares its
type id in a line like  make_flyable('A-4E-C', ...) . This module reads those files, matches
each mod in the catalog by folder name, and uses the id it finds. If nothing is installed,
the catalog's best guess is used and the builder warns about it.
"""

import re
from pathlib import Path

_MAKE_FLYABLE = re.compile(r"""make_flyable\(\s*['"]([^'"]+)['"]""")


def saved_games_dir(home=None):
    """The Windows 'Saved Games' folder. Asks Windows, so it is right even when the folder has been
    moved (to another drive or OneDrive); falls back to <home>\\Saved Games."""
    if home:
        return Path(home) / "Saved Games"
    try:
        import ctypes
        # FOLDERID_SavedGames = {4C5C32FF-BB9D-43B0-B5B4-2D72E54EAAA4}
        fid = (ctypes.c_ubyte * 16)(0xFF, 0x32, 0x5C, 0x4C, 0x9D, 0xBB, 0xB0, 0x43,
                                    0xB5, 0xB4, 0x2D, 0x72, 0xE5, 0x4E, 0xAA, 0xA4)
        out = ctypes.c_wchar_p()
        res = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(out))
        if res == 0 and out.value:
            path = Path(out.value)
            ctypes.windll.ole32.CoTaskMemFree(out)
            return path
    except Exception:  # noqa: BLE001 - not Windows, or the call failed
        pass
    return Path.home() / "Saved Games"


def saved_games_profiles(home=None):
    """Saved Games folders that look like a DCS profile (DCS, DCS.openbeta, ...)."""
    base = saved_games_dir(home)
    if not base.is_dir():
        return []
    return sorted((p for p in base.glob("DCS*") if p.is_dir()),
                  key=lambda p: (p.name != "DCS", p.name))


def scan_installed_mods(home=None):
    """{folder name: [declared flyable type ids]} for every aircraft mod found."""
    found = {}
    for profile in saved_games_profiles(home):
        for entry in sorted((profile / "Mods" / "aircraft").glob("*/[Ee]ntry.lua")):
            try:
                text = entry.read_text(errors="ignore")
            except OSError:
                continue
            found.setdefault(entry.parent.name, [])
            for type_id in _MAKE_FLYABLE.findall(text):
                if type_id not in found[entry.parent.name]:
                    found[entry.parent.name].append(type_id)
    return found


def resolve_mod_type(spec, installed=None):
    """Return (dcs_type_id, source) where source is "found" or "guess"."""
    installed = scan_installed_mods() if installed is None else installed
    for folder, ids in installed.items():
        hay = " ".join([folder.lower()] + [i.lower() for i in ids])
        if ids and any(term in hay for term in spec.search):
            return ids[0], "found"
    return spec.dcs_type, "guess"
