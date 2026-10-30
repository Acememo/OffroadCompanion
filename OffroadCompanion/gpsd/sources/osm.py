"""Race circuits from OpenStreetMap (Overpass API): the real track outline, mapped as highway=raceway.

Anywhere in the world: the circuits, karting and motocross tracks near the car (or near a venue another source
names). The raceway ways of one circuit are joined end to end into the lap; pit lanes and paddock roads are left
out. Data (c) OpenStreetMap contributors, ODbL.
"""

from .. import geo, overpass, trackparse

ID = "osm"
TITLE = "OpenStreetMap circuits (worldwide)"
ATTRIBUTION = "Track: (c) OpenStreetMap contributors (ODbL), via Overpass API"
TTL = 7 * 24 * 3600
DEFAULT_RADIUS = 25000
MAX_RADIUS = 150000
MIN_LAP_M = 250
_SKIP = {"pit_lane", "pitlane", "pit", "service", "paddock", "access"}


GRID_DEG = 0.05              # query areas centred on this grid (~5 km): one cached answer serves every spot near it
GRID_PAD_M = 6000.0


def area(lat, lon, radius):
    """(centre lat, centre lon, half size m) of the query area for (lat, lon, radius): snapped to GRID_DEG and padded,
    so a list asked a little further on, the course loaded from it and the pre-load around the car share one answer."""
    r = max(500.0, min(MAX_RADIUS, float(radius)))
    return (round(lat / GRID_DEG) * GRID_DEG, round(lon / GRID_DEG) * GRID_DEG, r + GRID_PAD_M)


def query(lat, lon, radius):
    """A bounding box (lighter on the servers than around:, which timed out on busy days) of the area for (lat, lon,
    radius); near() keeps the tracks within the radius."""
    import math
    clat, clon, half = area(lat, lon, radius)
    dlat = half / 111320.0
    dlon = half / (111320.0 * max(0.05, math.cos(math.radians(clat))))
    bb = f"{clat - dlat:.4f},{clon - dlon:.4f},{clat + dlat:.4f},{clon + dlon:.4f}"
    return (f"[out:json][timeout:25];("
            f'way["highway"="raceway"]({bb});'
            f'way["leisure"="track"]["sport"~"motor|karting|motocross|rally|dirt_track|speedway"]({bb});'
            f");out tags geom;")


def _fetch(fetcher, q):
    return overpass.run(fetcher, q, ttl=TTL, what="OpenStreetMap circuits")


def _usable(tags):
    t = tags or {}
    for k in ("raceway", "service", "track"):
        if str(t.get(k, "")).lower() in _SKIP:
            return False
    if str(t.get("area", "")).lower() == "yes":
        return False
    return True


def circuits(data):
    """[{name, points, closed, length, lat, lon}] of an Overpass answer: connected raceway ways joined. Pure."""
    ways = []
    for el in (data or {}).get("elements", []):
        if el.get("type") != "way" or not el.get("geometry") or not _usable(el.get("tags")):
            continue
        pts = [(g["lat"], g["lon"]) for g in el["geometry"] if "lat" in g]
        if len(pts) >= 2:
            tags = el.get("tags") or {}
            ways.append({"name": tags.get("name") or tags.get("official_name") or "", "points": pts,
                         "sport": tags.get("sport", "")})
    # group ways that touch (shared end nodes, ~ 2 m), then join each group into its longest chain
    groups, used = [], [False] * len(ways)
    def key(p):
        return (round(p[0] * 50000), round(p[1] * 50000))
    ends = {}
    for i, w in enumerate(ways):
        for p in (w["points"][0], w["points"][-1]):
            ends.setdefault(key(p), []).append(i)
    for i in range(len(ways)):
        if used[i]:
            continue
        stack, grp = [i], []
        used[i] = True
        while stack:
            k = stack.pop()
            grp.append(ways[k])
            for p in (ways[k]["points"][0], ways[k]["points"][-1]):
                for j in ends.get(key(p), []):
                    if not used[j]:
                        used[j] = True
                        stack.append(j)
        groups.append(grp)
    out = []
    for grp in groups:
        line = trackparse.chain_lines(grp, gap_m=3.0)
        if len(line) < 2:
            continue
        length = geo.cumulative(line)[-1]
        if length < MIN_LAP_M:
            continue
        closed = geo.haversine(line[0][0], line[0][1], line[-1][0], line[-1][1]) < 15
        names = [w["name"] for w in grp if w["name"]]
        name = max(set(names), key=names.count) if names else "Unnamed track"
        c = line[len(line) // 2]
        out.append({"name": name, "points": line, "closed": closed, "length": length,
                    "lat": c[0], "lon": c[1], "sport": next((w["sport"] for w in grp if w["sport"]), "")})
    out.sort(key=lambda c: -c["length"])
    return out


def _key_for(c):
    p = c["points"][0]
    return f"{c['name']}|{p[0]:.5f},{p[1]:.5f}"


def near(fetcher, lat, lon, radius=DEFAULT_RADIUS):
    r = max(500.0, min(MAX_RADIUS, float(radius)))
    return [c for c in circuits(_fetch(fetcher, query(lat, lon, radius)))
            if min(geo.haversine(lat, lon, p[0], p[1]) for p in c["points"][::max(1, len(c["points"]) // 50)]) <= r]


def list_items(fetcher, ctx):
    lat, lon = ctx.get("lat"), ctx.get("lon")
    if lat is None or lon is None:
        return {"items": [], "note": "Drive somewhere first: circuits are searched around the car."}
    radius = float(ctx.get("radius") or DEFAULT_RADIUS)
    cs = near(fetcher, lat, lon, radius)
    q = (ctx.get("q") or "").strip().lower()
    if q:
        cs = [c for c in cs if q in c["name"].lower()]
    items = []
    for c in cs:
        d = geo.haversine(lat, lon, c["lat"], c["lon"])
        items.append({"id": f"{lat:.5f},{lon:.5f},{int(radius)}|{_key_for(c)}", "name": c["name"],
                      "detail": f"{c['length'] / 1000:.2f} km lap{'' if c['closed'] else ' (open)'} - "
                                f"{d / 1000:.0f} km away" + (f" - {c['sport']}" if c["sport"] else ""),
                      "kind": "circuit", "lat": round(c["lat"], 6), "lon": round(c["lon"], 6),
                      "dist": round(d)})
    items.sort(key=lambda i: i["dist"])
    note = f"{len(items)} tracks within {radius / 1000:.0f} km (OpenStreetMap)."
    return {"items": items, "note": note}


def track_from(c, name=None, source=ID, source_url="", attribution=ATTRIBUTION):
    pts = c["points"]
    wps = [{"name": "Start / Finish" if c["closed"] else "Start", "lat": pts[0][0], "lon": pts[0][1]}]
    if not c["closed"]:
        wps.append({"name": "Finish", "lat": pts[-1][0], "lon": pts[-1][1]})
    return trackparse.from_points(name or c["name"], pts, wps, source=source, source_url=source_url,
                                  attribution=attribution, kind_hint="circuit" if c["closed"] else None)


def get(fetcher, ref, ctx):
    try:
        where, key = ref.split("|", 1)
        lat, lon, radius = where.split(",")
        lat, lon, radius = float(lat), float(lon), float(radius)
    except ValueError:
        raise trackparse.TrackError("bad OpenStreetMap track reference") from None
    for c in near(fetcher, lat, lon, radius):
        if _key_for(c) == key:
            return track_from(c, source_url="https://www.openstreetmap.org/#map=15/%.5f/%.5f" % (c["lat"], c["lon"]))
    raise trackparse.TrackError("that track is no longer in OpenStreetMap's answer")


def preload(fetcher, lat, lon, radius=DEFAULT_RADIUS):
    """The circuits around (lat, lon) fetched into the cache ahead of the list (the companion, as the car moves)."""
    _fetch(fetcher, query(lat, lon, radius))


def best_near(fetcher, lat, lon, radius=3000):
    """The circuit nearest (lat, lon): the longest closed lap among those within radius, else the longest."""
    cs = near(fetcher, lat, lon, radius)
    if not cs:
        return None
    closed = [c for c in cs if c["closed"]]
    pool = closed or cs
    return max(pool, key=lambda c: c["length"] - 0.5 * geo.haversine(lat, lon, c["lat"], c["lon"]))
