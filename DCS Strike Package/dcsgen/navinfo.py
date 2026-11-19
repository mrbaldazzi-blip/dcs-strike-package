"""Position formats for the briefing: degrees/minutes, MGRS, and bearing/range."""

import math

_A = 6378137.0
_F = 1 / 298.257223563
_K0 = 0.9996
_BANDS = "CDEFGHJKLMNPQRSTUVWX"
_COLS = ("ABCDEFGH", "JKLMNPQR", "STUVWXYZ")
_ROWS = "ABCDEFGHJKLMNPQRSTUV"


def dm(lat, lng, decimals=3):
    """N42 11.382  E041 33.221 (degrees and decimal minutes)."""
    def part(v, pos, neg, width):
        hemi = pos if v >= 0 else neg
        v = abs(v)
        deg = int(v)
        minutes = round((v - deg) * 60, decimals)
        if minutes >= 60:
            deg, minutes = deg + 1, 0.0
        return f"{hemi}{deg:0{width}d}°{minutes:0{3 + decimals}.{decimals}f}'"
    return f"{part(lat, 'N', 'S', 2)} {part(lng, 'E', 'W', 3)}"


def mgrs(lat, lng, digits=5):
    """MGRS grid reference such as '38T LM 12345 67890' (WGS84)."""
    zone = int((lng + 180) // 6) + 1
    lon0 = math.radians((zone - 1) * 6 - 180 + 3)
    phi, lam = math.radians(lat), math.radians(lng) - lon0
    n = _F / (2 - _F)
    A = _A / (1 + n) * (1 + n ** 2 / 4 + n ** 4 / 64)
    alpha = (n / 2 - 2 * n ** 2 / 3 + 5 * n ** 3 / 16, 13 * n ** 2 / 48 - 3 * n ** 3 / 5,
             61 * n ** 3 / 240)
    c = 2 * math.sqrt(n) / (1 + n)
    t = math.sinh(math.atanh(math.sin(phi)) - c * math.atanh(c * math.sin(phi)))
    xi0 = math.atan2(t, math.cos(lam))
    eta0 = math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    xi = xi0 + sum(a * math.sin(2 * (j + 1) * xi0) * math.cosh(2 * (j + 1) * eta0)
                   for j, a in enumerate(alpha))
    eta = eta0 + sum(a * math.cos(2 * (j + 1) * xi0) * math.sinh(2 * (j + 1) * eta0)
                     for j, a in enumerate(alpha))
    easting = 500000 + _K0 * A * eta
    northing = _K0 * A * xi + (10000000 if lat < 0 else 0)
    band = _BANDS[max(0, min(19, int((lat + 80) // 8)))]
    col = _COLS[(zone - 1) % 3][int(easting // 100000) - 1]
    row = _ROWS[(int(northing // 100000) + (5 if zone % 2 == 0 else 0)) % 20]
    e, nn = int(easting % 100000), int(northing % 100000)
    scale = 10 ** (5 - digits)
    return f"{zone}{band} {col}{row} {e // scale:0{digits}d} {nn // scale:0{digits}d}"


def point_latlng(point):
    """(lat, lng) of a pydcs Point; `latlng` is a method in pydcs 1.0 and a property in other versions."""
    v = point.latlng
    if callable(v):
        v = v()
    return v.lat, v.lng
