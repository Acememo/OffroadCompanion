"""Race.mx (open data, CC BY 4.0): Mexico's circuits, ovals and Baja start lines, and the Baja 1000 course in race
order.

race.mx publishes its venues as points (venues.json), not track outlines: a circuit's lap comes from
OpenStreetMap at that point (osm.py). Its Baja 1000 spectator map lists the course's towns and checkpoints in race
order; that list is offered as a waypoint course (go town to town) and, once race.mx adds SCORE's course line to
the page, the linked course files are offered too.
"""
import re
import urllib.parse

from ..fetch import FetchError
from .. import geo, htmllinks, trackparse
from . import osm

ID = "racemx"
TITLE = "Race.mx (Mexico circuits and Baja courses)"
ATTRIBUTION = "Venues and course order: Race.mx (CC BY 4.0, race.mx)"
VENUES_URL = "https://race.mx/data/venues.json"
BAJA_MAP_URL = "https://race.mx/baja-1000-spectator-map/"
TTL = 6 * 3600
_GMAPS = re.compile(r"[?&]query=(-?\d+(?:\.\d+)?)(?:%2C|,)\s*(-?\d+(?:\.\d+)?)", re.I)
_DIRT = re.compile(r"dirt|off-road|offroad", re.I)


def _slug(url):
    return urllib.parse.urlsplit(url or "").path.rstrip("/").rsplit("/", 1)[-1]


def venues(fetcher):
    data = fetcher.get(VENUES_URL, ttl=TTL, accept="application/json").json()
    out = []
    for v in (data or {}).get("venues", []):
        try:
            lat, lon = float(v["latitude"]), float(v["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append({"slug": _slug(v.get("url")) or v.get("name", ""), "name": v.get("name", ""),
                    "location": v.get("location", ""), "surface": v.get("surface", "") or "",
                    "length_km": v.get("length_km"), "lat": lat, "lon": lon, "url": v.get("url", "")})
    return out


def baja_course_points(html_text, base=BAJA_MAP_URL):
    """[(name, lat, lon)] of the spectator map's Google Maps links, in page (race) order. The name is the bold
    place name of the list item the link sits in. Pure."""
    _, links = htmllinks.parse(html_text, base)
    out, seen = [], set()
    for l in links:
        m = _GMAPS.search(l["href"])
        if not m or "google." not in l["href"]:
            continue
        lat, lon = float(m.group(1)), float(m.group(2))
        if (lat, lon) in seen:
            continue
        seen.add((lat, lon))
        name = (l.get("block") or l.get("heading") or "").strip()
        if not name or name.lower().startswith("google"):
            name = f"Waypoint {len(out) + 1}"
        out.append((name.rstrip(":"), lat, lon))
    return out


def list_items(fetcher, ctx):
    items, notes = [], []
    lat, lon = ctx.get("lat"), ctx.get("lon")
    try:
        page = fetcher.get(BAJA_MAP_URL, ttl=TTL).text()
        title, links = htmllinks.parse(page, BAJA_MAP_URL)
        pts = baja_course_points(page)
        if pts:
            items.append({"id": "baja1000-order", "name": "2026 SCORE Baja 1000 - towns & checkpoints in race order",
                          "detail": f"{len(pts)} waypoints, San Jose del Cabo loop (go town to town)",
                          "kind": "waypoints", "lat": pts[0][1], "lon": pts[0][2]})
        for l in links:
            if htmllinks.is_course_file(l["href"]):
                items.append({"id": "file:" + l["href"], "name": "2026 Baja 1000 course line - " + (l["text"] or "file"),
                              "detail": "course file linked by race.mx", "kind": "course"})
    except Exception as e:
        notes.append(f"Baja 1000 map unavailable ({e}).")
    try:
        for v in venues(fetcher):
            kind = "start" if _DIRT.search(v["surface"]) else "circuit"
            d = f"{v['location']}"
            if v["length_km"]:
                d += f" - {float(v['length_km']):.3f} km"
            if v["surface"]:
                d += f" - {v['surface']}"
            item = {"id": "venue:" + v["slug"], "name": v["name"], "detail": d, "kind": kind,
                    "lat": v["lat"], "lon": v["lon"]}
            if lat is not None and lon is not None:
                item["dist"] = round(geo.haversine(lat, lon, v["lat"], v["lon"]))
            items.append(item)
    except Exception as e:
        notes.append(f"Venue list unavailable ({e}).")
    q = (ctx.get("q") or "").strip().lower()
    if q:
        items = [i for i in items if q in i["name"].lower() or q in i.get("detail", "").lower()]
    notes.append("Circuit outlines come from OpenStreetMap at each race.mx venue.")
    return {"items": items, "note": " ".join(notes)}


def get(fetcher, ref, ctx):
    if ref == "baja1000-order":
        page = fetcher.get(BAJA_MAP_URL, ttl=TTL).text()
        pts = baja_course_points(page)
        if len(pts) < 2:
            raise trackparse.TrackError("race.mx's Baja 1000 map lists no waypoints right now")
        wps = [{"name": n, "lat": la, "lon": lo} for n, la, lo in pts]
        # the course is a loop: the start/finish closes it
        wps[0]["name"] = wps[0]["name"] + " (Start)"
        wps.append({"name": pts[0][0] + " (Finish)", "lat": pts[0][1], "lon": pts[0][2]})
        t = trackparse.build("2026 SCORE Baja 1000 (race order, race.mx)", [], wps, source=ID,
                             source_url=BAJA_MAP_URL, attribution=ATTRIBUTION + "; course by SCORE International")
        return t
    if ref.startswith("file:"):
        url = ref[5:]
        resp = fetcher.get(url, ttl=24 * 3600)
        return trackparse.parse(resp.body, url.rsplit("/", 1)[-1], source=ID, source_url=url,
                                attribution="Course: SCORE International via race.mx")
    if ref.startswith("venue:"):
        slug = ref[6:]
        v = next((v for v in venues(fetcher) if v["slug"] == slug), None)
        if not v:
            raise trackparse.TrackError("venue not found on race.mx")
        note = None
        if not _DIRT.search(v["surface"]):
            try:
                c = osm.best_near(fetcher, v["lat"], v["lon"], 3000)
            except FetchError as e:
                # (OpenStreetMap's Overpass servers down, as for weeks from about 2026-10-10: the user's Tulum stayed on
                # "Loading course"): the venue itself, to drive to; its outline once the servers answer again
                c, note = None, str(e)
            if c:
                return osm.track_from(c, name=v["name"], source=ID, source_url=v["url"],
                                      attribution=ATTRIBUTION + "; outline (c) OpenStreetMap contributors (ODbL)")
        # a Baja start line (or a circuit OSM has no outline for, or none to be had now): the point itself
        t = trackparse.build(v["name"], [], [{"name": v["name"] + " (start/finish)", "lat": v["lat"],
                                              "lon": v["lon"]}], source=ID, source_url=v["url"],
                             attribution=ATTRIBUTION)
        if note:
            t["note"] = ("The circuit's outline comes from OpenStreetMap, whose servers are not answering right now: "
                         "this takes you to the venue. Load it again later for the lap.")
        return t
    raise trackparse.TrackError("unknown race.mx item")
