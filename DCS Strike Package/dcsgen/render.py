"""Printed-briefing renderer: turns a Briefing into page images, a PDF and kneeboard PNGs.

One layout (768 x 1024 logical units, the DCS kneeboard shape) is drawn at 2x for the PDF and
reduced to 768 x 1024 for the kneeboard, so both always match. Everything is drawn with Pillow
(no other dependencies). Insignia are simple original drawings of the national roundels, and
every page is stamped as a fictional exercise.
"""

import io
import math
import re
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

import random

from . import layouts, silhouettes
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 768, 1024
MARGIN = 26
PAPER = (244, 240, 228)
INK = (30, 32, 38)
GREY = (112, 110, 102)
RULE = (150, 146, 134)
BLUE = (32, 82, 170)
RED = (186, 38, 38)
BODY, LINE = 15, 19                 # body font size and line height (logical px)

_FONTS = {
    "mono": ["consola.ttf", "Consolas.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
             "/System/Library/Fonts/Menlo.ttc", "DejaVuSansMono.ttf"],
    "mono_bold": ["consolab.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
                  "DejaVuSansMono-Bold.ttf"],
    "sans": ["arial.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf"],
    "sans_bold": ["arialbd.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"],
}

NAVY_JETS = {"fa18c", "f14a", "f14b", "a4e"}
MARINE_JETS = {"av8b"}

# service -> (title, roundel, band colour)
SERVICES = {
    "USAF": ("UNITED STATES AIR FORCE", "us", (24, 44, 96)),
    "USN": ("UNITED STATES NAVY", "us", (24, 44, 96)),
    "USMC": ("UNITED STATES MARINE CORPS", "us", (24, 44, 96)),
    "VVS": ("SOVIET AIR FORCES", "soviet", (118, 24, 28)),
    "VKS": ("RUSSIAN AEROSPACE FORCES", "russian", (118, 24, 28)),
    "LUFTWAFFE": ("LUFTWAFFE", "german", (40, 42, 46)),
    "PLAAF": ("PEOPLE'S LIBERATION ARMY AIR FORCE", "soviet", (118, 24, 28)),
}


@lru_cache(maxsize=None)
def font(kind, px):
    for name in _FONTS[kind]:
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=px)
    except TypeError:                      # very old Pillow
        return ImageFont.load_default()


@dataclass
class RenderedPage:
    name: str            # file-name stem, e.g. "02_strike-dagger-1"
    image: object        # PIL image at 2x scale


# ---- roundels ---------------------------------------------------------------------------------

def _star(cx, cy, r, rot=-90.0):
    pts = []
    for i in range(10):
        ang = math.radians(rot + i * 36)
        rad = r if i % 2 == 0 else r * 0.382
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    return pts


def roundel(kind, size):
    """Return an RGBA image of a national roundel, drawn at 4x and reduced for smooth edges."""
    n = size * 4
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c, r = n / 2, n / 2 - 4
    if kind == "us":
        d.ellipse([c - r, c - r, c + r, c + r], fill=(22, 46, 110), outline=(255, 255, 255), width=n // 40)
        d.polygon(_star(c, c, r * 0.62), fill=(255, 255, 255))
        bh = r * 0.30
        for sx in (-1, 1):
            x0 = c + sx * r * 0.70
            x1 = c + sx * r * 1.22 if False else c + sx * r * 1.0
            d.rectangle([min(x0, x1), c - bh / 2, max(x0, x1), c + bh / 2], fill=(255, 255, 255))
        d.ellipse([c - r, c - r, c + r, c + r], outline=(190, 30, 40), width=n // 30)
    elif kind == "soviet":
        d.ellipse([c - r, c - r, c + r, c + r], fill=(244, 240, 228), outline=(60, 60, 60), width=n // 50)
        d.polygon(_star(c, c, r * 0.86), fill=(196, 28, 34), outline=(100, 14, 18))
    elif kind == "russian":
        d.ellipse([c - r, c - r, c + r, c + r], fill=(30, 70, 160))
        d.ellipse([c - r * 0.80, c - r * 0.80, c + r * 0.80, c + r * 0.80], fill=(255, 255, 255))
        d.polygon(_star(c, c, r * 0.74), fill=(196, 28, 34))
    elif kind == "german":
        d.ellipse([c - r, c - r, c + r, c + r], fill=(244, 240, 228))
        t, long_ = r * 0.26, r * 0.82
        for pts in ([c - long_, c - t, c + long_, c + t], [c - t, c - long_, c + t, c + long_]):
            d.rectangle(pts, fill=(20, 20, 20), outline=(255, 255, 255), width=n // 50)
    else:
        from . import emblems
        extra = emblems.draw(kind, n)
        if extra is not None:
            im = extra
    return im.resize((size, size), Image.LANCZOS)


# ---- drawing surface --------------------------------------------------------------------------

class Canvas:
    """Draws in logical units; scales everything by S."""

    def __init__(self, scale):
        self.S = scale
        self.img = Image.new("RGB", (W * scale, H * scale), PAPER)
        self.d = ImageDraw.Draw(self.img)

    def f(self, kind, px):
        return font(kind, max(6, int(round(px * self.S))))

    def width(self, s, kind="mono", px=BODY):
        return self.f(kind, px).getlength(s) / self.S

    def text(self, x, y, s, kind="mono", px=BODY, fill=INK, anchor="la"):
        self.d.text((x * self.S, y * self.S), s, font=self.f(kind, px), fill=fill, anchor=anchor)

    def line(self, p0, p1=None, fill=INK, width=1):
        """Draw a line from two points, or from one (x0, y0, x1, y1) tuple."""
        S = self.S
        if p1 is None:
            x0, y0, x1, y1 = p0
        else:
            (x0, y0), (x1, y1) = p0, p1
        self.d.line([x0 * S, y0 * S, x1 * S, y1 * S], fill=fill, width=max(1, int(width * S)))

    def rect(self, box, outline=None, fill=None, width=1):
        S = self.S
        self.d.rectangle([box[0] * S, box[1] * S, box[2] * S, box[3] * S], outline=outline, fill=fill,
                         width=max(1, int(width * S)))

    def paste(self, im, x, y):
        """Paste an image that is already drawn at this canvas's scale."""
        S = self.S
        self.img.paste(im, (int(x * S), int(y * S)), im if im.mode == "RGBA" else None)


def wrap(c, text, kind, px, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if c.width(trial, kind, px) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


# ---- plan-view map ----------------------------------------------------------------------------

ROLE_COLOUR = {"strike": (20, 20, 24), "cas": (20, 20, 24), "dead": (20, 20, 24),
               "sead": (206, 120, 20), "cap": (40, 130, 70),
               "naval": (20, 20, 24), "intercept": (40, 130, 70)}


def _dashed(d, p0, p1, fill, width, dash=10, gap=7):
    x0, y0 = p0
    x1, y1 = p1
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 1:
        return
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    pos = 0.0
    while pos < length:
        end = min(pos + dash, length)
        d.line([x0 + ux * pos, y0 + uy * pos, x0 + ux * end, y0 + uy * end], fill=fill, width=width)
        pos += dash + gap


def _arrow(d, tip, ang, size, fill):
    a = math.radians(ang)
    pts = [tip,
           (tip[0] - size * math.cos(a - 0.45), tip[1] - size * math.sin(a - 0.45)),
           (tip[0] - size * math.cos(a + 0.45), tip[1] - size * math.sin(a + 0.45))]
    d.polygon(pts, fill=fill)


def draw_map(plan, size, focus=None, S=2, across=False):
    """Plan view centred on the objective. `focus` is the flight to emphasise (None = whole package)."""
    from .planner import _offset  # noqa: F401  (kept for symmetry; geometry is local below)
    mw, mh = int(size[0] * S), int(size[1] * S)
    im = Image.new("RGB", (mw, mh), (228, 224, 208))
    d = ImageDraw.Draw(im, "RGBA")
    rot = plan.rotation_deg
    me = BLUE if plan.player_side == "blue" else RED
    foe = RED if plan.player_side == "blue" else BLUE

    cx, cy = mw / 2, mh / 2

    spin = 0.0
    if across:
        lead = next((f for f in plan.flights if f.primary), plan.flights[0] if plan.flights else None)
        if lead is not None and lead.waypoints:
            w0 = lead.waypoints[0]
            r0 = math.radians(w0.bearing_deg + rot)
            vx, vy = -w0.distance_nm * math.sin(r0), -w0.distance_nm * math.cos(r0)   # start -> target
            if abs(vx) + abs(vy) > 1e-6:
                spin = 90.0 - math.degrees(math.atan2(vx, vy))

    def xy(bearing, dist):
        r = math.radians(bearing + rot + spin)
        return dist * math.sin(r), dist * math.cos(r)

    # Zoom to fit: show the target and the waypoints that matter (not the far-away start and
    # landing, which get edge labels), then round the view up to a tidy size.
    margin = int(30 * S)
    need = [(0.0, 0.0)]
    for fl in ([focus] if focus is not None else [f for f in plan.flights if f.primary]):
        for wp in (fl.waypoints if across else fl.waypoints[1:-1]):
            if wp.distance_nm > 18 and not across:
                continue                      # far legs run off the edge with a label
            need.append(xy(wp.bearing_deg, wp.distance_nm))
    xs, ys = [x for x, _ in need], [y for _, y in need]
    ox, oy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2          # centre the view on what matters
    hw, hh = max((max(xs) - min(xs)) / 2, 0.5), max((max(ys) - min(ys)) / 2, 0.5)
    fit = min((mw / 2 - margin) / hw, (mh / 2 - margin) / hh)          # pixels per nm that just fits
    short = min(mw, mh)
    if across:
        fit_w = (mw / 2 - margin) / hw
        scale = max(fit, 0.6 * fit_w)                # width sets the scale; legs may run off the top/bottom
        oy = 0.0                                     # keep the target on the centre line
        half = short / (2 * scale)
        step = 5 if half <= 15 else 10
    else:
        half = min(max(short / (2 * fit), 10.0), 32.0)
        half = next(v for v in (10, 12, 15, 20, 25, 32) if v >= half - 1e-9)
        scale = short / (2 * half)
        step = 2 if half <= 8 else 5 if half <= 15 else 10

    def P(bearing, dist):
        x, y = xy(bearing, dist)
        return cx + (x - ox) * scale, cy - (y - oy) * scale

    px = lambda v: int(round(v * S))
    small = font("sans", px(9.5))
    tiny = font("sans_bold", px(8.5))

    # grid lines at a tidy spacing
    reach = int((max(mw, mh) / scale / 2 + abs(ox) + abs(oy)) / step) + 2
    gstep = step * 2 if across and step * scale < px(18) else step
    for k in range(-reach * gstep, reach * gstep + 1, gstep):
        d.line([cx + (k - ox) * scale, 0, cx + (k - ox) * scale, mh], fill=(200, 196, 180), width=1)
        d.line([0, cy - (k - oy) * scale, mw, cy - (k - oy) * scale], fill=(200, 196, 180), width=1)

    # SAM / AAA lethal rings
    for g in plan.groups:
        if g.tag in ("sam", "target") and g.range_nm and g.range_nm <= 30:
            gx, gy = P(g.bearing_deg, g.distance_nm)
            rr = g.range_nm * scale
            ring = foe + (34,)
            d.ellipse([gx - rr, gy - rr, gx + rr, gy + rr], fill=ring, outline=foe + (150,), width=max(1, px(0.8)))

    # frontline
    if plan.frontline:
        f = plan.frontline
        cb = P(f.bearing_deg, f.distance_nm)
        hx, hy = xy(f.heading_deg, f.length_nm / 2 * 1.0)
        a_pt = (cb[0] - hx * scale, cb[1] + hy * scale)
        b_pt = (cb[0] + hx * scale, cb[1] - hy * scale)
        d.line([a_pt, b_pt], fill=(60, 60, 60), width=px(2.2))
        # teeth on the enemy side (away from the base, toward the objective)
        ex, ey = xy(f.bearing_deg + 180, 1.0)
        for k in range(-3, 4):
            tx = cb[0] + (b_pt[0] - cb[0]) * k / 3.5
            ty = cb[1] + (b_pt[1] - cb[1]) * k / 3.5
            d.polygon([(tx - 3 * S, ty - 3 * S), (tx + 3 * S, ty + 3 * S),
                       (tx + ex * 7 * S, ty - ey * 7 * S)], fill=foe + (220,))
        d.text((cb[0] + 4 * S, cb[1] + 3 * S), "FLOT", font=tiny, fill=(60, 60, 60))

    # ground groups, AAA, EWR, CAP
    for g in plan.groups:
        gx, gy = P(g.bearing_deg, g.distance_nm)
        col = me if g.side == plan.player_side else foe
        if not (-20 < gx < mw + 20 and -20 < gy < mh + 20):
            continue
        if g.tag == "sam":
            r = px(5.5)
            d.polygon([(gx, gy - r), (gx - r, gy + r * 0.8), (gx + r, gy + r * 0.8)], fill=col, outline=(255, 255, 255, 200))
            d.text((gx + px(7), gy - px(5)), re.sub(r"^SAM - ", "", g.name).split()[0], font=small, fill=col)
        elif g.tag == "aaa":
            r = px(3.5)
            d.line([gx - r, gy - r, gx + r, gy + r], fill=col, width=px(1.6))
            d.line([gx - r, gy + r, gx + r, gy - r], fill=col, width=px(1.6))
        elif g.tag == "ewr":
            r = px(4)
            d.ellipse([gx - r, gy - r, gx + r, gy + r], outline=col, width=px(1.5))
            d.text((gx + px(6), gy - px(4)), "EW", font=tiny, fill=col)
        elif g.tag == "cap":
            r = px(5)
            d.polygon([(gx, gy - r), (gx - r, gy + r), (gx, gy + r * 0.4), (gx + r, gy + r)], fill=col)
            d.text((gx + px(7), gy - px(4)), "CAP", font=tiny, fill=col)
        elif g.tag in ("frontline", "route"):
            r = px(4)
            d.rectangle([gx - r * 1.3, gy - r, gx + r * 1.3, gy + r], outline=col, fill=col + (70,), width=px(1.2))

    # ships
    for g in plan.groups:
        if g.kind != "ship":
            continue
        gx, gy = P(g.bearing_deg, g.distance_nm)
        r = px(6 if g.tag == "target" else 4)
        d.polygon([(gx, gy - r * 1.4), (gx + r * 0.7, gy + r), (gx - r * 0.7, gy + r)], fill=foe)
        d.text((gx + px(8), gy - px(5)), "TGT SHIP" if g.tag == "target" else "ESC", font=tiny, fill=foe)

    # the inbound raid (Intercept): its route, and a label at the edge when it starts off the map
    for g in plan.groups:
        if g.tag not in ("raid", "raid_escort") or len(g.route) < 2:
            continue
        p0 = P(g.bearing_deg, g.distance_nm)
        p1 = P(*g.route[-1])
        _dashed(d, p0, p1, foe, px(2.0))
        _arrow(d, ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2),
               math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0])), px(7), foe)
        if g.tag == "raid":
            vx, vy = p0[0] - cx, p0[1] - cy
            k = min((cx - px(14)) / abs(vx) if vx else 1e9, (cy - px(14)) / abs(vy) if vy else 1e9, 1.0)
            ex, ey = cx + vx * k, cy + vy * k
            d.text((min(max(ex, px(30)), mw - px(60)), min(max(ey, px(8)), mh - px(14))),
                   f"RAID {g.distance_nm:.0f}nm", font=tiny, fill=foe, anchor="mm")

    # routes
    def role_colour(fl):
        return ROLE_COLOUR[fl.role.value]

    flights = plan.flights if focus is None else [fl for fl in plan.flights if fl is not focus] + [focus]
    off_marks = []
    for fl in flights:
        is_focus = focus is not None and fl is focus
        col = role_colour(fl) if (focus is None or is_focus) else (150, 148, 140)
        width = px(2.6 if (is_focus or (focus is None and fl.primary)) else 1.4)
        pts = [P(wp.bearing_deg, wp.distance_nm) for wp in fl.waypoints]
        for a, b in zip(pts, pts[1:]):
            if is_focus or (focus is None and fl.primary):
                d.line([a, b], fill=col, width=width)
            else:
                _dashed(d, a, b, col, width)
        # direction arrows at leg midpoints
        for a, b in zip(pts, pts[1:]):
            mx_, my_ = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            if 8 < mx_ < mw - 8 and 8 < my_ < mh - 8 and math.hypot(b[0] - a[0], b[1] - a[1]) > px(30):
                _arrow(d, (mx_, my_), math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])), px(6), col)
        # waypoint markers
        for i, (wp, p) in enumerate(zip(fl.waypoints, pts)):
            inside = 10 < p[0] < mw - 10 and 10 < p[1] < mh - 10
            if inside and (is_focus or focus is None):
                if wp.name == fl.key_waypoint:
                    r = px(7)
                    d.polygon([(p[0], p[1] - r), (p[0] + r, p[1]), (p[0], p[1] + r), (p[0] - r, p[1])],
                              fill=(255, 255, 255, 235), outline=col, width=px(1.8))
                    d.line([p[0] - r * 1.5, p[1], p[0] + r * 1.5, p[1]], fill=col, width=px(1))
                    d.line([p[0], p[1] - r * 1.5, p[0], p[1] + r * 1.5], fill=col, width=px(1))
                    if is_focus or fl.primary:
                        d.text((p[0] + px(9), p[1] + px(5)),
                               {"sead": "SAM", "intercept": "MERGE"}.get(fl.role.value, "TGT"), font=tiny, fill=col)
                elif is_focus:
                    r = px(6.5)
                    d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=(255, 255, 255, 240), outline=col, width=px(1.4))
                    d.text((p[0], p[1]), str(i + 1), font=tiny, fill=col, anchor="mm")
                    d.text((p[0] + px(8), p[1] - px(5)), wp.name, font=small, fill=(40, 40, 40))
            elif not inside and (is_focus or fl.primary) and 0 < i < len(fl.waypoints) - 1:
                off_marks.append((wp, p, col))
            elif not inside and (is_focus or fl.primary) and i in (0, len(fl.waypoints) - 1):
                off_marks.append((wp, p, col))

    # edge labels for waypoints that fall off the map. Markers that land in the same spot (Start
    # and Land are both the home airfield) share one label instead of printing over each other.
    spots = {}
    for wp, p, col in off_marks:
        vx, vy = p[0] - cx, p[1] - cy
        k = min((cx - px(14)) / abs(vx) if vx else 1e9, (cy - px(14)) / abs(vy) if vy else 1e9)
        ex, ey = cx + vx * k, cy + vy * k
        spot = spots.setdefault((round(ex / 40), round(ey / 40)), {"ex": ex, "ey": ey, "vx": vx,
                                                                   "vy": vy, "col": col, "names": [],
                                                                   "dist": wp.distance_nm})
        if wp.name.upper() not in spot["names"]:
            spot["names"].append(wp.name.upper())
    for spot in spots.values():
        ex, ey, vx, vy, col = spot["ex"], spot["ey"], spot["vx"], spot["vy"], spot["col"]
        _arrow(d, (ex, ey), math.degrees(math.atan2(vy, vx)), px(7), col)
        label = f"{'/'.join(spot['names'])} {spot['dist']:.0f}nm"
        tw = d.textlength(label, font=tiny)
        lx = min(max(ex - tw / 2, px(3)), mw - tw - px(3))
        ly = min(max(ey - px(5) - (px(11) if vy > 0 else -px(7)), px(2)), mh - px(12))
        d.rectangle([lx - px(2), ly - px(1), lx + tw + px(2), ly + px(10)], fill=(244, 240, 228, 215))
        d.text((lx, ly), label, font=tiny, fill=col)

    # scale bar and north arrow
    if across:
        bar_nm = next((v for v in (50, 25, 20, 10, 5, 2) if v * scale <= mw * 0.22), 2)
    else:
        bar_nm = step * (2 if half >= 20 else 1) if half > 8 else step
    bar = bar_nm * scale
    bx, by = px(8), mh - px(12)
    d.line([bx, by, bx + bar, by], fill=INK, width=px(2))
    d.line([bx, by - px(3), bx, by + px(3)], fill=INK, width=px(1.4))
    d.line([bx + bar, by - px(3), bx + bar, by + px(3)], fill=INK, width=px(1.4))
    d.text((bx + bar + px(4), by - px(5)), f"{bar_nm} NM", font=tiny, fill=INK)
    nx, ny = mw - px(16), px(26)
    if across and mh < px(150):
        nx, ny = mw - px(20), px(16)
    if across:                                    # the map is turned, so draw where true north points
        ux, uy = xy(0, 1.0)
        ang = math.atan2(-uy, ux)                  # screen angle of north
        tip = (nx + math.cos(ang) * px(11), ny + math.sin(ang) * px(11))
        tail = (nx - math.cos(ang) * px(7), ny - math.sin(ang) * px(7))
        perp = (-math.sin(ang) * px(4.5), math.cos(ang) * px(4.5))
        d.polygon([tip, (tail[0] + perp[0], tail[1] + perp[1]), (tail[0] - perp[0], tail[1] - perp[1])], fill=INK)
        d.text((nx + math.cos(ang) * px(19), ny + math.sin(ang) * px(19)), "N", font=tiny, fill=INK, anchor="mm")
    else:
        d.polygon([(nx, ny - px(14)), (nx - px(5), ny), (nx + px(5), ny)], fill=INK)
        d.text((nx, ny + px(2)), "N", font=tiny, fill=INK, anchor="ma")
    tag = "TRUE NORTH" if plan.geometry_final else "SCHEMATIC"
    d.text((mw - px(6), mh - px(12)), tag, font=tiny, fill=GREY, anchor="ra")

    d.rectangle([0, 0, mw - 1, mh - 1], outline=INK, width=max(1, px(1.2)))
    return im


# ---- stylised aerial photos -------------------------------------------------------------------

def _terrain_texture(rng, w, h):
    """A grey 'film' base: soft patches, field parcels and tree stands."""
    base = Image.new("L", (w, h), 128)
    lo = Image.new("L", (14, 14))
    lo.putdata([rng.randint(70, 190) for _ in range(14 * 14)])
    base = ImageChops.blend(base, lo.resize((w, h), Image.BICUBIC), 0.85)
    d = ImageDraw.Draw(base)
    for _ in range(26):                                   # field parcels with hard edges
        x, y = rng.randint(-w // 8, w), rng.randint(-h // 8, h)
        pw, ph = rng.randint(w // 10, w // 3), rng.randint(h // 12, h // 4)
        d.rectangle([x, y, x + pw, y + ph], fill=rng.randint(95, 175))
        for k in range(0, ph, max(4, ph // 9)):           # furrow lines
            d.line([x, y + k, x + pw, y + k], fill=rng.randint(85, 150), width=1)
    for _ in range(30):                                   # tree stands, darker and rounder
        x, y, r = rng.randint(0, w), rng.randint(0, h), rng.randint(w // 70, w // 26)
        d.ellipse([x - r, y - r, x + r, y + r], fill=rng.randint(55, 90))
    return base.filter(ImageFilter.GaussianBlur(max(1, w // 400)))


def _sea_texture(rng, w, h):
    """Open water: a smooth dark swell with short bright wave crests."""
    base = Image.new("L", (w, h), 92)
    lo = Image.new("L", (10, 10))
    lo.putdata([rng.randint(60, 120) for _ in range(100)])
    base = ImageChops.blend(base, lo.resize((w, h), Image.BICUBIC), 0.9)
    d = ImageDraw.Draw(base)
    for _ in range(int(w * h / 2200)):
        x, y = rng.randint(0, w), rng.randint(0, h)
        ln = rng.randint(max(4, w // 90), max(8, w // 36))
        d.line([x, y, x + ln, y + rng.randint(-2, 2)], fill=rng.randint(125, 165), width=1)
    return base.filter(ImageFilter.GaussianBlur(max(1, w // 600)))


_SHIP_M = {"KUZNECOW": 305, "Stennis": 333, "Forrestal": 325, "Essex": 270, "MOSCOW": 186,
           "PIOTR": 252, "TICONDEROG": 173, "USS_Arleigh_Burke_IIa": 155, "PERRY": 135,
           "NEUSTRASH": 130, "REZKY": 124, "ALBATROS": 82, "MOLNIYA": 56, "ELNYA": 160,
           "Dry_cargo_ship_1": 120, "Dry_cargo_ship_2": 110}
_CARRIERS = {"KUZNECOW", "Stennis", "Forrestal", "Essex"}
_CARGO = {"ELNYA", "Dry_cargo_ship_1", "Dry_cargo_ship_2"}


def draw_ship(d, cls, x, y, heading_deg, length_px, S, tone=235, wake=None):
    """A top-down ship drawn into a greyscale layer (tone = brightness, so the photo pass can turn
    it into relief). Heading is a compass bearing; north is up on the page. `wake`, when given,
    is a second layer that receives the bow wave and the churned water behind the stern."""
    a = math.radians(heading_deg)
    fx, fy = math.sin(a), -math.cos(a)           # bow direction on the page
    rx, ry = -fy, fx                             # starboard

    def pt(f, r):
        return (x + (f * fx + r * rx) * length_px, y + (f * fy + r * ry) * length_px)

    def poly(points, fill):
        d.polygon([pt(f, r) for f, r in points], fill=max(1, min(255, fill)))

    def box(f0, f1, r0, r1, fill):
        poly([(f1, r0), (f1, r1), (f0, r1), (f0, r0)], fill)

    def dot(f, r, rad, fill):
        px_, py_ = pt(f, r)
        rr = max(1.0, rad * length_px)
        d.ellipse([px_ - rr, py_ - rr, px_ + rr, py_ + rr], fill=max(1, min(255, fill)))

    L = 0.5
    base_t = 58 if tone < 220 else 70           # the target is a little brighter
    if wake is not None:
        for sgn in (-1, 1):                                             # bow wave and Kelvin wake
            wake.line([pt(0.46, sgn * 0.04), pt(0.3, sgn * 0.085), pt(-0.1, sgn * 0.11)],
                      fill=200, width=max(1, int(2 * S)))
            wake.line([pt(-L, sgn * 0.03), pt(-L - 0.7, sgn * 0.2)], fill=130, width=max(1, int(1.2 * S)))
        wake.line([pt(-L, 0), pt(-L - 0.9, 0)], fill=170, width=max(2, int(0.03 * length_px)))
        for k in range(1, 9):                                           # foam patches in the track
            wake.ellipse([pt(-L - 0.13 * k, 0)[0] - 3 * S, pt(-L - 0.13 * k, 0)[1] - 3 * S,
                          pt(-L - 0.13 * k, 0)[0] + 3 * S, pt(-L - 0.13 * k, 0)[1] + 3 * S], fill=140)
    if cls in _CARRIERS:
        poly([(L, 0), (0.36, 0.08), (-L, 0.09), (-L, -0.1), (0.36, -0.08)], base_t - 20)     # hull
        poly([(0.44, 0), (0.3, -0.078), (0.0, -0.088), (-0.2, -0.13), (-0.5, -0.15), (-0.5, 0.09), (0.3, 0.078)], base_t + 8)   # flight deck
        poly([(0.12, -0.012), (-0.46, -0.13), (-0.46, -0.118), (0.12, 0.0)], base_t + 70)        # angled-deck line
        box(-0.48, 0.4, 0.02, 0.028, base_t + 60)                                           # centreline
        box(-0.05, 0.12, 0.062, 0.1, base_t + 52)                                             # island
        box(0.0, 0.05, 0.058, 0.07, base_t + 75)
        for i, (f, r) in enumerate(((-0.3, 0.03), (-0.36, 0.045), (-0.24, 0.05), (-0.42, 0.02),
                                    (-0.18, 0.012), (-0.34, -0.04), (-0.4, -0.08))):               # parked aircraft
            dot(f, r, 0.012, base_t + 85)
            box(f - 0.014, f + 0.014, r - 0.003, r + 0.003, base_t + 85)
    elif cls in _CARGO:
        poly([(L, 0), (0.4, 0.07), (0.3, 0.085), (-L, 0.085), (-L, -0.085), (0.3, -0.085), (0.4, -0.07)], base_t - 12)
        box(-0.46, 0.34, -0.065, 0.065, base_t + 6)                                           # main deck
        for f in (0.28, 0.12, -0.04, -0.2):                                                   # hatches with coamings
            box(f - 0.07, f + 0.07, -0.052, 0.052, base_t + 48)
            box(f - 0.062, f + 0.062, -0.044, 0.044, base_t - 18)
            box(f - 0.03, f + 0.03, -0.03, 0.03, base_t + (30 if f > 0.1 else 18))             # stacked boxes / tarps
        box(-0.46, -0.32, -0.07, 0.07, base_t + 72)                                           # bridge block aft
        box(-0.43, -0.37, -0.04, 0.04, base_t + 95)
        dot(-0.34, 0.0, 0.018, base_t + 100)                                                 # funnel
        for f in (0.2, -0.12):                                                                # deck cranes
            d.line([pt(f, 0.065), pt(f, 0.15 if False else 0.065)], fill=base_t + 80, width=1)
    else:                                                                                    # warship
        poly([(L, 0), (0.33, 0.055), (-0.05, 0.075), (-L, 0.07), (-L, -0.07), (-0.05, -0.075), (0.33, -0.055)], base_t - 14)
        poly([(0.45, 0), (0.32, 0.04), (-0.46, 0.056), (-0.46, -0.056), (0.32, -0.04)], base_t + 6)      # deck
        dot(0.30, 0, 0.026, base_t + 62)                                                      # main gun
        box(0.3, 0.42, -0.004, 0.004, base_t + 90)
        box(0.14, 0.22, -0.034, 0.034, base_t + 40)                                          # forward missile cells
        box(0.02, -0.2, -0.04, 0.04, base_t + 60)                                            # superstructure
        box(-0.02, -0.12, -0.026, 0.026, base_t + 84)                                        # bridge / upper works
        dot(-0.08, 0.0, 0.016, base_t + 98)                                                  # radar dome / funnel
        box(-0.3, -0.22, -0.03, 0.03, base_t + 34)                                           # funnel house
        box(-0.46, -0.34, -0.04, 0.04, base_t - 16)                                          # helideck
        dot(-0.4, 0.0, 0.02, base_t + 10)
        d.line([pt(-0.02, 0), pt(0.12, 0)], fill=base_t + 120, width=max(1, int(S)))          # mast


def _jittered(rng, p0, p1, steps, jitter):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        pts.append((p0[0] + (p1[0] - p0[0]) * t + rng.uniform(-jitter, jitter),
                    p0[1] + (p1[1] - p0[1]) * t + rng.uniform(-jitter, jitter)))
    return pts


def _composite_units(base, ulayer, S, rng, dust_on=True, shadow_off=(3.2, 4.2)):
    """Turn the flat unit drawing into something that reads like a photographed object: soft
    cast shadows, churned ground, relief lighting, camouflage-toned and textured surfaces,
    darkened edges and a touch of defocus, all composited onto the terrain."""
    w, h = base.size
    mask = ulayer.point(lambda v: 255 if v > 0 else 0)
    if not mask.getbbox():
        return base
    odd = lambda n: max(3, int(n) | 1)
    # churned ground / dust around vehicles
    dust = mask.filter(ImageFilter.MaxFilter(odd(5 * S))).filter(ImageFilter.GaussianBlur(3.2 * S))
    if not dust_on:
        dust = Image.new("L", (w, h), 0)
    base = Image.composite(ImageChops.multiply(base, Image.new("L", (w, h), 200)), base,
                           dust.point(lambda v: v * 2 // 5))
    # soft cast shadow, sun from the upper left
    sh = ImageChops.offset(mask, int(shadow_off[0] * S), int(shadow_off[1] * S)).filter(ImageFilter.GaussianBlur(1.5 * S))
    base = Image.composite(ImageChops.multiply(base, Image.new("L", (w, h), 120)), base,
                           sh.point(lambda v: v * 3 // 4))
    # relief lighting from the drawing's own tones
    soft = ulayer.filter(ImageFilter.GaussianBlur(0.6 * S))
    relief = soft.filter(ImageFilter.EMBOSS)
    body = ImageChops.add(soft.point(lambda v: 82 + v * 60 // 100),
                          relief.point(lambda v: max(0, min(255, 128 + (v - 128) * 22 // 10))),
                          scale=1, offset=-128)
    # weathered paint / dirt texture
    tex = Image.effect_noise((w, h), 30).filter(ImageFilter.GaussianBlur(0.5 * S))
    body = ImageChops.add(body, tex.point(lambda v: 128 + (v - 128) * 6 // 10), scale=1, offset=-128)
    # darker edges (ambient occlusion) so units sit in the picture
    inner = mask.filter(ImageFilter.MinFilter(odd(2 * S)))
    edge = ImageChops.subtract(mask, inner).filter(ImageFilter.GaussianBlur(0.5 * S))
    body = Image.composite(ImageChops.multiply(body, Image.new("L", (w, h), 165)), body, edge)
    body = body.filter(ImageFilter.GaussianBlur(0.55 * S))              # slight defocus
    alpha = mask.filter(ImageFilter.GaussianBlur(0.7 * S))
    return Image.composite(body, base, alpha)


def draw_recon(plan, centre, size, half_nm, photo_no, S=2, age_hours=0):
    """One stylised overhead photo centred on `centre` (a Group), `half_nm` nautical miles to each
    side. North is up. Positions come from the plan; unit shapes are symbolic."""
    w, h = int(size[0] * S), int(size[1] * S)
    seed = f"{plan.request.seed}|{centre.name}|{photo_no}"
    rng = random.Random(seed)
    naval = plan.request.mission_type.value == "naval"
    base = _sea_texture(rng, w, h) if naval else _terrain_texture(rng, w, h)
    d = ImageDraw.Draw(base)
    pxnm = (min(w, h) / 2) / half_nm                  # pixels per nautical mile
    rot = plan.rotation_deg
    cx0 = centre.distance_nm * math.sin(math.radians(centre.bearing_deg + rot))
    cy0 = centre.distance_nm * math.cos(math.radians(centre.bearing_deg + rot))

    def P(bearing, dist):
        x = dist * math.sin(math.radians(bearing + rot)) - cx0
        y = dist * math.cos(math.radians(bearing + rot)) - cy0
        return w / 2 + x * pxnm, h / 2 - y * pxnm

    # roads: two crossing near the middle, plus a track
    for a, b, wd in ([] if naval else
                     ((( -w * .1, h * (.3 + rng.random() * .4)), (w * 1.1, h * (.3 + rng.random() * .4)), 9),
                      ((w * (.3 + rng.random() * .4), -h * .1), (w * (.3 + rng.random() * .4), h * 1.1), 7),
                      ((0, h * .8), (w, h * .15), 4))):
        pts = _jittered(rng, a, b, 14, h * .018)
        d.line(pts, fill=60, width=int(wd * S / 2) + 3)
        d.line(pts, fill=205, width=int(wd * S / 2))

    ulayer = Image.new("L", (w, h), 0)
    ud = ImageDraw.Draw(ulayer)

    def building(x, y, bw, bh, ang, tone=165):
        c, s_ = math.cos(ang), math.sin(ang)
        pts = [(x + (dx * c - dy * s_), y + (dx * s_ + dy * c))
               for dx, dy in ((-bw, -bh), (bw, -bh), (bw, bh), (-bw, bh))]
        ud.polygon(pts, fill=tone)
        ud.line([(x - bw * c, y - bw * s_), (x + bw * c, y + bw * s_)], fill=tone - 40, width=max(1, S))  # roof ridge

    k_px = S * (2.7 if half_nm < 1 else 1.9)          # pixels per silhouette unit
    placed_pts = []

    def free_spot(x, y, spread, r2, sep):
        """A point near (x, y) that is not on top of a unit already drawn."""
        sp = max(spread, sep)
        for attempt in range(40):
            if attempt and attempt % 8 == 0:
                sp *= 1.35
            px_, py_ = x + r2.uniform(-sp, sp), y + r2.uniform(-sp, sp)
            if all((px_ - qx) ** 2 + (py_ - qy) ** 2 >= sep * sep for qx, qy in placed_pts):
                placed_pts.append((px_, py_))
                return px_, py_
        px_, py_ = x + r2.uniform(-sp, sp), y + r2.uniform(-sp, sp)
        placed_pts.append((px_, py_))
        return px_, py_

    def unit(cname, ux, uy, ang, tone=0):
        shape = silhouettes.classify(cname)
        silhouettes.draw_unit(ud, shape, ux, uy, ang, k_px, tone, S, flat_shadow=False)

    labels = []
    in_frame = lambda x, y: -20 <= x <= w + 20 and -20 <= y <= h + 20

    # static structures first (they sit under the vehicles)
    for g in ([] if naval else plan.statics):
        if g.placement != "relative" or g.side != plan.enemy_side:
            continue
        x, y = P(g.bearing_deg, g.distance_nm)
        if in_frame(x, y):
            r2 = random.Random(f"{seed}|{g.name}")
            building(x, y, r2.uniform(5, 11) * S, r2.uniform(4, 8) * S, r2.uniform(0, math.pi))

    # the target group is drawn last so it is never hidden under other units
    order = sorted((g for g in plan.groups if g.kind == "vehicle"), key=lambda g: g.tag == "target")
    for g in order:
        x, y = P(g.bearing_deg, g.distance_nm)
        if not in_frame(x, y):
            continue
        flat = [c for c, n in g.units for _ in range(n)]
        kind, offs = layouts.layout(g, flat)
        # slot sizes in pixels, scaled so silhouettes sit side by side without touching
        slot_f = {"park": 13.0, "column": 15.5, "line": 17.0, "site": 11.0, "skirmish": 9.0}[kind] * k_px
        slot_r = {"park": 8.6, "column": 0.0, "line": 10.0, "site": 11.0, "skirmish": 7.0}[kind] * k_px
        hd = math.radians(g.heading_deg)
        fx, fy = math.sin(hd), -math.cos(hd)            # forward on the page (north is up)
        rx, ry = math.cos(hd), math.sin(hd)           # to the right of the heading
        if kind == "site":
            rr = 3.1 * slot_f
            d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=235, width=max(2, 2 * S))   # berm
        tone = -18 if g.tag == "target" else 0
        for cname, (f, r_, hoff) in zip(flat, offs):
            ux = x + f * slot_f * fx + r_ * slot_r * rx
            uy = y + f * slot_f * fy + r_ * slot_r * ry
            unit(cname, ux, uy, math.radians(g.heading_deg + hoff) - math.pi / 2, tone)
        if kind == "site":
            labels.append((x, y - 3.1 * slot_f - 4 * S, g.name.replace("SAM - ", "")))
        elif g.tag == "aaa" and half_nm >= 1:
            labels.append((x, y - 12 * S - 3 * slot_f, "AAA"))
        elif g.tag == "target":
            labels.append((x, y - 18 * S - 2.2 * slot_f, "TARGET"))
        elif kind == "column" and half_nm >= 1 and g.tag == "route":
            labels.append((x, y - 14 * S, "CONVOY"))

    if ulayer.getbbox():
        base = _composite_units(base, ulayer, S, rng)
        d = ImageDraw.Draw(base)

    # ships: hulls go to their own layer and get the same photographic treatment as vehicles;
    # the wakes are painted into the water first so they sit under the hulls
    sl = Image.new("L", (w, h), 0)
    wl = Image.new("L", (w, h), 0)
    sd, wd = ImageDraw.Draw(sl), ImageDraw.Draw(wl)
    for g in sorted((g for g in plan.groups if g.kind == "ship"), key=lambda g: g.tag == "target"):
        x, y = P(g.bearing_deg, g.distance_nm)
        if not in_frame(x, y):
            continue
        cls = g.units[0][0]
        length = max(_SHIP_M.get(cls, 130) / 1852.0 * pxnm, 52 * S if half_nm >= 1 else 80 * S)
        draw_ship(sd, cls, x, y, g.heading_deg + rot, length, S, 235 if g.tag == "target" else 205, wake=wd)
        labels.append((x, y - length * 0.28 - 8 * S,
                       "TARGET" if g.tag == "target" else "ESCORT"))
    if sl.getbbox():
        foam = wl.filter(ImageFilter.GaussianBlur(1.6 * S)).point(lambda v: v * 22 // 100)
        base = ImageChops.add(base, foam)
        base = _composite_units(base, sl, S, rng, dust_on=False, shadow_off=(1.6, 2.2))
        d = ImageDraw.Draw(base)

    # film look: grain, vignette, tint
    grain = Image.effect_noise((w, h), 11 if naval else 18)
    base = ImageChops.add(ImageChops.multiply(base, Image.new("L", (w, h), 235)), grain, scale=3, offset=-40)
    vig = Image.radial_gradient("L").resize((w, h))
    base = ImageChops.multiply(base, ImageChops.invert(vig).point(lambda v: 150 + v * 105 // 255))
    base = ImageOps.autocontrast(base, cutoff=1)
    photo = ImageOps.colorize(base, (16, 14, 12), (236, 230, 212)).convert("RGB")

    dd = ImageDraw.Draw(photo)
    tick = int(6 * S)
    for k in range(0, int(w), int(40 * S)):
        dd.line([k, 0, k, tick], fill=(236, 230, 212), width=max(1, S // 2))
        dd.line([k, h - tick, k, h], fill=(236, 230, 212), width=max(1, S // 2))
    for k in range(0, int(h), int(40 * S)):
        dd.line([0, k, tick, k], fill=(236, 230, 212), width=max(1, S // 2))
        dd.line([w - tick, k, w, k], fill=(236, 230, 212), width=max(1, S // 2))
    # crosshair on the aim point
    gap, arm = int(8 * S), int(22 * S)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        dd.line([w / 2 + dx * gap, h / 2 + dy * gap, w / 2 + dx * arm, h / 2 + dy * arm],
                fill=(250, 240, 200), width=max(1, S))
    lab = font("sans_bold", int(9 * S))
    for lx, ly, text in labels:
        tw = dd.textlength(text, font=lab)
        dd.rectangle([lx - tw / 2 - 3 * S, ly - 6 * S, lx + tw / 2 + 3 * S, ly + 6 * S], fill=(20, 18, 16))
        dd.text((lx, ly), text, font=lab, fill=(245, 238, 215), anchor="mm")
    # north arrow and scale bar
    dd.polygon([(w - 18 * S, 26 * S), (w - 24 * S, 40 * S), (w - 12 * S, 40 * S)], fill=(245, 238, 215))
    dd.text((w - 18 * S, 46 * S), "N", font=lab, fill=(245, 238, 215), anchor="mm")
    bar_nm = 0.5 if half_nm >= 1 else 0.1
    bl = bar_nm * pxnm
    by = h - 16 * S
    dd.line([14 * S, by, 14 * S + bl, by], fill=(245, 238, 215), width=max(2, S))
    dd.text((14 * S, by - 9 * S), f"{bar_nm:g} NM", font=lab, fill=(245, 238, 215), anchor="lm")
    taken = plan.start_time - timedelta(hours=age_hours)
    cap = (f"PHOTO {photo_no}  -  {'WIDE' if half_nm >= 1 else 'CLOSE-UP'}  -  "
           f"{taken:%d %b %Y %H%M}L  -  {age_hours} HRS OLD" if age_hours else
           f"PHOTO {photo_no}  -  {'WIDE' if half_nm >= 1 else 'CLOSE-UP'}  -  {taken:%d %b %Y}")
    dd.rectangle([0, 0, dd.textlength(cap, font=lab) + 14 * S, 16 * S], fill=(20, 18, 16))
    dd.text((7 * S, 8 * S), cap, font=lab, fill=(245, 238, 215), anchor="lm")
    dd.rectangle([0, 0, w - 1, h - 1], outline=(20, 18, 16), width=max(2, S))
    return photo


# ---- pages ------------------------------------------------------------------------------------

def _style(plan, page):
    """(title, emblem, band colour) for the page header: the player's national air force, or
    for the United States the Air Force unless the aircraft is a carrier jet (F/A-18, F-14, A-4), or the Marine Corps for the AV-8B."""
    from . import emblems
    mine = plan.countries.get(plan.player_side) if plan.countries else None
    fl = page.flight if page.flight else plan.flights[0]
    if mine is None or mine.key == "usa":
        key = getattr(fl, "aircraft_key", "")
        return SERVICES["USMC" if key in MARINE_JETS else "USN" if key in NAVY_JETS else "USAF"]
    prof = emblems.profile(mine, plan.era.key)
    if prof is None:
        service = fl.service or "USAF"
        return SERVICES.get(service, SERVICES["USAF"])
    title, band, kind = prof
    return title, kind, band


def _header(c, plan, brief, page, compact=False):
    title, kind, band = _style(plan, page)
    h = 76 if compact else 128
    c.rect((0, 0, W, h), fill=band)
    c.rect((0, h, W, h + 4), fill=(190, 150, 60) if band[0] < 60 else (200, 170, 90))
    size = 56 if compact else 92
    badge = roundel(kind, size * c.S)
    c.img.paste(badge, (int(MARGIN * c.S), int(((h - size) / 2) * c.S)), badge)
    tx = MARGIN + size + 16
    c.text(tx, 14 if not compact else 10, title, "sans_bold", 24 if not compact else 18, (255, 255, 255))
    c.text(tx, 46 if not compact else 36, "MISSION BRIEFING  -  " + brief.code, "mono_bold",
           15 if not compact else 13, (232, 220, 170))
    if not compact:
        c.text(tx, 72, page.title.upper(), "sans_bold", 17, (255, 255, 255))
        c.text(tx, 98, f"{plan.era.label}   |   {plan.start_time:%d %b %Y}   |   {plan.map_display}",
               "mono", 13, (210, 210, 220))
    else:
        c.text(tx, 54, page.title.upper() + " (continued)", "sans_bold", 13, (255, 255, 255))
    return h + 4


def _facts(c, y, facts):
    cols = 3
    rows = math.ceil(len(facts) / cols)
    cell_w = (W - 2 * MARGIN) / cols
    h = rows * 38 + 8
    c.rect((MARGIN, y, W - MARGIN, y + h), outline=RULE, width=1)
    for i, (label, value) in enumerate(facts):
        r, k = divmod(i, cols)
        x = MARGIN + k * cell_w + 8
        yy = y + 6 + r * 38
        c.text(x, yy, label.upper(), "sans", 9.5, GREY)
        px_ = 14
        while c.width(value, "mono_bold", px_) > cell_w - 14 and px_ > 9:
            px_ -= 1
        c.text(x, yy + 13, value, "mono_bold", px_, INK)
    for k in range(1, cols):
        c.line((MARGIN + k * cell_w, y + 4, MARGIN + k * cell_w, y + h - 4), fill=RULE)
    return y + h + 8


def _route_table(c, x, y, w, page):
    header, rows = page.route_header, page.route
    show_hdg = "HDG" in header
    cols = [("#", 20), ("Waypoint", 98), ("Alt ft", 56), ("Kts", 34), ("ETA", 46)] + ([("HDG", 40)] if show_hdg else [])
    scale = w / sum(cw for _, cw in cols)
    c.rect((x, y, x + w, y + 20), fill=(60, 64, 76))
    xx = x
    for name, cw in cols:
        c.text(xx + 3, y + 3, name.upper(), "sans_bold", 10, (255, 255, 255))
        xx += cw * scale
    yy = y + 22
    for n, row in enumerate(rows):
        if n % 2 == 0:
            c.rect((x, yy - 1, x + w, yy + 19), fill=(236, 232, 218))
        xx = x
        for (name, cw), val in zip(cols, row):
            c.text(xx + 3, yy + 2, str(val), "mono_bold" if name == "Waypoint" else "mono", 13, INK)
            xx += cw * scale
        yy += 21
    c.rect((x, y, x + w, yy), outline=RULE, width=1)
    return yy


def _heading(c, x, y, text, w):
    c.text(x, y, text.upper(), "sans_bold", 12.5, (150, 30, 36) if True else INK)
    c.line((x, y + 17, x + w, y + 17), fill=RULE, width=1)


def _flow_items(c, sections, width, body=BODY):
    """Turn sections into drawable line items: ('h', text) / ('l', text, bullet) / ('gap', px)."""
    items = []
    for heading, lines in sections:
        if heading:
            items.append(("h", heading))
        for ln in lines:
            bullet = ln.startswith("- ")
            txt = ln[2:] if bullet else ln
            wrapped = wrap(c, txt, "mono", body, width - (16 if bullet else 0))
            for i, seg in enumerate(wrapped):
                items.append(("l", seg, bullet, bullet and i == 0))
            items.append(("gap", 2))
        items.append(("gap", 4))
    return items


def _place(c, items, y, y_max, width, start=0, body=BODY, line=LINE):
    """Draw items from `start` until the page is full; return (y, next_index)."""
    i = start
    while i < len(items):
        it = items[i]
        if it[0] == "h":
            if y + 22 + line > y_max:
                break
            _heading(c, MARGIN, y, it[1], width)
            y += 24
        elif it[0] == "l":
            if y + line > y_max:
                break
            _, seg, bullet, first = it
            x = MARGIN + (16 if bullet else 0)
            if first:
                c.text(MARGIN + 2, y, "•", "mono", body, (150, 30, 36))
            c.text(x, y, seg, "mono", body, INK)
            y += line
        else:
            y += it[1]
        i += 1
    return y, i


def _footer(c, n, total):
    c.line((MARGIN, H - 34, W - MARGIN, H - 34), fill=RULE)
    c.text(MARGIN, H - 28, "FICTIONAL EXERCISE FOR DCS WORLD  -  NOT AN OFFICIAL DOCUMENT", "sans", 9.5, GREY)
    c.text(W - MARGIN, H - 28, f"PAGE {n} / {total}", "mono_bold", 11, INK, anchor="ra")
    c.rect((6, 6, W - 6, H - 6), outline=RULE, width=1)


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# (body px, line height, flight map height, overview map height) - tried in order until a page fits
LEVELS = [(15, 19, 214, 176), (14, 17, 180, 140), (13, 16, 150, 110), (12, 14, 130, 90),
          (11, 13, 110, 70), (10, 12, 96, 56)]


def _draw_page(plan, brief, page, scale, level, allow_cont):
    body, line, fmap, omap = level
    width = W - 2 * MARGIN
    c = Canvas(scale)
    y = _header(c, plan, brief, page) + 10
    y = _facts(c, y, page.facts)
    if page.kind == "imagery":
        ph = int(fmap * 1.42)
        for k, half in enumerate((1.6, 0.32), 1):
            ph_img = draw_recon(plan, page.target, (width, ph), half, k, S=scale, age_hours=page.age_hours)
            c.img.paste(ph_img, (int(MARGIN * scale), int(y * scale)))
            y += ph + 10
    elif page.kind == "flight":
        map_w, map_h = 340, fmap
        m = draw_map(plan, (map_w, map_h), focus=page.flight, S=scale)
        c.img.paste(m, (int(MARGIN * scale), int(y * scale)))
        ty = _route_table(c, MARGIN + map_w + 12, y, width - map_w - 12, page)
        y = max(y + map_h, ty) + 10
    else:
        m = draw_map(plan, (width, omap), focus=None, S=scale, across=True)
        c.img.paste(m, (int(MARGIN * scale), int(y * scale)))
        y += omap + 12
    items = _flow_items(c, page.sections, width, body)
    y, idx = _place(c, items, y, H - 44, width, body=body, line=line)
    sheets = [c]
    while allow_cont and idx < len(items):            # overflow: continuation sheet
        c = Canvas(scale)
        y = _header(c, plan, brief, page, compact=True) + 14
        y, idx = _place(c, items, y, H - 44, width, start=idx, body=body, line=line)
        sheets.append(c)
    return sheets if idx >= len(items) else None


def render_pages(plan, brief, scale=2):
    """Draw every page, shrinking text until it fits one sheet; as a last resort it continues
    on an extra sheet. Returns [RenderedPage]."""
    sheets = []   # (stem, Canvas)
    for page in brief.pages:
        got = None
        for level in LEVELS:
            got = _draw_page(plan, brief, page, scale, level, allow_cont=False)
            if got:
                break
        if not got:
            got = _draw_page(plan, brief, page, scale, LEVELS[-1], allow_cont=True)
        for k, c in enumerate(got):
            sheets.append((f"{len(sheets) + 1:02d}_{_slug(page.tab)}" + ("-cont" if k else ""), c))
    total = len(sheets)
    out = []
    for n, (stem, c) in enumerate(sheets, 1):
        _footer(c, n, total)
        out.append(RenderedPage(stem, c.img))
    return out


# ---- outputs ----------------------------------------------------------------------------------

def save_pdf(pages, path):
    imgs = [p.image.convert("RGB") for p in pages]
    scale = imgs[0].width / W
    imgs[0].save(str(path), "PDF", save_all=True, append_images=imgs[1:],
                 resolution=96.0 * scale * 2, quality=92)


def kneeboard_files(pages):
    """[(file name, PNG bytes)] at DCS kneeboard size (768 x 1024)."""
    out = []
    for p in pages:
        buf = io.BytesIO()
        p.image.convert("RGB").resize((W, H), Image.LANCZOS).save(buf, "PNG", optimize=True)
        out.append((p.name + ".png", buf.getvalue()))
    return out
