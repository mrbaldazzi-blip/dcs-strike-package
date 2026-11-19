"""Which aircraft the user can fly, found by looking at their DCS installation.

Every module the user has installed has a folder in <DCS>/Mods/aircraft. The program reads those
folder names and offers only the matching aircraft. If DCS cannot be found, everything is offered.
The user can switch the filter off with a tick box; that choice is remembered in a small file.
"""

import json
import re
from pathlib import Path

from . import catalog, liveryscan

# Folder-name patterns (lower case, letters and digits only) for each aircraft. Flaming Cliffs
# "FC" copies of the full modules (F-5E_FC, F-86_FC, MiG-15bis_FC) are separate aircraft types in
# DCS, so they have their own entries and do not count as the full module.
PATTERNS = {
    "f86f": r"f86f(sabre)?", "f100d": r"f100d?", "f5e": r"f5e(3)?", "f4e": r"f4e(45mc)?",
    "a10a": r"a10a", "f14a": r"f14a(135gr)?", "f14b": r"f14b", "fa18c": r"fa18c",
    "f16c": r"f16c(50)?", "f15c": r"f15c", "f15e": r"f15e", "av8b": r"av8b(na)?",
    "a10c": r"a10c", "a10c2": r"a10c2", "mig15bis": r"mig15bis", "mig21bis": r"mig21bis",
    "su25": r"su25a?", "su25t": r"su25t", "mig29a": r"mig29a?", "mig29s": r"mig29s?",
    "su27": r"su27", "su33": r"su33", "j11a": r"j11a", "mig19p": r"mig19p",
    "f5e_fc": r"f5efc", "f86f_fc": r"f86f?fc", "mig15bis_fc": r"mig15bisfc",
    "l39c": r"l39c", "l39za": r"l39za", "jf17": r"jf17",
}
_COMPILED = {k: re.compile(p + "$") for k, p in PATTERNS.items()}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def settings_path(home=None):
    return (Path(home) if home else Path.home()) / ".dcs_strike_package" / "settings.json"


def installed_folders(install=None):
    """Names of the folders in <DCS>\\Mods\\aircraft, or None when DCS (or that folder) is not found."""
    dirs = [Path(install)] if install else liveryscan.install_dirs()
    for d in dirs:
        base = Path(d) / "Mods" / "aircraft"
        try:
            if base.is_dir():
                return sorted(p.name for p in base.iterdir() if p.is_dir())
        except OSError:
            continue
    return None


def keys_for(folders):
    """The aircraft keys the given Mods\\aircraft folder names correspond to."""
    names = {_norm(f) for f in folders}
    return {k for k, rx in _COMPILED.items() if any(rx.match(n) for n in names)}


def unmatched(folders):
    """Folders that matched no aircraft (so a missing module can be spotted)."""
    return sorted(f for f in folders if not any(rx.match(_norm(f)) for rx in _COMPILED.values()))


def load_choice(home=None):
    """True/False when the user has chosen; None means 'not chosen, use the default (on)'."""
    try:
        raw = json.loads(settings_path(home).read_text(encoding="utf-8"))
        v = raw.get("only_installed")
        return None if v is None else bool(v)
    except (OSError, ValueError, AttributeError):
        return None


def save_choice(value, home=None):
    p = settings_path(home)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"only_installed": bool(value)}), encoding="utf-8")
    except OSError:
        pass


def detect(install=None):
    """(keys, folders) found in the DCS install, or (None, None) if there is nothing to go on."""
    folders = installed_folders(install)
    if not folders:
        return None, None
    keys = keys_for(folders)
    return (keys or None), folders


def apply(only_installed, install=None):
    """Set the catalog filter. Returns the number of aircraft found, or None when not filtering."""
    if not only_installed:
        catalog.set_owned(None)
        return None
    keys, _ = detect(install)
    catalog.set_owned(keys)
    return None if keys is None else len(keys)


def startup(home=None, install=None):
    """Apply the saved (or default) choice. Returns (filtering, number found)."""
    choice = load_choice(home)
    only = True if choice is None else choice
    n = apply(only, install)
    return n is not None, n
