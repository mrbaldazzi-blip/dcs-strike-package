"""Find the liveries installed with DCS, without relying on pydcs's own (often empty) list.

Each livery is a folder holding a description.lua:
    <DCS>\\Bazar\\Liveries\\<aircraft type>\\<livery id>\\description.lua  (or <livery id>.zip)
    <DCS>\\CoreMods\\aircraft\\<module>\\Liveries\\<aircraft type>\\<livery id>\\description.lua
    Saved Games\\DCS*\\Liveries\\<aircraft type>\\<livery id>\\description.lua
The folder name is the livery id used in a mission; `countries = {...}` lists who may use it.
If DCS is not found, nothing is returned and aircraft keep their default skins.
"""

import os
import re
from pathlib import Path

from . import mods

_COUNTRIES = re.compile(r"countries\s*=\s*\{([^}]*)\}", re.S)
_QUOTED = re.compile(r"""["']([^"']+)["']""")
_cache = {}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def install_dirs():
    """Candidate DCS install folders, best first. Honours DCS_INSTALL and dcs_path.txt."""
    cands = []
    if os.environ.get("DCS_INSTALL"):
        cands.append(Path(os.environ["DCS_INSTALL"]))
    for f in (Path.cwd() / "dcs_path.txt", Path(__file__).resolve().parent.parent / "dcs_path.txt"):
        try:
            if f.is_file():
                cands.append(Path(f.read_text(encoding="utf-8", errors="ignore").strip().strip('"')))
        except OSError:
            pass
    try:
        import winreg
        for sub in ("DCS World", "DCS World OpenBeta", "DCS World Server"):
            for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(root, rf"SOFTWARE\Eagle Dynamics\{sub}") as k:
                        cands.append(Path(winreg.QueryValueEx(k, "Path")[0]))
                except OSError:
                    pass
    except ImportError:
        pass
    # Steam keeps its games in libraries that can be on any drive
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam") as k:
            steam = Path(winreg.QueryValueEx(k, "SteamPath")[0])
        libs = [steam]
        vdf = steam / "steamapps" / "libraryfolders.vdf"
        if vdf.is_file():
            libs += [Path(m.replace("\\\\", "\\")) for m in
                     re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="ignore"))]
        for lib in libs:
            cands.append(lib / "steamapps" / "common" / "DCSWorld")
    except Exception:  # noqa: BLE001 - no Steam
        pass
    drives = [f"{c}:\\" for c in "CDEFGHIJKLMNOPQRSTUVWXYZ"]
    for d in drives:
        for rel in (r"Program Files\Eagle Dynamics\DCS World", r"Program Files\Eagle Dynamics\DCS World OpenBeta",
                    r"Program Files (x86)\Steam\steamapps\common\DCSWorld",
                    r"SteamLibrary\steamapps\common\DCSWorld", r"Games\DCS World", r"DCS World",
                    r"DCS World OpenBeta", r"Eagle Dynamics\DCS World OpenBeta"):
            cands.append(Path(d) / rel)
    seen, out = set(), []
    for p in cands:
        try:
            if p.is_dir() and (p / "Bazar").is_dir() and str(p).lower() not in seen:
                seen.add(str(p).lower())
                out.append(p)
        except OSError:
            continue
    return out


def _liveries_roots(install, home=None):
    roots = []
    for inst in install:
        roots.append(inst / "Bazar" / "Liveries")
        for sub in ("CoreMods/aircraft", "Mods/aircraft"):
            base = inst / sub
            if base.is_dir():
                roots.extend(sorted(base.glob("*/Liveries")))
    for prof in mods.saved_games_profiles(home):
        roots.append(prof / "Liveries")
        base = prof / "Mods" / "aircraft"
        if base.is_dir():
            roots.extend(sorted(base.glob("*/Liveries")))
    return [r for r in roots if r.is_dir()]


def _description(entry):
    """Text of a livery's description.lua: from a livery folder, or from inside a .zip livery."""
    try:
        if entry.is_dir():
            return (entry / "description.lua").read_text(encoding="utf-8", errors="ignore")
        if entry.suffix.lower() == ".zip":
            import zipfile
            with zipfile.ZipFile(entry) as z:
                for member in z.namelist():
                    if member.lower().endswith("description.lua"):
                        return z.read(member).decode("utf-8", errors="ignore")
    except (OSError, ValueError, KeyError, RuntimeError, __import__("zipfile").BadZipFile):
        return None
    return None


def scan(home=None, install=None):
    """{aircraft type (lower case): [(livery id, set of normalised country tokens)]}"""
    key = (str(home), tuple(map(str, install)) if install is not None else None)
    if key in _cache:
        return _cache[key]
    index = {}
    for root in _liveries_roots(install_dirs() if install is None else install, home):
        for type_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            for liv in sorted(type_dir.iterdir()):
                text = _description(liv)
                if text is None:
                    continue
                toks = set()
                m = _COUNTRIES.search(text)
                if m:
                    toks = {_norm(x) for x in _QUOTED.findall(m.group(1))}
                name = liv.stem if liv.is_file() else liv.name
                index.setdefault(type_dir.name.lower(), []).append((name, toks))
    _cache[key] = index
    return index


def ids_for(type_id, tokens, index=None):
    """Livery ids for an aircraft type and a set of normalised country tokens.
    Country-specific liveries win; if none match, liveries without a country list are used."""
    index = scan() if index is None else index
    entries = index.get(type_id.lower(), [])
    specific = [i for i, t in entries if t & tokens]
    if specific:
        return list(dict.fromkeys(specific))
    return list(dict.fromkeys(i for i, t in entries if not t))
