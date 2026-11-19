"""Top-down unit silhouettes for the stylised target photos.

Each unit is drawn from its DCS class name as a recognisable plan-view shape (tank with turret and
gun, tracked or wheeled SAM launcher with its missiles, dish radars, trucks, artillery...). These are
simple original drawings, not the game's 3D models. Shapes use local coordinates in "units":
x points forward, y to the right, and the unit is roughly 10 units long.
"""

import math
import re

# ---- classification ---------------------------------------------------------------------------

_RULES = [
    (r"ewr|fps_117|rls_19j6|gci_station", "ewr"),
    # radars, search and tracking (before the launchers that share a family name)
    (r"p14_sr|p_19_s_125_sr|_sr$|_sr_|silkworm_sr|dog_ear|hawk_sr|nasams_radar|patriot_str|rapier.*radar", "radar_search"),
    (r"_tr$|_tr_|snr_|son_9|fire_control|kub_1s91|hawk_tr|hawk_pcp|roland_radar|rapier.*tracker|patriot_ecs|patriot_epp|patriot_amg|iristslm_str|hq_7_str|_str$", "radar_track"),
    (r"_cp$|_cp_|_cc_|_cc$|command_post|m30_cc|hawk_cwar|patriot_cp|iristslm_cp", "command"),
    # air-defence launchers
    (r"s_75|sa_2|rd_75|volhov", "sam_sa2"),
    (r"s_200|x_5p73|sa_3", "sam_sa3"),
    (r"kub_2p25", "sam_sa6"),
    (r"osa_|strela_1_|sa_8", "sam_sa8"),
    (r"buk_ln|sa_11", "sam_sa11"),
    (r"s_300ps_5p85|sa_10", "sam_sa10"),
    (r"tor_|torm2|pantsir|strela_10|sa_13", "sam_tor"),
    (r"patriot_ln", "sam_patriot"),
    (r"hawk_ln|^hawk$", "sam_hawk"),
    (r"nasams_ln", "sam_nasams"),
    (r"rapier_fsa_launcher", "sam_rapier"),
    (r"roland_ads", "sam_roland"),
    (r"chaparral|linebacker|avenger|iristslm_ln|hq_7_ln|hy_launcher|chap_m1083", "sam_avenger"),
    (r"igla|stinger|manpad|soldier|infantry|paratrooper|jtac", "man"),
    # anti-aircraft guns
    (r"gepard", "gepard"),
    (r"tunguska", "tunguska"),
    (r"shilka|zsu_57|zsu_23|ural_375_zu|c_ram|phalanx", "shilka"),
    (r"zu_23|s_60|bofors|flak|vulcan|m1_37|qf_37|type_.*aa|m45_quad|type_94_25|_aa$", "aaa_towed"),
    # ground forces
    (r"^t_|^m_1_|m1a2|leopard|leclerc|challenger|merkava|ztz96|chap_t|^m_60|t62|tiger|panther|^pz_|centaur|chieftain|churchill|cromwell|sherman|type_89|type_98_ke|stug|jagd|elefant|pt_76|tetrarch|tacr|type_59$|^t_34", "tank"),
    (r"^bmp|^bmd|m_2_bradley|marder|mcv_80|lav_25|zbd04|chap_bmp|chap_fv101|chap_fv107|aav7|btr_d", "ifv"),
    (r"^btr|m_113|mtlb|stryker|brdm|vab_|maxxpro|hummer|tigr|uaz|cobra|m1043|m1045|m1126|chap_matv|m2a1_half|sd_kfz|kubelwagen|land_rover|horch|willys|m8_grey|daimler|chap_m1130|chap_m1296|tpz", "apc"),
    (r"sau_|m_109|plz05|t155|dana|wespe|m12_gmc|m10_gmc|chap_tos|lefh|m2a1_105|l118|gd_20|2b11|type_98_so|chap_titan", "spg"),
    (r"smerch|uragan|grad|mlrs|scud|chap_m142|chap_9k720|v1_launcher", "mlrs"),
    (r"atz|atmz|m978|tz_22|tfft|tanker|b600|zil_135", "tanker"),
]
_COMPILED = [(re.compile(p), shape) for p, shape in _RULES]


def classify(name):
    """Return a shape key for a DCS vehicle class name."""
    n = str(name).lower()
    for rx, shape in _COMPILED:
        if rx.search(n):
            return shape
    return "truck"


# ---- drawing ----------------------------------------------------------------------------------

def _xf(pts, x, y, ang, k):
    c, s = math.cos(ang), math.sin(ang)
    return [(x + (px * c - py * s) * k, y + (px * s + py * c) * k) for px, py in pts]


def _box(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _ellipse(cx, cy, rx, ry, n=14):
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n))
            for i in range(n)]


DARK, MID, LIGHT, PALE, SHADOW = 34, 78, 130, 215, 18


def draw_unit(d, shape, x, y, ang, k=1.0, tone=0, S=1, flat_shadow=True):
    """Draw one unit silhouette on an 'L' (greyscale) ImageDraw `d` at (x, y) facing `ang` radians
    (0 = right). `k` scales it (pixels per unit), `tone` darkens/lightens the whole unit."""
    def poly(pts, fill, outline=None, off=0.0):
        p = _xf(pts, x + off * k * 0.5, y + off * k * 0.5, ang, k)
        d.polygon(p, fill=max(1, min(255, fill + tone)), outline=outline)

    def shadow(pts):
        if not flat_shadow:
            return
        d.polygon(_xf(pts, x + 1.2 * k * 0.5, y + 1.6 * k * 0.5, ang, k), fill=SHADOW)

    def line(a, b, fill, w=1.0):
        pa, pb = _xf([a, b], x, y, ang, k)
        d.line([pa, pb], fill=max(1, min(255, fill + tone)), width=max(1, int(w * k * 0.35 * S ** 0)))

    def missile(cx, cy, length=9, rise=0.0):
        pts = [(cx - length / 2, cy - 0.7), (cx + length / 2 - 1.5, cy - 0.7), (cx + length / 2, cy),
               (cx + length / 2 - 1.5, cy + 0.7), (cx - length / 2, cy + 0.7)]
        poly(pts, PALE, outline=60)

    def tracks(l0, l1, wid, hw):
        for sgn in (-1, 1):
            poly(_box(l0, sgn * hw - wid / 2, l1, sgn * hw + wid / 2), 28, outline=90)

    if shape == "tank":
        body = _box(-5, -3.2, 5, 3.2)
        shadow(body)
        tracks(-5.3, 5.3, 1.9, 3.0)
        poly([(-5, -2.4), (4.5, -2.4), (5.2, 0), (4.5, 2.4), (-5, 2.4)], MID, outline=150)
        poly(_ellipse(-0.6, 0, 2.7, 2.3, 10), LIGHT, outline=190)
        line((0.5, 0), (8.3, 0), 190, 2.2)
        poly(_box(-1.9, -0.6, -0.9, 0.6), 60)
    elif shape in ("ifv", "apc"):
        body = _box(-5, -2.8, 5, 2.8)
        shadow(body)
        tracks(-5, 5, 1.5, 2.5) if shape == "ifv" else None
        poly([(-5, -2.4), (4, -2.4), (5, -1.2), (5, 1.2), (4, 2.4), (-5, 2.4)], MID, outline=150)
        if shape == "ifv":
            poly(_ellipse(0.5, 0, 1.9, 1.7, 9), LIGHT, outline=190)
            line((1, 0), (5.8, 0), 190, 1.6)
        else:
            poly(_ellipse(-0.5, 0, 1.2, 1.2, 8), 40, outline=170)
            for wx in (-3.4, -1.2, 1.2, 3.4):
                poly(_box(wx - 0.6, -3.3, wx + 0.6, -2.6), 25)
                poly(_box(wx - 0.6, 2.6, wx + 0.6, 3.3), 25)
    elif shape == "spg":
        shadow(_box(-5, -3, 5, 3))
        tracks(-5.3, 5.3, 1.8, 3.0)
        poly([(-5, -2.3), (5, -2.3), (5, 2.3), (-5, 2.3)], MID, outline=150)
        poly(_box(-4, -2.6, 1.5, 2.6), LIGHT, outline=190)
        line((1.0, 0), (10.5, 0), 195, 2.0)
    elif shape == "mlrs":
        shadow(_box(-6, -2.5, 6, 2.5))
        poly(_box(2, -2.4, 6, 2.4), 70, outline=150)
        poly(_box(-6, -2.5, 2, 2.5), 90, outline=150)
        for i in range(-2, 3):
            line((-5, i * 0.9), (1, i * 0.9), 200, 1.2)
    elif shape in ("truck", "tanker", "command"):
        shadow(_box(-6, -2.3, 6, 2.3))
        poly(_box(2.5, -2.2, 6, 2.2), 100, outline=170)
        poly(_box(-6, -2.3, 2.2, 2.3), 70 if shape != "tanker" else 110, outline=150)
        if shape == "tanker":
            poly(_ellipse(-1.9, 0, 3.8, 1.8, 12), 175, outline=60)
        elif shape == "command":
            line((-3, 0), (-3, -4), 220, 1.0)
            poly(_box(-5.5, -1.8, 0, 1.8), 120, outline=190)
        for wx in (-4.2, 0, 4.2):
            poly(_box(wx - 0.8, -2.8, wx + 0.8, -2.2), 22)
            poly(_box(wx - 0.8, 2.2, wx + 0.8, 2.8), 22)
    elif shape in ("shilka", "gepard", "tunguska"):
        shadow(_box(-5.2, -3, 5.2, 3))
        tracks(-5.3, 5.3, 1.8, 3.0)
        poly([(-5, -2.4), (5, -2.4), (5, 2.4), (-5, 2.4)], MID, outline=150)
        poly(_box(-3.2, -2.9, 2.2, 2.9), LIGHT, outline=190)
        if shape == "shilka":
            for yy in (-1.8, -0.6, 0.6, 1.8):
                line((1.5, yy), (7.2, yy), 200, 1.0)
            poly(_ellipse(-4.6, 0, 1.2, 1.6, 8), 210, outline=90)
        elif shape == "gepard":
            for yy in (-2.3, 2.3):
                line((1.5, yy), (6.8, yy), 200, 1.4)
            poly(_ellipse(-2.3, 0, 1.4, 1.5, 8), 215, outline=90)
            poly(_ellipse(0.4, 0, 1.0, 1.1, 8), 180, outline=90)
        else:
            for yy in (-1.2, 1.2):
                line((1.5, yy), (7.4, yy), 200, 1.4)
            for yy in (-2.9, 2.9):
                for xx in (-2.5, -1.0, 0.5, 2.0):
                    missile(xx, yy * 0.97, 2.8)
    elif shape == "aaa_towed":
        shadow(_box(-4, -2, 4, 2))
        poly(_ellipse(0, 0, 2.2, 2.2, 10), 70, outline=170)
        poly(_box(-4.5, -0.5, -2, 0.5), 60)
        for yy in (-0.7, 0.7):
            line((0.5, yy), (6.5, yy), 205, 1.2)
        poly(_box(-1.2, -2.6, -0.2, 2.6), 28)
    elif shape.startswith("sam_") or shape in ("patriot", "hawk"):
        fam = shape[4:]
        _sam(d, fam, x, y, ang, k, tone, poly, shadow, line, missile, tracks)
    elif shape == "man":
        poly(_ellipse(0, 0, 1.3, 1.9, 8), 120, outline=200)
    elif shape in ("radar_search", "radar_track"):
        shadow(_box(-4, -3, 4, 3))
        poly(_box(-4.5, -2.2, 3, 2.2), 70, outline=150)
        if shape == "radar_search":
            poly([(-0.5, -6.5), (0.5, -6.5), (1.3, 0), (0.5, 6.5), (-0.5, 6.5), (0.3, 0)], 200, outline=60)
            line((0, -6.5), (0, 6.5), 90, 1.0)
        else:
            poly(_ellipse(-0.5, 0, 3.4, 3.4, 14), 215, outline=60)
            poly(_ellipse(-0.5, 0, 1.2, 1.2, 8), 70)
            line((-0.5, 0), (3.5, 0), 40, 1.0)
    elif shape == "ewr":
        shadow(_box(-5, -5, 5, 5))
        poly(_box(-1.2, -9, 1.2, 9), 205, outline=60)
        for i in range(-8, 9, 2):
            line((-1.2, i), (1.2, i), 80, 1.0)
        poly(_box(-5, -2, -1.4, 2), 80, outline=150)
    else:
        poly(_box(-4, -2, 4, 2), 70, outline=150)


def _sam(d, fam, x, y, ang, k, tone, poly, shadow, line, missile, tracks):
    """Launchers: a chassis plus the right number and layout of missiles."""
    tracked = fam in ("sa6", "sa11", "tor", "tunguska")
    if fam == "sa2":
        shadow(_box(-5, -4, 5, 4))
        poly(_box(-3, -3, 3, 3), 60, outline=150)
        poly(_ellipse(0, 0, 2.4, 2.4, 10), 100, outline=170)
        missile(0.8, 0, 11)
        return
    if fam == "sa3":
        shadow(_box(-5, -4, 5, 4))
        poly(_box(-3.2, -3.2, 3.2, 3.2), 60, outline=150)
        for yy in (-1.6, 1.6):
            missile(1.2, yy, 8)
            missile(1.2, yy + (0.9 if yy > 0 else -0.9), 8) if False else None
        poly(_box(-3, -1.0, 0, 1.0), 110)
        return
    if fam == "hawk":
        shadow(_box(-4, -4.5, 4, 4.5))
        poly(_box(-3, -3, 3, 3), 60, outline=150)
        for ang_off in (-0.5, 0, 0.5):
            c, s = math.cos(ang_off), math.sin(ang_off)
            pa = (-2 * c, -2 * s)
            pb = (6.5 * c, 6.5 * s)
            line(pa, pb, 215, 2.2)
        return
    if fam == "patriot":
        shadow(_box(-7, -3, 7, 3))
        poly(_box(-7, -2.5, 6, 2.5), 70, outline=150)
        for yy in (-1.5, -0.5, 0.5, 1.5):
            poly(_box(-6, yy - 0.45, 6.5, yy + 0.45), 205, outline=60)
        return
    if fam == "nasams":
        shadow(_box(-5, -3, 5, 3))
        poly(_box(-5, -2.5, 5, 2.5), 70, outline=150)
        for yy in (-1.3, 0, 1.3):
            poly(_box(-4.5, yy - 0.5, 5.5, yy + 0.5), 205, outline=60)
        return
    # tracked / wheeled TELs
    shadow(_box(-5.5, -3, 5.5, 3))
    if tracked:
        tracks(-5.5, 5.5, 1.8, 3.0)
        poly(_box(-5, -2.3, 5, 2.3), 70, outline=150)
    else:
        poly(_box(-6, -2.4, 6, 2.4), 70, outline=150)
        poly(_box(3.5, -2.3, 6, 2.3), 105, outline=170)
        for wx in (-4.5, -1.5, 1.5):
            poly(_box(wx - 0.8, -3.0, wx + 0.8, -2.3), 22)
            poly(_box(wx - 0.8, 2.3, wx + 0.8, 3.0), 22)
    layouts = {
        "sa6": [(-0.3, -1.4), (-0.3, 0), (-0.3, 1.4)],
        "sa11": [(0, -1.5), (0, -0.5), (0, 0.5), (0, 1.5)],
        "sa10": [(-0.5, -1.4), (-0.5, -0.45), (-0.5, 0.45), (-0.5, 1.4)],
        "tor": [(-0.8, -1.2), (-0.8, -0.4), (-0.8, 0.4), (-0.8, 1.2)],
        "sa8": [(-1.2, -1.5), (-1.2, 1.5), (0.6, -1.5), (0.6, 1.5)],
        "roland": [(-0.5, -1.2), (-0.5, 1.2)],
        "rapier": [(-0.5, -1.4), (-0.5, -0.5), (-0.5, 0.5), (-0.5, 1.4)],
        "avenger": [(-0.5, -1.4), (-0.5, 1.4)],
    }
    for cx, cy in layouts.get(fam, [(0, -1.0), (0, 1.0)]):
        missile(cx, cy, 8.6 if fam in ("sa6", "sa11", "sa10") else 5.6)
    if fam in ("tor", "sa8"):
        poly(_ellipse(-3.4, 0, 1.5, 1.5, 10), 215, outline=60)
