"""Real coastlines, so ground units and statics are never placed in the sea.

pydcs 1.0 cannot tell land from water. The DCS maps are real places, so we use the public
Natural Earth 1:10m land polygons: `dcsgen fetch-coast` (fetch_coast.bat) downloads them once and
keeps only the parts that fall on the maps we support, as a small file in dcsgen/data/.
After that, is_land() is a plain point-in-polygon test on latitude and longitude.
"""

import json
import tempfile
import urllib.request
from pathlib import Path

URLS = ["https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_land.geojson",
        "https://github.com/nvkelso/natural-earth-vector/raw/master/geojson/ne_10m_land.geojson"]

# (south, west, north, east) generous boxes around each map with a coast
BOXES = {
    "caucasus": (39.0, 27.0, 47.5, 47.5),
    "persian_gulf": (22.0, 47.0, 31.0, 61.0),
    "syria": (31.0, 31.0, 38.5, 43.0),
    "marianas": (11.0, 139.0, 21.0, 148.0),
    "sinai": (26.5, 28.0, 33.5, 37.0),
    "kola": (66.0, 15.0, 72.5, 42.0),
    "south_atlantic": (-56.0, -66.0, -49.0, -55.0),
}

DATA = Path(__file__).parent / "data" / "coast.json"
_cache = {}


# ---- building the file (run once, needs internet) ---------------------------

def _clip_edge(poly, inside, cross):
    out = []
    for i, cur in enumerate(poly):
        prev = poly[i - 1]
        if inside(cur):
            if not inside(prev):
                out.append(cross(prev, cur))
            out.append(cur)
        elif inside(prev):
            out.append(cross(prev, cur))
    return out


def clip_ring(ring, box):
    """Sutherland-Hodgman clip of a ring of (lng, lat) points to (south, west, north, east)."""
    s, w, n, e = box
    poly = list(ring)

    def xcut(x):
        return lambda a, b: (x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))

    def ycut(y):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y)

    for inside, cross in ((lambda p: p[0] >= w, xcut(w)), (lambda p: p[0] <= e, xcut(e)),
                          (lambda p: p[1] >= s, ycut(s)), (lambda p: p[1] <= n, ycut(n))):
        if not poly:
            break
        poly = _clip_edge(poly, inside, cross)
    return poly


def _rings(geojson):
    for feat in geojson.get("features", []):
        g = feat.get("geometry") or {}
        polys = g["coordinates"] if g.get("type") == "MultiPolygon" else (
            [g["coordinates"]] if g.get("type") == "Polygon" else [])
        for poly in polys:
            for ring in poly:
                yield ring


def build(geojson, boxes=BOXES):
    """{map_key: [ring, ...]} from a parsed Natural Earth land GeoJSON."""
    out = {k: [] for k in boxes}
    for ring in _rings(geojson):
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        for key, box in boxes.items():
            s, w, n, e = box
            if max(xs) < w or min(xs) > e or max(ys) < s or min(ys) > n:
                continue
            clipped = clip_ring([(p[0], p[1]) for p in ring], box)
            if len(clipped) >= 3:
                out[key].append([[round(x, 4), round(y, 4)] for x, y in clipped])
    return out


def fetch(path=DATA, say=print):
    data = None
    for url in URLS:
        try:
            say(f"Downloading {url} ...")
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "land.geojson"
                urllib.request.urlretrieve(url, dest)
                data = json.loads(dest.read_text(encoding="utf-8"))
            break
        except Exception as e:  # noqa: BLE001
            say(f"  failed: {type(e).__name__}: {e}")
    if data is None:
        raise RuntimeError("Could not download the coastline data. Check your internet connection.")
    rings = build(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rings, separators=(",", ":")), encoding="utf-8")
    pts = {k: sum(len(r) for r in v) for k, v in rings.items()}
    say(f"Wrote {path}  ({path.stat().st_size // 1024} KB; points per map: {pts})")
    return pts


# ---- using it ----------------------------------------------------------------

def _load(path=DATA):
    key = str(path)
    if key not in _cache:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        prepared = {}
        for k, rings in raw.items():
            items = []
            for r in rings:
                xs = [p[0] for p in r]
                ys = [p[1] for p in r]
                items.append((min(xs), min(ys), max(xs), max(ys), r))
            prepared[k] = items
        _cache[key] = prepared
    return _cache[key]


def has(map_key, path=DATA):
    return bool(_load(path).get(map_key))


def is_land(map_key, lat, lng, path=DATA):
    """True on land, False on water, None when there is no coastline data for this map."""
    rings = _load(path).get(map_key)
    if not rings:
        return None
    inside = False
    for x0, y0, x1, y1, r in rings:
        if lng < x0 or lng > x1 or lat < y0 or lat > y1:
            continue
        j = len(r) - 1
        for i in range(len(r)):
            xi, yi = r[i]
            xj, yj = r[j]
            if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
    return inside
