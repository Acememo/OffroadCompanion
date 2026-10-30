"""Streets with their names for the app's map (the way Google Maps shows them): OpenStreetMap ways from the Overpass
API, in tiles of TILE_DEG degrees, fetched in one background thread and kept (in memory and in the companion's
download cache), so the game asks for what is near the car and gets each tile once.

A tile: {key, ways: [{c: class, n: name, r: ref, p: [[lat, lon]...]}]}, the line simplified to SIMPLIFY_M.
"""
import logging
import math
import threading
from collections import OrderedDict

from . import geo, overpass

log = logging.getLogger("earth_gpsd.streets")

TILE_DEG = 0.02
SIMPLIFY_M = 3.0
TTL = 30 * 24 * 3600
CLASSES = ("motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service|track|road|"
           "pedestrian")
MAX_RADIUS = 6000.0
MEM_TILES = 64


def tile_of(lat, lon):
    return int(math.floor(lat / TILE_DEG)), int(math.floor(lon / TILE_DEG))


def tile_key(t):
    return f"{t[0]}_{t[1]}"


def tiles_near(lat, lon, radius):
    r = min(MAX_RADIUS, max(200.0, radius))
    dlat = r / 111320.0
    dlon = r / (111320.0 * max(0.05, math.cos(math.radians(lat))))
    a0, o0 = tile_of(lat - dlat, lon - dlon)
    a1, o1 = tile_of(lat + dlat, lon + dlon)
    out = [(a, o) for a in range(a0, a1 + 1) for o in range(o0, o1 + 1)]
    ca, co = tile_of(lat, lon)
    out.sort(key=lambda t: (t[0] - ca) ** 2 + (t[1] - co) ** 2)     # the car's own tile first
    return out


def query(t):
    s, w = t[0] * TILE_DEG, t[1] * TILE_DEG
    return (f'[out:json][timeout:60];way["highway"~"^({CLASSES})(_link)?$"]'
            f"({s:.5f},{w:.5f},{s + TILE_DEG:.5f},{w + TILE_DEG:.5f});out tags geom qt;")


def parse(data):
    """The ways of an Overpass answer, simplified. Pure."""
    out = []
    for el in (data or {}).get("elements", []):
        g = el.get("geometry") or []
        tags = el.get("tags") or {}
        if el.get("type") != "way" or len(g) < 2 or str(tags.get("area", "")) == "yes":
            continue
        cls = str(tags.get("highway", "road")).replace("_link", "")
        pts = [(p["lat"], p["lon"]) for p in g if "lat" in p]
        pts = geo.simplify(pts, SIMPLIFY_M)
        out.append({"c": cls, "n": str(tags.get("name") or ""), "r": str(tags.get("ref") or ""),
                    "p": [[round(a, 6), round(b, 6)] for a, b in pts]})
    return out


class Streets:
    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.lock = threading.Lock()
        self.tiles = OrderedDict()      # key -> ways
        self.failed = {}                # key -> error
        self.queue = []
        self.wake = threading.Event()
        threading.Thread(target=self._run, name="streets", daemon=True).start()

    def near(self, lat, lon, radius, have=()):
        """{tiles: [{key, ways}] not in have, pending, error}"""
        have = set(str(k) for k in have or ())
        out, pending, err = [], 0, None
        want = tiles_near(lat, lon, radius)
        with self.lock:
            for t in want:
                k = tile_key(t)
                if k in self.tiles:
                    self.tiles.move_to_end(k)
                    if k not in have:
                        out.append({"key": k, "ways": self.tiles[k]})
                    continue
                pending += 1
                err = err or self.failed.get(k)
                if t not in self.queue:
                    self.queue.append(t)
            # what is near goes first; tiles no longer wanted are dropped from the queue
            self.queue = [t for t in want if t in self.queue]
        if pending:
            self.wake.set()
        return {"tiles": out, "pending": pending, "error": err}

    def _run(self):
        while True:
            self.wake.wait(5.0)
            self.wake.clear()
            while True:
                with self.lock:
                    if not self.queue:
                        break
                    t = self.queue.pop(0)
                k = tile_key(t)
                try:
                    data = overpass.run(self.fetcher, query(t), ttl=TTL, what="OpenStreetMap streets")
                    ways = parse(data)
                    with self.lock:
                        self.tiles[k] = ways
                        self.failed.pop(k, None)
                        while len(self.tiles) > MEM_TILES:
                            self.tiles.popitem(last=False)
                except Exception as e:
                    log.warning("streets %s: %s", k, e)
                    with self.lock:
                        self.failed[k] = str(e)
