"""The ground's surfaces along the course (gpsd/surfaces.py, terrain version 3): sand in dry washes, sandy canyon floors
and on beaches, mud on banks of water there all year, loose and packed dirt by the country, gravel in green country's
creek beds and over rock; nothing changed on paved roads or away from the course.

Pure: numpy only (test_paint.py checks the hook inside BeamNG.Earth's block surfaces).
"""
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(HERE))

try:
    import numpy as np
    HAVE_NP = True
except ImportError:
    HAVE_NP = False

if HAVE_NP:
    from gpsd import courseroads as cr
    from gpsd import relief as rf
    from gpsd import surfaces as sf

LAT0, LON0 = 31.02, -115.43
MATS = {"ASPHALT": 0, "GRASS": 1, "DUSTY": 2, "LOOSE": 3, "ROCK": 4, "SNOW": 5, "MUD": 6, "COBBLE": 7, "LAWN": 8,
        "DIRT": 9, "SAND": 10, "GRAVEL": 11}
NAMES = {v: k for k, v in MATS.items()}


def frame():
    kx = math.radians(1) * cr.R_EARTH * math.cos(math.radians(LAT0))
    ky = math.radians(1) * cr.R_EARTH

    def ll(x, y):
        return LAT0 + np.asarray(y, np.float64) / ky, LON0 + np.asarray(x, np.float64) / kx

    def xy(lat, lon):
        return (np.asarray(lon) - LON0) * kx, (np.asarray(lat) - LAT0) * ky
    return ll, xy


def world(tv=3):
    """6 km due east (x), the track along y = 0:
        0 - 1000      open desert (bare land)
        1200          a dry wash crosses (a stream mapped intermittent)
        1500 - 2500   a desert canyon (the ground rises 1.5 m per m from 6 m off the line)
        2600 - 3200   green country (grassland); 2900 a creek mapped intermittent
        3500          a stream there all year crosses (green country)
        4000 - 4500   a mapped dirt road the course follows (desert)
        4600 - 5000   a dry lake (mapped intermittent)
        5200 - 5600   the sea 40 m south (desert)
        5800          a paved road across"""
    ll, xy = frame()
    course = cr.Course([tuple(map(float, ll(x, 0.0))) for x in range(0, 6001, 50)], tv=tv)

    def road_fn(lat0, lon0, lat1, lon1, plane):
        out = []
        for xa, ya, xb, yb, hw, paved in ((4000, 0, 4500, 0, 3.0, 0), (5800, -300, 5800, 300, 4.0, 1)):
            (la, lo), (lb, lob) = ll(xa, ya), ll(xb, yb)
            ax, ay = plane.xy(float(la), float(lo))
            bx, by = plane.xy(float(lb), float(lob))
            out.append((ax, ay, bx, by, hw, paved))
        return out

    def ground(lat, lon):
        x, y = xy(np.asarray(lat, np.float64), np.asarray(lon, np.float64))
        canyon = (x > 1500) & (x < 2500)
        return np.where(canyon, np.maximum(0.0, np.abs(y) - 6.0) * 1.5, 0.0)

    def land(lat, lon):
        x, _ = xy(np.asarray(lat, np.float64), np.asarray(lon, np.float64))
        green = (x > 2550) & (x < 3700)
        return np.where(green, 30, 60).tolist()

    def lake(lat, lon):
        x, _ = xy(np.asarray(lat, np.float64), np.asarray(lon, np.float64))
        return ((x > 4600) & (x < 5000)).astype(float).tolist()

    def lonlat(pts):
        la, lo = ll(np.array([p[0] for p in pts], float), np.array([p[1] for p in pts], float))
        return np.stack([lo, la], 1)
    waters = [("wash", 2.0, False, lonlat([(1200, -500), (1200, 500)])),
              ("wash", 2.0, False, lonlat([(2900, -500), (2900, 500)])),
              ("bank", 2.0, False, lonlat([(3500, -500), (3500, 500)])),
              ("sea", 0.0, True, lonlat([(5150, -40), (5650, -40), (5650, -900), (5150, -900)]))]

    def waters_fn(lat0, lon0, lat1, lon1):
        return [w for w in waters if w[3][:, 0].max() >= lon0 and w[3][:, 0].min() <= lon1 and
                w[3][:, 1].max() >= lat0 and w[3][:, 1].min() <= lat1]
    profs = {k: rf.window_profile(course, k, [], road_fn, lambda la, lo: ground(la, lo).tolist(), lake, land,
                                  waters_fn) for k in range(course.nwin)}
    return ll, xy, course, profs, land


def earth_idx(xs, ys, land):
    """BeamNG.Earth's materials at the points: the land cover's (bare: loose, grass: grass), the track drawn as dirt
    (paint_roads), the paved road as asphalt."""
    ll, _ = frame()
    la, lo = ll(xs, ys)
    cls = np.asarray(land(la, lo))
    idx = np.where(cls == 30, MATS["GRASS"], MATS["LOOSE"])
    idx = np.where(np.abs(ys) <= 2.5, MATS["DIRT"], idx)
    idx = np.where(np.abs(xs - 5800) <= 4.0, MATS["ASPHALT"], idx)
    return idx.astype(np.uint8), la, lo


@unittest.skipUnless(HAVE_NP, "numpy")
class TestSurfaces(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        w = world()
        cls.course, cls.profs = w[2], w[3]
        cls.land = staticmethod(w[4])

    def at(self, x, ys):
        xs = np.full(len(ys), float(x))
        ys = np.asarray(ys, float)
        idx, la, lo = earth_idx(xs, ys, self.land)
        out = sf.course_surfaces(idx, la, lo, self.course, self.profs, MATS)
        return [NAMES[int(v)] for v in out]

    def test_desert_track(self):
        got = self.at(600, [0.0, 2.2, -3.0, 10.0, 40.0])
        self.assertEqual(got[0], "DUSTY", "the racing line packed")
        self.assertEqual(got[1], "LOOSE", "its sides loose")
        self.assertEqual(got[3:], ["LOOSE", "LOOSE"], "the desert beside: BeamNG.Earth's own")

    def test_dry_wash_is_sand(self):
        got = self.at(1200, [0.0, 3.0, -15.0, 30.0])
        self.assertEqual(got[:3], ["SAND", "SAND", "SAND"], "the wash across the track and beside it")
        self.assertEqual(got[3], "LOOSE", "past the corridor: as it was")
        self.assertEqual(self.at(1210, [0.0]), ["DUSTY"], "past the wash's width: the desert track again")

    def test_canyon_floor_is_sand(self):
        got = self.at(2000, [0.0, 4.0, 8.0, 25.0])
        self.assertEqual(got[:3], ["SAND", "SAND", "SAND"])
        self.assertEqual(got[3], "LOOSE", "up the canyon's side: as it was")

    def test_green_country(self):
        self.assertEqual(self.at(2700, [0.0, 2.0, 10.0]), ["DIRT", "DIRT", "GRASS"], "a track through grass: packed")
        self.assertEqual(self.at(2900, [0.0, 6.0]), ["GRAVEL", "GRAVEL"], "a creek bed in green country")

    def test_mud_by_water_all_year(self):
        got = self.at(3500, [0.0, 7.0])
        self.assertEqual(got, ["MUD", "MUD"])
        self.assertEqual(self.at(3520, [0.0]), ["DIRT"], "away from the bank")

    def test_followed_road_and_dry_lake_packed(self):
        self.assertEqual(self.at(4200, [0.0])[0], "DIRT", "a graded dirt road")
        self.assertEqual(self.at(4200, [2.7])[0], "LOOSE", "... its sides loose in the desert")
        self.assertEqual(self.at(4800, [0.0, 1.5]), ["DIRT", "DIRT"], "a dry lake bed: packed hard")

    def test_beach(self):
        self.assertEqual(self.at(5400, [0.0, -20.0]), ["SAND", "SAND"])
        self.assertEqual(self.at(5400, [19.0]), ["LOOSE"], "more than BEACH_M from the sea: as it was")

    def test_paved_and_far_untouched(self):
        self.assertEqual(self.at(5800, [0.0, 2.0]), ["ASPHALT", "ASPHALT"])
        ys = np.arange(-60.0, 61.0, 5.0)
        xs = np.full(len(ys), 600.0)
        idx, la, lo = earth_idx(xs, ys, self.land)
        out = sf.course_surfaces(idx, la, lo, self.course, self.profs, MATS)
        far = np.abs(ys) > 2.5 + sf.CORRIDOR_M
        self.assertTrue(np.array_equal(out[far], idx[far]))

    def test_older_versions_unchanged(self):
        _, _, old, profs, land = world(tv=2)
        xs, ys = np.full(5, 1200.0), np.array([0.0, 2.0, 5.0, 10.0, 15.0])
        idx, la, lo = earth_idx(xs, ys, land)
        self.assertTrue(np.array_equal(sf.course_surfaces(idx, la, lo, old, profs, MATS), idx))
        self.assertNotIn("waters", profs[0], "no new facts in an older version's windows")

    def test_the_same_whoever_asks(self):
        xs = np.arange(0.0, 6000.0, 7.0)
        ys = np.sin(xs / 50.0) * 20.0
        idx, la, lo = earth_idx(xs, ys, self.land)
        one = sf.course_surfaces(idx, la, lo, self.course, self.profs, MATS)
        part = sf.course_surfaces(idx[100:300], la[100:300], lo[100:300], self.course, self.profs, MATS)
        self.assertTrue(np.array_equal(one[100:300], part))

    def test_v4_no_scrub_on_a_bare_desert_track(self):
        """Terrain 4: BeamNG.Earth's ground cover grows on GRASS, LAWN and DUSTY: a track through bare desert carries
        none of them (terrain 3 packed its middle as DUSTY, and scrub grew along the racing line)."""
        _, _, c4, p4, land = world(tv=4)
        xs, ys = np.full(4, 600.0), np.array([0.0, 1.0, 2.2, 10.0])
        idx, la, lo = earth_idx(xs, ys, land)
        got = [NAMES[int(v)] for v in sf.course_surfaces(idx, la, lo, c4, p4, MATS)]
        self.assertEqual(got[0], "DIRT", "the racing line packed, bare")
        self.assertNotIn("DUSTY", got[:3])
        self.assertEqual(self.at(600, [0.0])[0], "DUSTY", "terrain 3 as it always was")

    def test_v4_plants_only_where_the_land_beside_has_them(self):
        _, _, c4, p4, land = world(tv=4)
        xs, ys = np.full(5, 2700.0), np.array([0.0, 1.0, 1.5, 2.2, 10.0])
        idx, la, lo = earth_idx(xs, ys, land)
        got = [NAMES[int(v)] for v in sf.course_surfaces(idx, la, lo, c4, p4, MATS)]
        self.assertEqual(got[:3], ["DIRT", "DIRT", "DIRT"], "the wheel paths bare")
        self.assertEqual(got[3], "LAWN", "grass over the track's edge in grassland")
        self.assertEqual(got[4], "GRASS", "beside it: as it was")

    def test_v4_two_track_middle(self):
        """A track wide enough for two wheel paths keeps a grassy hump between them on stretches that keep one (hashed
        along the course), the paths bare; shrubland's is scrub."""
        M = MATS
        n = 6
        ad = np.array([0.0, 0.5, 1.6, 2.4, 3.6, 0.0])
        hw = np.full(n, 4.0)
        track = ad <= hw + 0.3
        f = {"cover": np.ones(n), "grass": np.array([1, 1, 1, 1, 1, 0.0]), "road": np.zeros(n)}
        s = np.zeros(n)
        b = 0
        while not sf._lanes(np.array([b * sf.LANES_M + 1.0]))[0]:
            b += 1
        s[:] = b * sf.LANES_M + 1.0
        new = np.full(n, M["DIRT"])
        got = [NAMES[int(v)] for v in sf._cover(new.copy(), new.copy(), M, track, np.zeros(n, bool), ad, hw, f, s,
                                                  np.zeros(n, bool))]
        self.assertEqual(got, ["LAWN", "LAWN", "DIRT", "DIRT", "LAWN", "DUSTY"])
        while sf._lanes(np.array([b * sf.LANES_M + 1.0]))[0]:
            b += 1
        s[:] = b * sf.LANES_M + 1.0
        got = [NAMES[int(v)] for v in sf._cover(new.copy(), new.copy(), M, track, np.zeros(n, bool), ad, hw, f, s,
                                                  np.zeros(n, bool))]
        self.assertEqual(got[:4], ["DIRT"] * 4, "a stretch run bare wall to wall")
        share = np.mean(sf._lanes(np.arange(0, 200) * sf.LANES_M + 1.0))
        self.assertTrue(0.45 < share < 0.75, share)

    def test_water_kinds(self):
        self.assertEqual(sf.water_kind("stream", "stream", True, False, False), ("wash", 2.0))
        self.assertEqual(sf.water_kind("river", "river", False, False, False), ("bank", 7.0))
        self.assertEqual(sf.water_kind("lake", "lake", False, False, True), ("bank", 0.0))
        self.assertIsNone(sf.water_kind("lake", "lake", True, False, True), "a dry lake: the lake fact's")
        self.assertIsNone(sf.water_kind("stream", "ditch", False, False, False))
        self.assertEqual(sf.water_kind("ocean", "ocean", False, True, True), ("sea", 0.0))

    def test_clipping(self):
        ring = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float)
        c = sf._clip_ring(ring, (5, -1, 20, 20))
        self.assertAlmostEqual(c[:, 0].min(), 5.0)
        parts = sf._clip_line(np.array([[-5, 5], [15, 5], [15, 25]], float), (0, 0, 10, 10))
        self.assertEqual(len(parts), 1)
        self.assertTrue(np.allclose(parts[0], [[0, 5], [10, 5]]))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE_NP, "numpy")
class TestNaturalBoundaries(unittest.TestCase):
    """Terrain 14 (the user, 2026-11-12: "Can we do something to make the terrain transitions look more natural"): no
    blocks of one ground and another a few metres long along the track, and no ruler-straight boundaries."""

    def world(self, tv):
        ll, xy = frame()
        course = cr.Course([tuple(map(float, ll(x, 0.0))) for x in range(0, 3001, 50)], tv=tv)

        def land(lat, lon):         # scrubby desert, patches of grass every 20 m or so
            x, y = xy(np.asarray(lat, np.float64), np.asarray(lon, np.float64))
            grass = (np.floor((x + 3.0 * y) / 17.0) % 2 == 0) & (x > 500) & (x < 2500)
            return np.where(grass, 30, 60).tolist()
        profs = {k: rf.window_profile(course, k, [], lambda *a: [], lambda la, lo: [0.0] * len(la), None, land,
                                      lambda *a: []) for k in range(course.nwin)}
        return ll, course, profs

    def along(self, tv, y):
        ll, course, profs = self.world(tv)
        xs = np.arange(600.0, 2400.0, 2.0)
        ys = np.full(len(xs), y)
        la, lo = ll(xs, ys)
        idx = np.where(np.abs(ys) <= 2.5, MATS["DIRT"], MATS["LOOSE"]).astype(np.uint8)
        return sf.course_surfaces(idx, la, lo, course, profs, MATS)

    def test_facts_smoothed_along_the_course(self):
        """Land cover that changes every sample or two (a patchy WorldCover): terrain 14's dry-land share along the
        course varies far less from sample to sample than terrain 13's, so the track does not flip between packed dirt,
        loose dirt and plain dirt in blocks."""
        ll, xy = frame()

        def land(lat, lon):
            x, _ = xy(np.asarray(lat, np.float64), np.asarray(lon, np.float64))
            b = np.floor(x / 10.0).astype(np.int64)
            return np.where(rf._hash(b, np.zeros_like(b), 7) < 0.5, 30, 60).tolist()
        steps = {}
        for tv in (13, 14):
            course = cr.Course([tuple(map(float, ll(x, 0.0))) for x in range(0, 3001, 50)], tv=tv)
            prof = rf.window_profile(course, 1, [], lambda *a: [], lambda la, lo: [0.0] * len(la), None, land,
                                     lambda *a: [])
            steps[tv] = float(np.mean(np.abs(np.diff(prof["arid"]))))
        self.assertLess(steps[14], steps[13] * 0.6, steps)

    def test_edges_wander(self):
        ll, course, profs = self.world(14)
        xs = np.arange(100.0, 500.0, 2.0)          # (open desert: the track's loose sides, then the land's own)
        edge = []
        for x in xs:
            ys = np.arange(0.0, 8.0, 0.25)
            la, lo = ll(np.full(len(ys), x), ys)
            idx = np.where(ys <= 2.5, MATS["DIRT"], MATS["GRASS"]).astype(np.uint8)
            got = sf.course_surfaces(idx, la, lo, course, profs, MATS)
            edge.append(ys[np.flatnonzero(got == MATS["GRASS"])[0]])
        self.assertGreater(np.ptp(edge), 0.4, "the track's edge is not a ruler line")
        self.assertLess(np.ptp(edge), 2.5)

    def test_the_same_whoever_asks(self):
        ll, course, profs = self.world(14)
        xs = np.arange(600.0, 900.0, 3.0)
        ys = np.linspace(-6, 6, len(xs))
        la, lo = ll(xs, ys)
        idx = np.full(len(xs), MATS["LOOSE"], np.uint8)
        whole = sf.course_surfaces(idx, la, lo, course, profs, MATS)
        for i in (0, 13, 50, len(xs) - 1):
            one = sf.course_surfaces(idx[i:i + 1], la[i:i + 1], lo[i:i + 1], course, profs, MATS)
            self.assertEqual(int(one[0]), int(whole[i]))
