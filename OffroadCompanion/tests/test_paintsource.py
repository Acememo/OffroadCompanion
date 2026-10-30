"""The companion's dirt-track plan (for BeamNG.Earth's .exe): the PNG decoder, OSM roads, the whole Painter."""
import io
import json
import math
import os
import re
import struct
import sys
import tempfile
import time
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["EARTHGPS_DIR"] = tempfile.mkdtemp(prefix="egps-src-")

from gpsd import courseroads as cr, paintsource as ps  # noqa: E402
from gpsd.fetch import FetchError, Response  # noqa: E402

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

LAT0, LON0 = 31.0, -115.5
KX = math.radians(1) * cr.R_EARTH * math.cos(math.radians(LAT0))
KY = math.radians(1) * cr.R_EARTH


def ll(x, y):
    return LAT0 + y / KY, LON0 + x / KX


def ground_xy(x, y):
    if 3500 <= x < 4800:
        return 0.30 * y
    if x >= 5000:
        return (abs(y) - 5) * 1.5 if abs(y) > 5 else 0.0
    return 0.0


def png_rows(rows, ch, filters):
    """A PNG with the given per-row filter types (the encoder side of each filter)."""
    w = len(rows[0]) // ch
    raw, prev = bytearray(), bytearray(len(rows[0]))
    for r, f in zip(rows, filters):
        out = bytearray([f])
        for i in range(len(r)):
            a = r[i - ch] if i >= ch else 0
            b = prev[i]
            c = prev[i - ch] if i >= ch else 0
            if f == 0:
                p = 0
            elif f == 1:
                p = a
            elif f == 2:
                p = b
            elif f == 3:
                p = (a + b) >> 1
            else:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                p = a if pa <= pb and pa <= pc else b if pb <= pc else c
            out.append((r[i] - p) & 255)
        raw += out
        prev = bytearray(r)

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, len(rows), 8, 2 if ch == 3 else 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))


def terrarium_png(z, tx, ty):
    """The test world's tile as a Terrarium PNG (every filter type used)."""
    n = 2 ** z
    rows = []
    for py in range(256):
        r = bytearray()
        for px in range(256):
            gx, gy = tx * 256 + px + 0.5, ty * 256 + py + 0.5
            lon = gx / (n * 256) * 360.0 - 180.0
            lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * gy / (n * 256)))))
            x, y = (lon - LON0) * KX, (lat - LAT0) * KY
            v = ground_xy(x, y) + 32768.0
            R = int(v // 256)
            G = int(v - R * 256)
            B = int(round((v - R * 256 - G) * 256)) & 255
            r += bytes([R, G, B])
        rows.append(bytes(r))
    return png_rows(rows, 3, [py % 5 for py in range(256)])


class Fake:
    def __init__(self):
        self.calls = []

    def get(self, url, ttl=None, data=None, accept=None):
        self.calls.append(url)
        m = re.search(r"terrarium/(\d+)/(\d+)/(\d+)\.png", url)
        if m:
            return Response(terrarium_png(*map(int, m.groups())), url, "image/png")
        if "interpreter" in url:
            xs = range(2000, 3001, 25)
            road = [{"lat": ll(x, 0)[0], "lon": ll(x, 0)[1]} for x in xs]
            cross = [{"lat": ll(4200, y)[0], "lon": ll(4200, y)[1]} for y in range(-600, 601, 50)]
            return Response(json.dumps({"elements": [
                {"type": "way", "id": 1, "tags": {"highway": "track"}, "geometry": road},
                {"type": "way", "id": 2, "tags": {"highway": "residential"}, "geometry": cross},
                {"type": "way", "id": 3, "tags": {"highway": "footway"}, "geometry": road}]}).encode(), url)
        raise FetchError("HTTP 404", 404)


class TestPng(unittest.TestCase):
    def test_all_filters_rgb_and_rgba(self):
        import random
        rnd = random.Random(3)
        for ch in (3, 4):
            rows = [bytes(rnd.randrange(256) for _ in range(7 * ch)) for _ in range(10)]
            w, h, c, got = ps.decode_png(png_rows(rows, ch, [0, 1, 2, 3, 4, 4, 3, 2, 1, 0]))
            self.assertEqual((w, h, c), (7, 10, ch))
            self.assertEqual(got, rows)

    @unittest.skipUnless(HAVE_PIL, "Pillow")
    def test_against_pillow(self):
        im = Image.new("RGB", (256, 256))
        im.putdata([((i * 7) % 256, (i * 13) % 256, (i // 256) % 256) for i in range(65536)])
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        w, h, ch, rows = ps.decode_png(buf.getvalue())
        self.assertEqual(b"".join(rows), im.tobytes())

    def test_terrarium(self):
        w, h, t = ps.terrarium_heights(terrarium_png(15, 5870, 13398))
        self.assertEqual((w, h, len(t)), (256, 256, 65536))


class TestRoads(unittest.TestCase):
    def test_classes_and_widths(self):
        lines = ps.road_lines({"elements": [
            {"type": "way", "tags": {"highway": "primary_link"}, "geometry": [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 1}]},
            {"type": "way", "tags": {"highway": "track", "width": "6 m"}, "geometry": [{"lat": 0, "lon": 0}, {"lat": 1, "lon": 0}]},
            {"type": "way", "tags": {"highway": "path"}, "geometry": [{"lat": 0, "lon": 0}, {"lat": 1, "lon": 0}]}]})
        self.assertEqual([hw for hw, _ in lines], [4.0, 3.0])


class TestPainter(unittest.TestCase):
    def test_near(self):
        pts = [ll(x, 0.0) for x in range(0, 6001, 50)]
        p = ps.Painter(Fake())
        lat, lon = ll(3000, 0)
        res, end = None, time.time() + 120
        have = []
        got = []
        while time.time() < end:
            res = p.near(pts, 1.0, "Test", lat, lon, have, radius=4000)
            for w in res["windows"]:
                have.append(w["k"])
                got += w["pieces"]
            if res["pending"] == 0:
                break
            time.sleep(0.3)
        self.assertEqual(res["pending"], 0, res)
        self.assertEqual(sorted(have), list(range(6)))
        xs = {}
        for pc in got:
            for (lo, la) in pc["ll"]:
                xs[round((lo - LON0) * KX)] = pc["w"]
        painted = sorted(xs)
        self.assertFalse([x for x in painted if 2020 < x < 2980], "no track on the mapped dirt road")
        self.assertTrue(any(4150 < x < 4250 for x in painted), "painted across the residential road")
        self.assertEqual(xs[min(xs, key=lambda x: abs(x - 1000))], cr.WIDTH_MAX)
        self.assertLessEqual(xs[min(xs, key=lambda x: abs(x - 4000))], 4.0)
        self.assertLessEqual(xs[min(xs, key=lambda x: abs(x - 5600))], 6.5)
        self.assertTrue(all(len(pc["z"]) == len(pc["ll"]) for pc in got))
        # asked again: nothing new, nothing pending
        again = p.near(pts, 1.0, "Test", lat, lon, have, radius=4000)
        self.assertEqual((again["windows"], again["pending"]), ([], 0))


if __name__ == "__main__":
    unittest.main()
