"""The dirt track's plan made by the companion (for BeamNG.Earth's packaged .exe, whose server cannot be extended):
the same plan as the server painter (courseroads.py), from public data the companion can read itself.

  roads already drawn   OpenStreetMap ways via the Overpass API (BeamNG.Earth's Overture roads are mostly OSM's),
                        the classes BeamNG.Earth draws, with its default widths
  elevation             AWS Terrain Tiles (Terrarium PNGs, one of BeamNG.Earth's own elevation sources), decoded
                        here with the standard library
  trees                 not used (the server painter has the canopy model)

Painter.near(track, scale, lat, lon) hands out the windows of the course near the car: the ones ready now, and it
starts the missing ones (nearest first) in one background thread; the game asks again a moment later.
"""
import array
import logging
import math
import os
import struct
import threading
import zlib
from collections import OrderedDict

from . import courseroads, overpass, paintfile

log = logging.getLogger("earth_gpsd.paint")

TERRARIUM_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
BLOCK = 4                   # windows per Overpass request
BLOCK_PAD_M = 200.0
NEAR_M = 2500.0
DEM_MEM = 48                # decoded tiles kept
ATTRIBUTION = "Dirt track: roads (c) OpenStreetMap contributors (ODbL), elevation AWS Terrain Tiles"

# the classes BeamNG.Earth draws and its default carriageway widths (server/roads.py STYLE)
WIDTH = {"motorway": 11.0, "trunk": 9.0, "primary": 8.0, "secondary": 7.5, "tertiary": 6.5, "residential": 6.0,
         "living_street": 5.0, "unclassified": 5.5, "service": 4.0, "track": 3.5, "road": 5.0}


# -- PNG (8-bit RGB / RGBA, not interlaced: what Terrarium tiles are) --------------------------------------------
def decode_png(data):
    """(width, height, channels, rows: list of bytes) of a PNG. Raises ValueError for what it does not read."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, w = 8, [], None
    while pos + 8 <= len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            w, h, depth, ctype, _comp, _filt, inter = struct.unpack(">IIBBBBB", body)
            if depth != 8 or ctype not in (2, 6) or inter != 0:
                raise ValueError(f"PNG kind not read here (depth {depth}, colour {ctype}, interlace {inter})")
            ch = 3 if ctype == 2 else 4
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    if w is None:
        raise ValueError("PNG without a header")
    raw = zlib.decompress(b"".join(idat))
    stride = w * ch
    rows, prev = [], bytearray(stride)
    p = 0
    for _ in range(h):
        f = raw[p]
        cur = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        if f == 1:
            for i in range(ch, stride):
                cur[i] = (cur[i] + cur[i - ch]) & 255
        elif f == 2:
            for i in range(stride):
                cur[i] = (cur[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                left = cur[i - ch] if i >= ch else 0
                cur[i] = (cur[i] + ((left + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = cur[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                cur[i] = (cur[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        elif f != 0:
            raise ValueError(f"bad PNG filter {f}")
        rows.append(bytes(cur))
        prev = cur
    return w, h, ch, rows


def terrarium_heights(png):
    """array('f') of 256 x 256 heights (m) of a Terrarium tile: R x 256 + G + B / 256 - 32768."""
    w, h, ch, rows = decode_png(png)
    out = array.array("f")
    for r in rows:
        out.extend(r[i] * 256.0 + r[i + 1] + r[i + 2] / 256.0 - 32768.0 for i in range(0, w * ch, ch))
    return w, h, out


class Dem:
    """Bilinear heights from Terrarium tiles (fetched through the companion's Fetcher, decoded tiles on disk)."""

    def __init__(self, fetcher, zoom=courseroads.DEM_ZOOM, cache_dir=None):
        self.fetcher, self.zoom = fetcher, zoom
        self.cache_dir = cache_dir or os.path.join(paintfile.base_dir(), "dem")
        self.mem = OrderedDict()
        self.lock = threading.Lock()

    def tile(self, x, y):
        key = (x, y)
        with self.lock:
            t = self.mem.get(key)
            if t is not None:
                self.mem.move_to_end(key)
                return t
        path = os.path.join(self.cache_dir, str(self.zoom), str(x), f"{y}.f32")
        t = None
        try:
            with open(path, "rb") as f:
                t = array.array("f")
                t.frombytes(f.read())
            if len(t) != 65536:
                t = None
        except OSError:
            t = None
        if t is None:
            png = self.fetcher.get(TERRARIUM_URL.format(z=self.zoom, x=x, y=y), ttl=None).body
            w, h, t = terrarium_heights(png)
            if w != 256 or h != 256:
                raise ValueError(f"terrain tile {self.zoom}/{x}/{y} is {w}x{h}")
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path + ".tmp", "wb") as f:
                    f.write(t.tobytes())
                os.replace(path + ".tmp", path)
            except OSError:
                pass
        with self.lock:
            self.mem[key] = t
            while len(self.mem) > DEM_MEM:
                self.mem.popitem(last=False)
        return t

    def sample(self, lats, lons):
        n = 2 ** self.zoom
        size = n * 256
        out = []
        for la, lo in zip(lats, lons):
            la = min(85.05, max(-85.05, la))
            fx = (lo / 360.0 + 0.5) * size - 0.5
            fy = (0.5 - math.asinh(math.tan(math.radians(la))) / (2 * math.pi)) * size - 0.5
            x0, y0 = int(math.floor(fx)), int(math.floor(fy))
            tx, ty = fx - x0, fy - y0

            def px(gx, gy):
                gx %= size
                gy = min(size - 1, max(0, gy))
                t = self.tile(gx // 256, gy // 256)
                return t[(gy % 256) * 256 + gx % 256]
            a, b = px(x0, y0), px(x0 + 1, y0)
            c, d = px(x0, y0 + 1), px(x0 + 1, y0 + 1)
            out.append((a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty)
        return out


# -- the roads already drawn ---------------------------------------------------------------------------------------
def overpass_query(s, w, n, e):
    return ('[out:json][timeout:60];way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|'
            'residential|living_street|service|track|road)(_link)?$"]'
            f"({s:.6f},{w:.6f},{n:.6f},{e:.6f});out geom qt;")


def road_lines(data):
    """[(half width, [(lat, lon)...])] of an Overpass answer: the classes BeamNG.Earth draws. Pure."""
    out = []
    for el in (data or {}).get("elements", []):
        g = el.get("geometry") or []
        tags = el.get("tags") or {}
        cls = str(tags.get("highway", "")).replace("_link", "")
        if el.get("type") != "way" or len(g) < 2 or cls not in WIDTH:
            continue
        if str(tags.get("area", "")) == "yes":
            continue
        width = WIDTH[cls]
        try:
            tw = float(str(tags.get("width", "")).split()[0])
            if 1.0 <= tw <= 40.0:
                width = tw
        except (ValueError, IndexError):
            pass
        out.append((width / 2, [(p["lat"], p["lon"]) for p in g if "lat" in p]))
    return out


class Painter:
    """Windows of dirt track per course, made in one background thread, kept in memory and on disk."""

    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.dem = Dem(fetcher)
        self.lock = threading.Lock()
        self.courses = OrderedDict()     # cid -> Course
        self.done = {}                   # (cid, k) -> pieces
        self.failed = {}                 # (cid, k) -> error text
        self.queue = []                  # (cid, k) wanted, nearest first
        self.blocks = OrderedDict()      # (cid, block) -> [(half width, [(lat, lon)])]
        self.wake = threading.Event()
        threading.Thread(target=self._run, name="paint", daemon=True).start()

    def course(self, points, scale, name):
        cid = courseroads.course_id(points, scale)
        with self.lock:
            c = self.courses.get(cid)
            if c is None:
                c = self.courses[cid] = courseroads.Course(points, scale, name)
                while len(self.courses) > 3:
                    self.courses.popitem(last=False)
        return c

    def near(self, points, scale, name, lat, lon, have=(), radius=NEAR_M):
        """{cid, windows: [{k, pieces}], pending, errors} for the windows near (lat, lon) not in `have`."""
        c = self.course(points, scale, name)
        ks = c.windows_near(lat, lon, radius)
        # nearest first
        def dist(k):
            a, b = c.inner(k)
            m = (a + b) // 2
            return courseroads.haversine(lat, lon, c.lat[m], c.lon[m])
        ks.sort(key=dist)
        have = set(int(k) for k in have or ())
        out, pending, errors = [], 0, []
        with self.lock:
            for k in ks:
                key = (c.cid, k)
                if key in self.done:
                    if k not in have:
                        out.append({"k": k, "pieces": self.done[key]})
                    continue
                if key not in self.queue:
                    self.queue.append(key)
                pending += 1
                if key in self.failed:
                    errors.append(self.failed[key])
            # what the car is near goes first
            near = [(c.cid, k) for k in ks]
            self.queue = [q for q in near if q in self.queue] + [q for q in self.queue if q not in near]
        if pending:
            self.wake.set()
        return {"cid": c.cid, "windows": out, "pending": pending, "errors": sorted(set(errors))[:2],
                "total": c.nwin}

    # -- the worker ----------------------------------------------------------------------------------------------
    def _run(self):
        while True:
            self.wake.wait(5.0)
            self.wake.clear()
            while True:
                with self.lock:
                    if not self.queue:
                        break
                    cid, k = self.queue.pop(0)
                    c = self.courses.get(cid)
                if c is None:
                    continue
                try:
                    pieces = self._window(c, k)
                    with self.lock:
                        self.done[(cid, k)] = pieces
                        self.failed.pop((cid, k), None)
                except Exception as e:          # (offline, a service down: asked again on the next request)
                    log.warning("dirt track window %d of %s: %s", k, c.name, e)
                    with self.lock:
                        self.failed[(cid, k)] = str(e)

    def _window(self, c, k):
        path = os.path.join(paintfile.windows_dir(c.cid), f"g{k:06d}.json")
        got = paintfile.read_json(path)
        if isinstance(got, dict) and got.get("algo") == courseroads.ALGO:
            return got["pieces"]
        pieces = courseroads.window_pieces(c, k, self._segs_fn(c, k), self.dem.sample)
        try:
            paintfile.write_json(path, {"algo": courseroads.ALGO, "pieces": pieces})
        except OSError:
            pass
        return pieces

    def _block_roads(self, c, b):
        key = (c.cid, b)
        with self.lock:
            got = self.blocks.get(key)
        if got is not None:
            return got
        ks = range(b * BLOCK, min(c.nwin, (b + 1) * BLOCK))
        x0 = min(c.boxes[k][0] for k in ks)
        y0 = min(c.boxes[k][1] for k in ks)
        x1 = max(c.boxes[k][2] for k in ks)
        y1 = max(c.boxes[k][3] for k in ks)
        pad = BLOCK_PAD_M / 111320.0
        padlo = pad / max(0.05, math.cos(math.radians((y0 + y1) / 2)))
        q = overpass_query(y0 - pad, x0 - padlo, y1 + pad, x1 + padlo)
        data = overpass.run(self.fetcher, q, ttl=7 * 24 * 3600, what="OpenStreetMap roads")
        lines = road_lines(data)
        with self.lock:
            self.blocks[key] = lines
            while len(self.blocks) > 16:
                self.blocks.popitem(last=False)
        return lines

    def _segs_fn(self, c, k):
        def fn(lat0, lon0, lat1, lon1, plane):
            # (the block's box is padded well past the window's context and the widest road's reach)
            lines = self._block_roads(c, k // BLOCK)
            out = []
            for hw, pts in lines:
                for (a1, o1), (a2, o2) in zip(pts, pts[1:]):
                    if max(a1, a2) < lat0 or min(a1, a2) > lat1 or max(o1, o2) < lon0 or min(o1, o2) > lon1:
                        continue
                    ax, ay = plane.xy(a1, o1)
                    bx, by = plane.xy(a2, o2)
                    out.append((ax, ay, bx, by, hw))
            return out
        return fn

