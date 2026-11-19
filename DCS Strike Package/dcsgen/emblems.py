"""National air-force insignia and header titles for the briefing pages.

Each emblem is a simplified drawing of the country's real roundel or air-force marking,
made from basic shapes (no copied artwork) so it reads as the right nation at header size.
"""

import math

from PIL import Image, ImageDraw

WHITE = (250, 248, 240)
RED = (196, 28, 34)
BLUE = (28, 62, 140)
DKBLUE = (18, 36, 92)
GREEN = (24, 120, 60)
BLACK = (24, 24, 26)
YELLOW = (236, 190, 40)
ORANGE = (236, 118, 24)

# key -> (header title, band colour, emblem name)
FORCES = {
    "usa": ("UNITED STATES AIR FORCE", (24, 44, 96), "us"),
    "uk": ("ROYAL AIR FORCE", (20, 40, 90), "uk"),
    "france": ("ARMEE DE L'AIR", (24, 44, 110), "france"),
    "germany": ("LUFTWAFFE", (40, 42, 46), "german"),
    "canada": ("ROYAL CANADIAN AIR FORCE", (150, 24, 30), "canada"),
    "australia": ("ROYAL AUSTRALIAN AIR FORCE", (20, 44, 100), "australia"),
    "netherlands": ("ROYAL NETHERLANDS AIR FORCE", (170, 84, 20), "netherlands"),
    "belgium": ("BELGIAN AIR COMPONENT", (40, 40, 44), "belgium"),
    "norway": ("ROYAL NORWEGIAN AIR FORCE", (24, 40, 100), "norway"),
    "denmark": ("ROYAL DANISH AIR FORCE", (140, 24, 34), "denmark"),
    "italy": ("AERONAUTICA MILITARE", (26, 80, 56), "italy"),
    "spain": ("EJERCITO DEL AIRE", (130, 30, 34), "spain"),
    "turkey": ("TURKISH AIR FORCE", (140, 24, 34), "turkey"),
    "israel": ("ISRAELI AIR FORCE", (24, 56, 130), "israel"),
    "south_korea": ("REPUBLIC OF KOREA AIR FORCE", (24, 44, 100), "south_korea"),
    "japan": ("JAPAN AIR SELF-DEFENSE FORCE", (30, 44, 90), "japan"),
    "poland": ("POLISH AIR FORCE", (120, 26, 34), "poland"),
    "russia": ("RUSSIAN AEROSPACE FORCES", (118, 24, 28), "russian"),
    "china": ("PEOPLE'S LIBERATION ARMY AIR FORCE", (118, 24, 28), "china"),
    "north_korea": ("KOREAN PEOPLE'S ARMY AIR FORCE", (110, 26, 34), "north_korea"),
    "cuba": ("CUBAN REVOLUTIONARY AIR FORCE", (24, 48, 110), "cuba"),
    "egypt": ("EGYPTIAN AIR FORCE", (110, 28, 30), "egypt"),
    "syria": ("SYRIAN ARAB AIR FORCE", (96, 28, 30), "syria"),
    "iraq": ("IRAQI AIR FORCE", (100, 28, 30), "iraq"),
    "libya": ("LIBYAN ARAB AIR FORCE", (24, 84, 50), "libya"),
    "iran": ("ISLAMIC REPUBLIC OF IRAN AIR FORCE", (24, 84, 50), "iran"),
    "vietnam": ("VIETNAM PEOPLE'S AIR FORCE", (120, 26, 30), "vietnam"),
    "yugoslavia": ("YUGOSLAV AIR FORCE", (24, 48, 110), "yugoslavia"),
    "belarus": ("BELARUSIAN AIR FORCE", (120, 28, 34), "belarus"),
}
SERBIA = ("SERBIAN AIR FORCE", (24, 48, 110), "serbia")


def profile(choice, era_key):
    """-> (title, band colour, emblem name) for a countries.CountryChoice."""
    if choice.key == "yugoslavia" and era_key in ("nineties", "modern"):
        return SERBIA
    if choice.key == "russia" and era_key in ("early_cold_war", "mid_cold_war", "late_cold_war"):
        return ("SOVIET AIR FORCES", (118, 24, 28), "soviet")
    if choice.key == "germany" and era_key in ("early_cold_war", "mid_cold_war", "late_cold_war"):
        return ("LUFTWAFFE (WEST GERMANY)", (40, 42, 46), "german")
    return FORCES.get(choice.key)


# ---- drawing helpers (all coordinates in pixels of the 4x canvas) -----------------------------

def _disc(d, c, r, fill, outline=None, width=0):
    d.ellipse([c - r, c - r, c + r, c + r], fill=fill, outline=outline, width=width)


def _rings(d, c, r, colours):
    """Concentric discs from the outside in; each colour takes an equal share of the radius."""
    n = len(colours)
    for i, col in enumerate(colours):
        _disc(d, c, r * (1 - i / n), col)


def _star(c, r, points=5, inner=0.382, rot=-90.0, cy=None):
    cy = c if cy is None else cy
    pts = []
    for i in range(points * 2):
        ang = math.radians(rot + i * 180 / points)
        rad = r if i % 2 == 0 else r * inner
        pts.append((c + rad * math.cos(ang), cy + rad * math.sin(ang)))
    return pts


def _maple(c, r):
    # a simplified eleven-point maple leaf, unit coordinates around the centre
    pts = [(0, -1), (0.2, -0.6), (0.5, -0.7), (0.42, -0.25), (0.85, -0.4), (0.72, -0.05),
           (1.0, 0.1), (0.5, 0.45), (0.58, 0.75), (0.12, 0.62), (0.06, 1.0), (-0.06, 1.0),
           (-0.12, 0.62), (-0.58, 0.75), (-0.5, 0.45), (-1.0, 0.1), (-0.72, -0.05),
           (-0.85, -0.4), (-0.42, -0.25), (-0.5, -0.7), (-0.2, -0.6)]
    return [(c + x * r, c + y * r) for x, y in pts]


def _hexagram(c, r, w):
    out = []
    for rot in (-90, 90):
        out.append([(c + r * math.cos(math.radians(rot + k * 120)),
                     c + r * math.sin(math.radians(rot + k * 120))) for k in range(3)])
    return out


def _crescent(d, c, r, fill, bg, dx=0.28):
    _disc(d, c, r, fill)
    _disc_xy(d, c + r * dx, c, r * 0.8, bg)


def _disc_xy(d, x, y, r, fill):
    d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def _yinyang(d, c, r, top, bottom):
    _disc(d, c, r, bottom)
    d.pieslice([c - r, c - r, c + r, c + r], 180, 360, fill=top)
    _disc_xy(d, c - r / 2, c, r / 2, top)
    _disc_xy(d, c + r / 2, c, r / 2, bottom)


def draw(kind, n):
    """RGBA emblem of size n x n (n is the 4x working size), or None for an unknown kind."""
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c, r = n / 2, n / 2 - 4
    k = kind
    if k == "uk":
        _rings(d, c, r, [BLUE, WHITE, RED])
    elif k == "france":
        _rings(d, c, r, [RED, WHITE, BLUE])
    elif k == "canada":
        _disc(d, c, r, WHITE, outline=RED, width=n // 18)
        d.polygon(_maple(c, r * 0.68), fill=RED)
    elif k == "australia":
        _rings(d, c, r, [BLUE, WHITE, RED])
    elif k == "netherlands":
        _disc(d, c, r, ORANGE if False else WHITE, outline=ORANGE, width=n // 20)
        d.polygon([(c, c - r * .62), (c + r * .6, c + r * .38), (c - r * .6, c + r * .38)], fill=ORANGE)
    elif k == "belgium":
        _rings(d, c, r, [BLACK, YELLOW, RED])
    elif k == "norway":
        _rings(d, c, r, [BLUE, WHITE, RED, WHITE])
    elif k == "denmark":
        _rings(d, c, r, [RED, WHITE, RED])
    elif k == "italy":
        _rings(d, c, r, [GREEN, WHITE, RED])
    elif k == "spain":
        _rings(d, c, r, [RED, YELLOW, RED])
    elif k == "turkey":
        _disc(d, c, r, RED, outline=WHITE, width=n // 24)
        _crescent(d, c - r * 0.1, r * 0.5, WHITE, RED)
        d.polygon(_star(c + r * 0.28, r * 0.22, cy=c), fill=WHITE)
    elif k == "israel":
        _disc(d, c, r, WHITE, outline=BLUE, width=n // 30)
        for tri in _hexagram(c, r * 0.58, 0):
            d.polygon(tri, outline=BLUE, width=max(2, n // 28))
    elif k == "south_korea":
        _disc(d, c, r, WHITE, outline=(190, 190, 190), width=n // 60)
        _yinyang(d, c, r * 0.6, RED, BLUE)
    elif k == "japan":
        _disc(d, c, r, WHITE, outline=(200, 200, 200), width=n // 60)
        _disc(d, c, r * 0.5, RED)
    elif k == "poland":
        s = r * 0.92
        for i in range(2):
            for j in range(2):
                d.rectangle([c - s + i * s, c - s + j * s, c + i * s, c + j * s],
                            fill=RED if (i + j) % 2 == 0 else WHITE, outline=(120, 120, 120))
    elif k == "china":
        _disc(d, c, r, BLUE)
        _disc(d, c, r * 0.82, WHITE)
        d.polygon(_star(c, r * 0.78), fill=RED, outline=YELLOW)
    elif k == "north_korea":
        _disc(d, c, r, BLUE)
        _disc(d, c, r * 0.84, WHITE)
        d.polygon(_star(c, r * 0.7), fill=RED)
    elif k == "cuba":
        _disc(d, c, r, BLUE)
        _disc(d, c, r * 0.82, WHITE)
        d.polygon([(c - r * .62, c - r * .5), (c - r * .62, c + r * .5), (c + r * .1, c)], fill=RED)
        d.polygon(_star(c - r * .32, r * .16, cy=c), fill=WHITE)
    elif k == "egypt":
        _rings(d, c, r, [RED, WHITE, BLACK])
    elif k == "syria":
        _rings(d, c, r, [RED, WHITE, BLACK])
        for sx in (-1, 1):
            d.polygon(_star(c + sx * r * .2, r * .16, cy=c), fill=GREEN)
    elif k == "iraq":
        _rings(d, c, r, [RED, WHITE, BLACK])
        d.rectangle([c - r * .3, c - r * .06, c + r * .3, c + r * .06], fill=GREEN)
    elif k == "libya":
        _disc(d, c, r, GREEN, outline=WHITE, width=n // 24)
        _crescent(d, c - r * 0.05, r * 0.4, WHITE, GREEN)
    elif k == "iran":
        _rings(d, c, r, [GREEN, WHITE, RED])
    elif k == "vietnam":
        _disc(d, c, r, RED, outline=YELLOW, width=n // 26)
        d.polygon(_star(c, r * 0.62), fill=YELLOW)
    elif k == "yugoslavia":
        _rings(d, c, r, [BLUE, WHITE, RED])
        d.polygon(_star(c, r * 0.34), fill=YELLOW)
    elif k == "serbia":
        _rings(d, c, r, [RED, BLUE, WHITE])
    elif k == "belarus":
        _rings(d, c, r, [RED, WHITE, GREEN])
    else:
        return None
    return im
