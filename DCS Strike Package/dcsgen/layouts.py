"""How a ground group is laid out: parked in rows, driving in column, a line abreast, or a SAM site.

Both the mission builder (real positions in metres) and the target photos (pixels) use the same
layout, so the pictures show exactly what the pilot will find. A layout is a list of
(forward, right, heading_offset_deg) per unit, in "slots": the builder multiplies slots by a distance
in metres, the photo by a number of pixels. Forward is along the group's heading.
"""

import math
import zlib

from . import silhouettes

# slot size in metres: (forward, right)
SLOT_M = {"park": (24.0, 15.0), "column": (30.0, 0.0), "line": (45.0, 32.0), "site": (45.0, 45.0),
           "skirmish": (7.0, 9.0)}
CENTRE_SHAPES = ("radar", "command", "ewr")


def formation_of(group):
    """'park' | 'column' | 'line' | 'site' for a ground Group (deterministic)."""
    tag, name = group.tag, group.name.lower()
    if tag in ("sam",) or name.startswith("sam"):
        return "site"
    if tag == "route" or "convoy" in name:
        return "column"
    if tag == "frontline" and all(c.startswith(("Soldier", "Infantry", "Paratrooper"))
                                  for c, _n in group.units):
        return "skirmish"         # foot soldiers spread out a few metres apart, not tank-wide
    if tag in ("aaa", "frontline"):
        return "line"
    if tag == "garrison" and zlib.crc32(name.encode()) % 100 < 30:
        return "column"           # some garrison groups are on the move
    return "park"


def _flat(group):
    return [cls for cls, n in group.units for _ in range(n)]


def layout(group, names=None):
    """Offsets for every unit of the group, in order. `names` overrides the unit class list."""
    names = list(names) if names is not None else _flat(group)
    n = len(names)
    kind = formation_of(group)
    if n == 0:
        return kind, []
    if kind == "column":
        return kind, [((n - 1) / 2 - i, 0.0, 0.0) for i in range(n)]
    if kind == "site":
        centre = [i for i, c in enumerate(names) if silhouettes.classify(c).startswith(CENTRE_SHAPES)]
        ring = [i for i in range(n) if i not in centre]
        out = [None] * n
        for j, i in enumerate(centre):
            out[i] = (0.0, (j - (len(centre) - 1) / 2) * 0.9, 0.0)
        for j, i in enumerate(ring):
            ang = 2 * math.pi * j / max(1, len(ring)) + math.pi / 4
            f, r = 2.4 * math.cos(ang), 2.4 * math.sin(ang)
            out[i] = (f, r, math.degrees(math.atan2(r, f)))
        return kind, out
    per_row = 8 if kind in ("line", "skirmish") else (4 + zlib.crc32(group.name.encode()) % 3)   # 4 to 6 abreast
    if n <= per_row:
        rows = [n]
    else:
        nrows = math.ceil(n / per_row)
        base, extra = divmod(n, nrows)
        rows = [base + (1 if i < extra else 0) for i in range(nrows)]
    out = []
    for r, count in enumerate(rows):
        for c in range(count):
            out.append((-float(r), c - (count - 1) / 2, 0.0))
    return kind, out


def place_metres(group, units, pos_x, pos_y, names):
    """Move pydcs units into the group's layout, around (pos_x, pos_y); headings in degrees.
    `names` are the DCS class names of the units, in the same order as `units`."""
    kind, offs = layout(group, names)
    fwd_m, right_m = SLOT_M[kind]
    h = math.radians(group.heading_deg)
    for u, (f, r, hoff) in zip(units, offs):
        fm, rm = f * fwd_m, r * right_m
        u.position.x = pos_x + fm * math.cos(h) - rm * math.sin(h)
        u.position.y = pos_y + fm * math.sin(h) + rm * math.cos(h)
        u.heading = (group.heading_deg + hoff) % 360
    return kind
