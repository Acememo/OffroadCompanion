"""Address and place search for the app, from the companion (BeamNG.Earth's own search goes through its server, one
Photon request at a time with a 5 s wait and an 8 s timeout: when Photon is slow, searches typed meanwhile fail with
"no free request slot", the user 2026-10-21).

  coordinates     "31.86, -116.60" (or with N/S/E/W) is a place at once, no network;
  Photon          (photon.komoot.io, komoot; made for search-as-you-type) for typing and Enter, a longer timeout;
  Nominatim       (nominatim.openstreetmap.org) only when the search is submitted (Enter / the button) and Photon
                  failed or found nothing: its usage policy allows no autocomplete, at most 1 request a second.

Results: [{name, detail, kind, lat, lon}], nearest first when the car's position is given. Cached for a week.
Both: data (c) OpenStreetMap contributors (ODbL).
"""
import re
import urllib.parse

from .fetch import FetchError

PHOTON_URL = "https://photon.komoot.io/api/"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
LIMIT = 8
MIN_CHARS = 3
TTL = 7 * 24 * 3600
PHOTON_TIMEOUT_S = 12
NOMINATIM_TIMEOUT_S = 15
LANGS = ("en", "de", "fr")          # Photon's languages (others: its default)


def parse_latlon(text):
    """(lat, lon) from typed coordinates ("31.8667, -116.6", "31.8667 N 116.6 W"), else None. Pure."""
    t = (text or "").strip().upper()
    m = re.fullmatch(r"([-+]?\d{1,2}(?:\.\d+)?)\s*([NS])?\s*[,; ]\s*([-+]?\d{1,3}(?:\.\d+)?)\s*([EW])?", t)
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(3))
    if m.group(2) == "S":
        lat = -abs(lat)
    if m.group(4) == "W":
        lon = -abs(lon)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def _bias(lat, lon):
    # rounded (~5 km): nearby searches share the cache
    return (round(lat, 2), round(lon, 2)) if lat is not None and lon is not None else None


def photon_url(q, lat=None, lon=None, lang="en"):
    params = [("q", q), ("limit", str(LIMIT))]
    if lang in LANGS:
        params.append(("lang", lang))
    b = _bias(lat, lon)
    if b:
        params += [("lat", f"{b[0]:.2f}"), ("lon", f"{b[1]:.2f}")]
    return PHOTON_URL + "?" + urllib.parse.urlencode(params)


def _label(p):
    street = " ".join(v for v in (p.get("housenumber"), p.get("street")) if v)
    name = p.get("name") or street or p.get("city") or p.get("state") or p.get("country") or "?"
    parts = []
    if street and street != name:
        parts.append(street)
    for k in ("city", "town", "village", "district", "county", "state", "country"):
        v = p.get(k)
        if v and v != name and v not in parts:
            parts.append(v)
        if len(parts) >= 3:
            break
    return name, ", ".join(parts)


def photon_parse(data):
    out = []
    for f in (data or {}).get("features") or []:
        try:
            lon, lat = f["geometry"]["coordinates"][:2]
            lat, lon = float(lat), float(lon)
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        p = f.get("properties") or {}
        name, detail = _label(p)
        out.append({"name": name, "detail": detail, "kind": p.get("osm_value") or "", "lat": round(lat, 6),
                    "lon": round(lon, 6)})
    return out


def nominatim_url(q, lat=None, lon=None, lang="en"):
    params = [("q", q), ("format", "jsonv2"), ("limit", str(LIMIT)), ("addressdetails", "1"),
              ("accept-language", lang or "en")]
    b = _bias(lat, lon)
    if b:       # a preferred area (not a limit): about 100 km around the car
        d = 1.0
        params.append(("viewbox", f"{b[1] - d:.2f},{b[0] + d:.2f},{b[1] + d:.2f},{b[0] - d:.2f}"))
    return NOMINATIM_URL + "?" + urllib.parse.urlencode(params)


def nominatim_parse(data):
    out = []
    for r in data if isinstance(data, list) else []:
        try:
            lat, lon = float(r["lat"]), float(r["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        a = r.get("address") or {}
        p = {"name": r.get("name") or "", "housenumber": a.get("house_number"), "street": a.get("road"),
             "city": a.get("city") or a.get("town") or a.get("village"), "county": a.get("county"),
             "state": a.get("state"), "country": a.get("country")}
        name, detail = _label(p)
        if name == "?":
            name = str(r.get("display_name") or "?").split(",")[0]
        out.append({"name": name, "detail": detail, "kind": r.get("type") or "", "lat": round(lat, 6),
                    "lon": round(lon, 6)})
    return out


def search(fetcher, q, lat=None, lon=None, lang="en", submitted=False):
    """{results, source, error?}. submitted: Enter / the button (Nominatim may be asked)."""
    q = " ".join((q or "").split())[:200]
    ll = parse_latlon(q)
    if ll:
        return {"results": [{"name": f"{ll[0]:.5f}, {ll[1]:.5f}", "detail": "Coordinates", "kind": "coordinates",
                             "lat": ll[0], "lon": ll[1]}], "source": "coordinates"}
    if len(q) < MIN_CHARS:
        return {"results": [], "source": None}
    err = None
    try:
        res = photon_parse(fetcher.get(photon_url(q, lat, lon, lang), ttl=TTL, timeout=PHOTON_TIMEOUT_S).json())
        if res or not submitted:
            return {"results": res, "source": "photon"}
    except (FetchError, ValueError) as e:
        err = e
        if not submitted:
            return {"results": [], "source": "photon", "error": f"Photon search: {e}", "retry": True}
    try:
        res = nominatim_parse(fetcher.get(nominatim_url(q, lat, lon, lang), ttl=TTL,
                                          timeout=NOMINATIM_TIMEOUT_S).json())
        return {"results": res, "source": "nominatim"}
    except (FetchError, ValueError) as e:
        msg = f"Nominatim search: {e}"
        if err is not None:
            msg = f"Photon search: {err}; {msg}"
        return {"results": [], "source": None, "error": msg}
