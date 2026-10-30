"""How urban each stretch of a course is: the bigger crowds gather near towns (the user, 2026-10-25: "The closer to urban
centers the larger the crowd", for the Lots spectators, with photos of SCORE Baja races: the course lined with people,
canopies and parked trucks for hundreds of metres near Ensenada and Tecate, far fewer out in the desert).

The places come from OpenStreetMap once per course (cities, towns and villages along it: one Overpass query of boxes
along the course, cached for a year, so a course keeps the same crowds), fetched in the background: a course_sides
answer says "pending" until they are in. Each place reaches out from its middle by its kind and its population; a point
of the course gets 0 (open desert) .. 1 (in a city).
"""
import logging
import math
import threading

from . import overpass

log = logging.getLogger("gpsd.urban")

STEP_M = 100.0              # one value every this many metres along the course
CHUNK_N = 5000              # course samples (10 m) per box of the query: ~50 km
MARGIN_DEG = 0.25           # each box this much bigger every way (~25 km: a city's reach)
TTL = 365 * 24 * 3600
# kind -> weight (how urban its middle is), reach (m: nothing past it), population that reach is for
KINDS = {"city": (1.0, 14000.0, 100000.0), "town": (0.7, 6000.0, 10000.0), "village": (0.4, 2500.0, 1000.0)}
REACH_SCALE = (0.6, 2.2)    # a population this much smaller / larger shrinks / grows the reach (by its 4th root)
FULL_AT = 0.25              # full weight within this share of the reach, then easing out to 0 at the reach


def query(boxes):
    parts = "".join(f'node["place"~"^(city|town|village)$"]({s:.4f},{w:.4f},{n:.4f},{e:.4f});' for s, w, n, e in boxes)
    return f"[out:json][timeout:120];({parts});out body;"


def boxes(lats, lons):
    """Boxes (south, west, north, east) covering the course in CHUNK_N-sample pieces, MARGIN_DEG round each."""
    out = []
    n = len(lats)
    for i in range(0, max(1, n), CHUNK_N):
        la, lo = lats[i:i + CHUNK_N + 1], lons[i:i + CHUNK_N + 1]
        if not la:
            break
        out.append((min(la) - MARGIN_DEG, min(lo) - MARGIN_DEG, max(la) + MARGIN_DEG, max(lo) + MARGIN_DEG))
    return out


def _pop(tags):
    v = str(tags.get("population") or "").replace(",", "").replace(" ", "").split(".")[0]
    return float(v) if v.isdigit() and int(v) > 0 else None


def parse(data):
    """[(lat, lon, kind, population or None)] of an Overpass answer, each place once."""
    out, seen = [], set()
    for el in (data or {}).get("elements") or ():
        tags = el.get("tags") or {}
        kind = tags.get("place")
        if kind not in KINDS or el.get("lat") is None or el.get("id") in seen:
            continue
        seen.add(el.get("id"))
        out.append((float(el["lat"]), float(el["lon"]), kind, _pop(tags)))
    return out


def reach(kind, pop):
    """(weight, reach m) of a place of this kind and population."""
    w, r, ref = KINDS[kind]
    if pop:
        lo, hi = REACH_SCALE
        r *= min(hi, max(lo, (pop / ref) ** 0.25))
    return w, r


class Places:
    """The places, by grid cell, to find those near a point fast."""
    CELL = 0.2

    def __init__(self, places):
        self.cells = {}
        self.max_r = 1.0
        for la, lo, kind, pop in places:
            w, r = reach(kind, pop)
            self.max_r = max(self.max_r, r)
            k = (int(math.floor(la / self.CELL)), int(math.floor(lo / self.CELL)))
            self.cells.setdefault(k, []).append((la, lo, w, r))

    def value(self, lat, lon):
        """0 (open country) .. 1 (a city's middle): every place near, combined (1 - the product of 1 - each)."""
        dla = self.max_r / 111320.0
        dlo = dla / max(0.05, math.cos(math.radians(lat)))
        ka0, ka1 = int(math.floor((lat - dla) / self.CELL)), int(math.floor((lat + dla) / self.CELL))
        ko0, ko1 = int(math.floor((lon - dlo) / self.CELL)), int(math.floor((lon + dlo) / self.CELL))
        keep = 1.0
        cosl = math.cos(math.radians(lat))
        for a in range(ka0, ka1 + 1):
            for b in range(ko0, ko1 + 1):
                for pla, plo, w, r in self.cells.get((a, b), ()):
                    d = math.hypot((pla - lat) * 111320.0, (plo - lon) * 111320.0 * cosl)
                    t = d / r
                    if t >= 1.0:
                        continue
                    f = 1.0 if t <= FULL_AT else 1.0 - _smooth((t - FULL_AT) / (1.0 - FULL_AT))
                    keep *= 1.0 - w * f
        return round(1.0 - keep, 2)


def _smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3.0 - 2.0 * x)


class Urban:
    """A course's places, fetched once in the background. state(key, lats, lons) -> 'ok' | 'pending' | 'failed'."""

    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.lock = threading.Lock()
        self.key = None
        self.st = None
        self.places = None
        self.error = None

    def state(self, key, lats, lons):
        with self.lock:
            if key == self.key:
                return self.st
            self.key, self.st, self.places, self.error = key, "pending", None, None
        threading.Thread(target=self._fetch, args=(key, list(lats), list(lons)), daemon=True,
                         name="gpsd-urban").start()
        return "pending"

    def _fetch(self, key, lats, lons):
        try:
            places = Places(parse(overpass.run(self.fetcher, query(boxes(lats, lons)), ttl=TTL,
                                               what="OpenStreetMap towns along the course")))
            st, err = "ok", None
        except Exception as e:              # (no towns known: open country everywhere, crowds as they are)
            log.info("towns along the course: %s", e)
            places, st, err = None, "failed", str(e)
        with self.lock:
            if self.key == key:
                self.places, self.st, self.error = places, st, err

    def values(self, lats, lons, k0, k1, sample_m):
        """The urban value every STEP_M from k0 to k1 (inclusive) of the course (samples lats / lons every sample_m);
        0 everywhere once the places could not be fetched, None while they are being fetched."""
        with self.lock:
            st, places = self.st, self.places
        if st == "pending":
            return None
        out = []
        per = max(1, int(round(STEP_M / sample_m)))
        n = len(lats)
        for k in range(k0, k1 + 1):
            i = min(n - 1, max(0, k * per))
            out.append(places.value(lats[i], lons[i]) if places is not None else 0.0)
        return out
