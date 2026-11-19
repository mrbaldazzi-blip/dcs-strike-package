"""Real runway geometry (length, width, both ends) from the public OurAirports data.

pydcs gives a runway's heading but not its length or position. The DCS airfields are mostly real,
so `dcsgen fetch-runways` (fetch_runways.bat) downloads OurAirports' runway list once and keeps the
runways with known end coordinates. find() then matches a DCS airfield to the nearest real runway
of the same heading. Fictional or moved airfields simply find nothing and keep the heading-only layout.
"""

import csv
import io
import json
import math
import urllib.request
from pathlib import Path

URLS = ["https://davidmegginson.github.io/ourairports-data/runways.csv",
        "https://ourairports.com/data/runways.csv"]
AIRPORT_URLS = ["https://davidmegginson.github.io/ourairports-data/airports.csv",
                "https://ourairports.com/data/airports.csv"]
DATA = Path(__file__).parent / "data" / "runways.json"

# (south, west, north, east): everywhere a supported map lives, generously
BOXES = [(26.5, 28.0, 33.5, 37.0), (39.0, 27.0, 47.5, 47.5), (22.0, 47.0, 31.0, 61.0),
         (31.0, 31.0, 38.5, 43.0), (11.0, 139.0, 21.0, 148.0), (66.0, 15.0, 72.5, 42.0),
         (-56.0, -66.0, -49.0, -55.0), (34.0, -118.5, 38.5, -112.0), (29.0, 60.0, 38.0, 75.0),
         (47.0, 3.0, 56.0, 16.0), (29.0, 38.0, 38.0, 49.0)]
_cache = {}


def _in_boxes(lat, lng):
    return any(s <= lat <= n and w <= lng <= e for s, w, n, e in BOXES)


def parse(text):
    """Rows of [lat_a, lng_a, lat_b, lng_b, length_m, width_m] from an OurAirports runways.csv.

    Closed runways are kept: many real military and Cold War fields that DCS models are listed as
    closed. Matching still requires the DCS airfield point to lie on the strip."""
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            a = (float(row["le_latitude_deg"]), float(row["le_longitude_deg"]))
            b = (float(row["he_latitude_deg"]), float(row["he_longitude_deg"]))
        except (KeyError, ValueError):
            continue
        if not (_in_boxes(*a) or _in_boxes(*b)):
            continue
        try:
            length = float(row.get("length_ft") or 0) * 0.3048
            width = float(row.get("width_ft") or 0) * 0.3048
        except ValueError:
            length = width = 0.0
        gap = _dist_m(a, b)
        if gap < 300:                      # helipad or a bad row
            continue
        out.append([round(a[0], 5), round(a[1], 5), round(b[0], 5), round(b[1], 5),
                    round(length or gap), round(width or 45)])
    return out


def _ident_heading(ident):
    digits = "".join(ch for ch in str(ident) if ch.isdigit())
    return (int(digits) * 10) % 360 if digits and not str(ident).upper().startswith("H") else None


def parse_estimates(runways_text, airports_text):
    """Runways with no end coordinates: [lat, lng, heading_true, length_m, width_m] at the airport's point."""
    ap = {}
    for row in csv.DictReader(io.StringIO(airports_text)):
        try:
            lat, lng = float(row["latitude_deg"]), float(row["longitude_deg"])
        except (KeyError, ValueError):
            continue
        if _in_boxes(lat, lng):
            ap[row.get("ident", "")] = (lat, lng)
    out = []
    for row in csv.DictReader(io.StringIO(runways_text)):
        if row.get("airport_ident") not in ap:
            continue
        has_ends = all(row.get(k) for k in ("le_latitude_deg", "le_longitude_deg",
                                            "he_latitude_deg", "he_longitude_deg"))
        if has_ends:
            continue
        try:
            length = float(row.get("length_ft") or 0) * 0.3048
        except ValueError:
            continue
        if length < 600:
            continue
        try:
            hdg = float(row["le_heading_degT"]) if row.get("le_heading_degT") else None
        except ValueError:
            hdg = None
        if hdg is None:
            hdg = _ident_heading(row.get("le_ident", ""))
        if hdg is None:
            continue
        try:
            width = float(row.get("width_ft") or 0) * 0.3048
        except ValueError:
            width = 0.0
        lat, lng = ap[row["airport_ident"]]
        out.append([round(lat, 5), round(lng, 5), round(hdg % 360), round(length), round(width or 45)])
    return out


def _download(urls, say):
    for url in urls:
        try:
            say(f"Downloading {url} ...")
            with urllib.request.urlopen(url, timeout=90) as r:
                return r.read().decode("utf-8", errors="ignore")
        except Exception as e:  # noqa: BLE001
            say(f"  failed: {type(e).__name__}: {e}")
    return None


def fetch(path=DATA, say=print):
    text = _download(URLS, say)
    if text is None:
        raise RuntimeError("Could not download the runway data. Check your internet connection.")
    exact = parse(text)
    est = []
    atext = _download(AIRPORT_URLS, say)
    if atext is not None:
        est = parse_estimates(text, atext)
    else:
        say("Airport list not available; runways without end coordinates will not be matched.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"exact": exact, "est": est}, separators=(",", ":")), encoding="utf-8")
    say(f"Wrote {path}  ({len(exact)} runways with ends, {len(est)} with length only, "
        f"{path.stat().st_size // 1024} KB)")
    return len(exact), len(est)


def _dist_m(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * 6371000.0 * math.asin(min(1.0, math.sqrt(h)))


def _bearing(a, b):
    la1, la2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    y = math.sin(dl) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dl)
    return math.degrees(math.atan2(y, x)) % 360


def _load(path=DATA):
    key = str(path)
    if key not in _cache:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        if isinstance(raw, list):             # an older file: exact rows only
            raw = {"exact": raw, "est": []}
        _cache[key] = raw
    return _cache[key]


def available(path=DATA):
    return bool(_load(path).get("exact") or _load(path).get("est"))


def find(lat, lng, heading=None, radius_m=4000.0, tol_deg=20.0, path=DATA):
    """The runway nearest (lat, lng), optionally of the given heading (either direction).

    Returns {"a": (lat, lng), "b": (lat, lng), "length": m, "width": m} or None."""
    best = None
    for la, lo, lb, lob, length, width in _load(path).get("exact", []):
        mid = ((la + lb) / 2, (lo + lob) / 2)
        d = _dist_m((lat, lng), mid)
        if d > radius_m or d > length / 2 + 300.0:     # the airfield point must lie on the strip
            continue
        if heading is not None:
            diff = abs(((_bearing((la, lo), (lb, lob)) - heading) + 90) % 180 - 90)
            if diff > tol_deg:
                continue
        if best is None or d < best[0]:
            best = (d, {"a": (la, lo), "b": (lb, lob), "length": float(length), "width": float(width)})
    return best[1] if best else None


def find_estimate(lat, lng, heading=None, radius_m=3000.0, tol_deg=20.0, path=DATA):
    """Length and width only, for runways whose end coordinates are not in the data.

    Returns {"length": m, "width": m} or None."""
    best = None
    for la, lo, hdg, length, width in _load(path).get("est", []):
        d = _dist_m((lat, lng), (la, lo))
        if d > radius_m:
            continue
        if heading is not None and abs(((hdg - heading) + 90) % 180 - 90) > tol_deg:
            continue
        if best is None or d < best[0]:
            best = (d, {"length": float(length), "width": float(width)})
    return best[1] if best else None


_NO_STRIP = ("heli", "helo", "farp", "fob", "h frg", "pad", "carrier")


def guess_length(name):
    """A plausible runway length (m) for an airfield with no real data, judged from its name.

    Military fields are usually shorter than commercial ones; small strips shorter still.
    Returns None for helipads and other places with no runway to speak of."""
    n = str(name).lower()
    if any(w in n for w in _NO_STRIP):
        return None
    if any(w in n for w in ("international", "intl")):
        return 3000.0
    if any(w in n for w in ("airstrip", "strip", "flying club", "field", "farm", "island")):
        return 1400.0
    return 2400.0
