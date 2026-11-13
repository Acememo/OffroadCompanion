"""Terrain 13's shaping (gpsd/shaping.py): a dip under a low bridge the track passes under, a ramp where the course
comes off a paved road cut into the ground. Pure: numpy, with stand-ins for BeamNG.Earth's grading and elevation.
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
    from gpsd import shaping as sh

LAT0, LON0 = 31.02, -115.43


def frame():
    kx = math.radians(1) * cr.R_EARTH * math.cos(math.radians(LAT0))
    ky = math.radians(1) * cr.R_EARTH

    def ll(x, y):
        return LAT0 + np.asarray(y, np.float64) / ky, LON0 + np.asarray(x, np.float64) / kx

    def xy(lat, lon):
        return (np.asarray(lon) - LON0) * kx, (np.asarray(lat) - LAT0) * ky
    return ll, xy


def straight(tv=13, length=1000):
    ll, _ = frame()
    pts = [tuple(map(float, ll(x, 0.0))) for x in range(0, length + 1, 10)]
    return cr.Course(pts, 1.0, "Shaping", tv)


def profile(c, hw=3.0, road=None, rough=None, **extra):
    a, b = c.inner(0)
    n = b - a + 1
    p = {"algo": rf.ALGO, "a": a, "b": b, "hw": [hw] * n, "ctr": [0.0] * n,
         "rough": rough if rough is not None else [1.0] * n, "rock": [0.0] * n, "turn": [0.0] * n,
         "lake": [0.0] * n, "road": road if road is not None else [0.0] * n}
    p.update(extra)
    return {0: p}


@unittest.skipUnless(HAVE_NP, "numpy")
class TestUnderBridge(unittest.TestCase):
    """The user, 2026-11-12: "when the dirt path passes below a bridge make ample room with a big depression that goes
    down and up smoothly and leaves enough clearance for trophy trucks to pass under the bridge"."""

    def setUp(self):
        self.ll, self.xy = frame()
        self.c = straight()
        a = self.ll(500.0, -20.0)
        b = self.ll(500.0, 20.0)
        # a 40 m road bridge across the course at x 500, its ends' road 3 m over the flat ground
        self.x = {"s": 500.0, "sin": 1.0, "a": [float(a[1]), float(a[0])], "b": [float(b[1]), float(b[0])],
                  "hw": 5.0, "len": 40.0, "id": "bridge", "f": 0}
        self.profs = profile(self.c, ux=[self.x])

    def elev(self, lat, lon):
        return np.zeros(np.size(lat))

    def grade(self, lat, lon, nat):
        x, y = self.xy(np.asarray(lat).ravel(), np.asarray(lon).ravel())
        return np.where(np.abs(y) >= 19.0, 3.0, 0.0) + 0.0 * x

    def dz_line(self, xs, y=0.0):
        la, lo = self.ll(np.asarray(xs, np.float64), np.full(len(xs), y))
        return sh.shape(self.c, self.profs, la, lo, np.zeros(len(xs)), self.grade, self.elev)

    def test_room_under_the_deck(self):
        want = 3.0 - sh.DECK_UNDER_M - sh.UNDER_CLEAR_M         # the deck's underside less the clearance
        xs = np.arange(300.0, 700.1, 1.0)
        dz = self.dz_line(xs)
        self.assertAlmostEqual(float(dz[xs == 500.0][0]), want, places=2)
        floor = (self.x["hw"] + 1.0 + sh.DIP_FLOOR_PAD_M)
        self.assertTrue(np.allclose(dz[np.abs(xs - 500.0) <= floor], want), "flat under the deck and past it")
        self.assertTrue(np.all(np.abs(np.diff(dz)) <= sh.DIP_GRADE * 1.0 + 1e-6), "no steeper than DIP_GRADE")
        self.assertEqual(float(dz[0]), 0.0)
        self.assertEqual(float(dz[-1]), 0.0)

    def test_sides_slope_back(self):
        ys = np.arange(0.0, 40.0, 0.5)
        la, lo = self.ll(np.full(len(ys), 500.0), ys)
        dz = sh.shape(self.c, self.profs, la, lo, np.zeros(len(ys)), self.grade, self.elev)
        self.assertLess(float(dz[0]), -4.0)
        self.assertTrue(np.all(np.diff(dz) >= -1e-9), "rising back out across the track")
        self.assertEqual(float(dz[-1]), 0.0)

    def test_none_where_high_enough_or_flattened_or_on_a_road(self):
        high = dict(self.x)
        self.profs = profile(self.c, ux=[high])
        self.grade = lambda la, lo, nat: np.where(np.abs(self.xy(np.asarray(la), np.asarray(lo))[1]) >= 19.0,
                                                  9.0, 0.0)
        self.assertFalse(np.any(self.dz_line(np.arange(400.0, 600.0, 5.0))), "a deck 9 m up: room enough")
        flat = dict(self.x, f=1)
        self.grade = TestUnderBridge.grade.__get__(self)
        self.profs = profile(self.c, ux=[flat])
        self.assertFalse(np.any(self.dz_line(np.arange(400.0, 600.0, 5.0))), "made a crossing at grade: no deck")
        n = self.c.inner(0)[1] + 1
        self.profs = profile(self.c, road=[1.0] * n, rough=[0.0] * n, ux=[self.x])
        self.assertFalse(np.any(self.dz_line(np.arange(400.0, 600.0, 5.0))), "on a paved road: BeamNG.Earth's")
        self.profs = profile(self.c, road=[1.0] * n, ux=[self.x])
        self.assertTrue(np.any(self.dz_line(np.arange(400.0, 600.0, 5.0))), "a dirt road it follows: dug too")

    def test_older_terrain_untouched(self):
        self.c = straight(tv=12)
        self.assertFalse(np.any(self.dz_line(np.arange(400.0, 600.0, 5.0))))

    def test_crossings_from_the_map(self):
        """bridge_crossings: where a bridge's line crosses the course, its ends and width."""
        c = self.c
        a, b = self.ll(500.0, -20.0), self.ll(500.0, 20.0)

        class F:
            ids = ["w1", "w2"]
            attrs = {"class": np.array(["primary", "footway"])}

            def __len__(self):
                return 2

        class R:
            @staticmethod
            def level_ranges(f, i):
                return [(0.0, 1.0, "bridge")]

            @staticmethod
            def bridge_parts(f, i):
                return [np.array([[float(a[1]), float(a[0])], [float(b[1]), float(b[0])]])]

        class Spec:
            width = 10.0
        xs = sh.bridge_crossings(R, F(), [Spec(), Spec()], c, 0)
        self.assertEqual(len(xs), 1, "the footbridge left out")
        self.assertAlmostEqual(xs[0]["s"], 500.0, delta=0.2)
        self.assertGreater(xs[0]["sin"], 0.99)
        self.assertEqual(xs[0]["hw"], 5.0)
        merged = sh.merge_crossings([xs, [dict(xs[0], len=10.0)]])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["len"], xs[0]["len"])


@unittest.skipUnless(HAVE_NP, "numpy")
class TestRoadEntrance(unittest.TestCase):
    """The user, 2026-11-12: "some parts of the road have dirt road entrances that are way too steep"."""

    def setUp(self):
        self.ll, self.xy = frame()
        self.c = straight()
        # the course on a paved road up to x 500 (sample 50), on its own track after; the road cut 4 m into the ground:
        # its level to x 504, the cut bank up to 4 m by x 506
        n = self.c.inner(0)[1] + 1
        near = [i <= 50 for i in range(n)]
        self.jn = sh.joins(self.c, 0, near)
        self.profs = profile(self.c, jn=self.jn)

    def elev(self, lat, lon):
        return np.zeros(np.size(lat))

    def grade(self, lat, lon, nat):
        x, _ = self.xy(np.asarray(lat).ravel(), np.asarray(lon).ravel())
        return np.clip((x - 504.0) * 2.0, 0.0, 4.0)

    def test_the_join_found(self):
        self.assertEqual(self.jn, [[50, 1]])
        self.assertEqual(sh.joins(self.c, 0, [i >= 30 for i in range(101)]), [[30, -1]])

    def test_a_ramp_through_the_bank(self):
        xs = np.arange(490.0, 640.0, 0.5)
        la, lo = self.ll(xs, np.zeros(len(xs)))
        g = self.grade(la, lo, None)
        z = g + sh.shape(self.c, self.profs, la, lo, g, self.grade, self.elev)
        slope = np.abs(np.diff(z)) / 0.5
        self.assertLessEqual(float(slope.max()), sh.JOIN_GRADE * 1.05, "no steeper than JOIN_GRADE")
        self.assertAlmostEqual(float(z[xs == 500.0][0]), 0.0, places=6, msg="the road itself untouched")
        self.assertAlmostEqual(float(z[-1]), 4.0, places=6, msg="back on its own ground")
        # across: the notch's sides slope back to the bank
        ys = np.arange(0.0, 30.0, 0.5)
        la, lo = self.ll(np.full(len(ys), 515.0), ys)
        g = self.grade(la, lo, None)
        z = g + sh.shape(self.c, self.profs, la, lo, g, self.grade, self.elev)
        self.assertLess(float(z[0]), 3.0)
        self.assertAlmostEqual(float(z[-1]), 4.0, places=6)
        self.assertTrue(np.all(np.diff(z) >= -1e-9))

    def test_gentle_entrance_left_alone(self):
        self.grade = lambda la, lo, nat: np.clip((self.xy(np.asarray(la), np.asarray(lo))[0] - 504.0) * 0.08,
                                                 0.0, 4.0)
        xs = np.arange(490.0, 640.0, 2.0)
        la, lo = self.ll(xs, np.zeros(len(xs)))
        self.assertFalse(np.any(sh.shape(self.c, self.profs, la, lo, self.grade(la, lo, None), self.grade,
                                         self.elev)))

    def test_the_same_whatever_else_is_asked(self):
        """A point's height never depends on the others asked with it (the physics block, the road tiles and the ground
        tiles agree)."""
        xs = np.arange(490.0, 640.0, 3.0)
        la, lo = self.ll(xs, np.full(len(xs), 2.0))
        g = self.grade(la, lo, None)
        whole = sh.shape(self.c, self.profs, la, lo, g, self.grade, self.elev, cache={})
        for i in (0, 7, 20, len(xs) - 1):
            one = sh.shape(self.c, self.profs, la[i:i + 1], lo[i:i + 1], g[i:i + 1], self.grade, self.elev, cache={})
            self.assertEqual(float(one[0]), float(whole[i]))



@unittest.skipUnless(HAVE_NP, "numpy")
class TestWhicheverWindows(unittest.TestCase):
    """A point's shape never depends on which relief windows were at hand: the windows next to them (around) give the
    facts its join or bridge reads past them (1.7.14: the ground tiles and the physics block disagreed, the user
    2026-11-12: "it appears as if the new fixes are non collidable")."""

    def test_the_same_with_the_neighbours(self):
        ll, xy = frame()
        c = straight(length=2000)
        # the paved road to sample 95 (window 0), then the track; window 0's track 8 m wide, window 1's 14 m, its
        # middle 3 m left of the line
        near = [i <= 95 for i in range(c.context(0)[0], c.context(0)[1] + 1)]
        jn0 = sh.joins(c, 0, near)
        a0, b0 = c.inner(0)
        a1, b1 = c.inner(1)
        p0 = profile(c, hw=4.0, jn=jn0)[0]
        p1 = {"algo": rf.ALGO, "a": a1, "b": b1, "hw": [7.0] * (b1 - a1 + 1), "ctr": [3.0] * (b1 - a1 + 1),
              "rough": [1.0] * (b1 - a1 + 1), "rock": [0.0] * (b1 - a1 + 1), "turn": [0.0] * (b1 - a1 + 1),
              "lake": [0.0] * (b1 - a1 + 1), "road": [0.0] * (b1 - a1 + 1), "jn": jn0}

        def grade(lat, lon, nat):
            x, y = xy(np.asarray(lat).ravel(), np.asarray(lon).ravel())
            return np.clip((x - 954.0) * 2.0, 0.0, 4.0) + 0.05 * y

        def elev(lat, lon):
            return np.zeros(np.size(lat))
        xs = np.arange(1000.0, 1060.0, 2.0)
        la, lo = ll(xs, np.full(len(xs), 1.0))
        g = grade(la, lo, None)
        both = sh.shape(c, {0: p0, 1: p1}, la, lo, g, grade, elev, cache={})
        self.assertTrue(np.any(both), "the ramp reaches into window 1")
        alone = sh.shape(c, {1: p1}, la, lo, g, grade, elev, cache={}, around={0: p0})
        self.assertTrue(np.array_equal(both, alone))
        self.assertEqual(sh.neighbours(c, [1]), [0])
        self.assertEqual(sh.neighbours(c, [0, 1]), [])


@unittest.skipUnless(HAVE_NP, "numpy")
class TestEarthworks(unittest.TestCase):
    """Terrain 15 (the user, 2026-11-12: "it should not affect the road and needs to be smoother than a huge hole";
    "the bridges are having enough clearance on the middle not on the edges"): the ground cut (or filled) to a design
    surface, flat across the track and past it, its sides sloping 1:3 back to the ground: never a pit or a trench."""

    def setUp(self):
        self.ll, self.xy = frame()
        self.c = straight(tv=15)

    def elev(self, lat, lon):
        return np.zeros(np.size(lat))

    def cut_grade(self, lat, lon, nat):
        # the paved road to x 500, cut 4 m into a hill rising 0.25 per m to the left of the course (a hillside)
        x, y = self.xy(np.asarray(lat).ravel(), np.asarray(lon).ravel())
        return np.clip((x - 504.0) * 2.0, 0.0, 4.0) + np.maximum(0.0, y) * 0.25 * (x > 504.0)

    def test_ramp_no_pit(self):
        n = self.c.inner(0)[1] + 1
        profs = profile(self.c, jn=sh.joins(self.c, 0, [i <= 50 for i in range(n)]))
        xs = np.arange(490.0, 640.0, 0.5)
        la, lo = self.ll(xs, np.zeros(len(xs)))
        g = self.cut_grade(la, lo, None)
        z = g + sh.shape(self.c, profs, la, lo, g, self.cut_grade, self.elev)
        self.assertLessEqual(float((np.abs(np.diff(z)) / 0.5).max()), sh.JOIN15_GRADE * 1.05, "the ramp")
        self.assertAlmostEqual(float(z[0]), 0.0, places=6, msg="the road untouched")
        ramp = dict(zip(xs.tolist(), z.tolist()))
        for x in (510.0, 525.0, 540.0):
            ys = np.arange(-30.0, 30.0, 0.5)
            la, lo = self.ll(np.full(len(ys), x), ys)
            g = self.cut_grade(la, lo, None)
            zz = g + sh.shape(self.c, profs, la, lo, g, self.cut_grade, self.elev)
            self.assertGreaterEqual(float(zz.min()), ramp[x] - 1e-6, f"no pit below the ramp's line at x {x}")
            self.assertLessEqual(float((np.abs(np.diff(zz)) / 0.5).max()), 0.6, f"its sides gentle at x {x}")
            self.assertTrue(np.all(zz <= g + 1e-9), "only cut here (the ground above the road)")

    def test_dip_room_under_the_whole_deck(self):
        ll = self.ll
        a, b = ll(500.0, -40.0), ll(500.0, 40.0)
        x = {"s": 500.0, "sin": 1.0, "a": [float(a[1]), float(a[0])], "b": [float(b[1]), float(b[0])], "hw": 5.0,
             "len": 80.0, "id": "bridge", "f": 0}
        profs = profile(self.c, ux=[x])

        def grade(lat, lon, nat):
            xx, yy = self.xy(np.asarray(lat).ravel(), np.asarray(lon).ravel())
            return np.where(np.abs(yy) >= 39.0, 3.0, 0.0) + 0.05 * yy      # (the ground tilted across)
        floor = (3.0 - 0.05 * 40.0) - sh.DECK_UNDER_M - sh.UNDER_CLEAR_M     # (the lower end's road)
        ys = np.arange(-30.0, 30.1, 0.5)
        la, lo = ll(np.full(len(ys), 500.0), ys)
        g = grade(la, lo, None)
        z = g + sh.shape(self.c, profs, la, lo, g, grade, self.elev)
        edge = np.abs(ys) <= 3.0 + sh.FLAT15_DIP_M                 # (the track's half width 3 m + the flat)
        self.assertTrue(np.allclose(z[edge], floor), "the floor's clearance across the track and past it")
        self.assertLessEqual(float((np.abs(np.diff(z)) / 0.5).max()), sh.SIDE15 + 0.05 + 1e-6, "gentle sides")
        # along: at the deck's edges (its half width 5 m + 1 m parapet) the floor too
        xs = np.array([494.0, 506.0])
        la, lo = ll(xs, np.zeros(2))
        g = grade(la, lo, None)
        z = g + sh.shape(self.c, profs, la, lo, g, grade, self.elev)
        self.assertTrue(np.allclose(z, floor, atol=1e-6))

    def test_the_same_change_whatever_ground_the_caller_has(self):
        """The change is worked out on the probes' own ground: a caller whose heights differ from it (a far ground
        tile's coarser DEM, BeamNG.Earth's roughening of the land) gets the same change, never a spike or a pit
        (1.7.17, the user 2026-11-12: a row of tall spikes beside the road)."""
        n = self.c.inner(0)[1] + 1
        profs = profile(self.c, jn=sh.joins(self.c, 0, [i <= 50 for i in range(n)]))
        gx, gy = np.meshgrid(np.arange(490.0, 600.0, 3.0), np.arange(-25.0, 25.0, 3.0))
        la, lo = self.ll(gx.ravel(), gy.ravel())
        g = self.cut_grade(la, lo, None)
        mine = sh.shape(self.c, profs, la, lo, g, self.cut_grade, self.elev, cache={})
        coarse = g + 3.0 * np.sin(gx.ravel() / 7.0) + 1.5                 # (another ground, metres off)
        theirs = sh.shape(self.c, profs, la, lo, coarse, self.cut_grade, self.elev, cache={})
        self.assertTrue(np.any(mine))
        self.assertTrue(np.array_equal(mine, theirs))


@unittest.skipUnless(HAVE_NP, "numpy")
class TestDecks(unittest.TestCase):
    """Terrain 16 (the user, 2026-11-12: "Bridge doesn't have the dip to clear; there is no terrain long dip under
    it"): a floor under every stretch a deck reaches over, beside the course as well as across it, in a town too."""

    def setUp(self):
        self.ll, self.xy = frame()
        self.c = straight(tv=16)

    def elev(self, lat, lon):
        return np.zeros(np.size(lat))

    def grade(self, lat, lon, nat):
        x, y = self.xy(np.asarray(lat).ravel(), np.asarray(lon).ravel())
        ends = ((np.abs(x - 380.0) < 3.0) | (np.abs(x - 620.0) < 3.0)) & (np.abs(y - 9.0) < 3.0)
        return np.where(ends, 3.0, 0.0)

    def deck(self, **kw):
        """A road on a deck from x 380 to 620 running beside the course, its middle 9 m to the left (half width 5 m:
        its edge right over the track's)."""
        class F:
            ids = ["deck"]
            attrs = {"class": np.array(["primary"])}

            def __len__(self):
                return 1
        a, b = self.ll(380.0, 9.0), self.ll(620.0, 9.0)

        class R:
            @staticmethod
            def level_ranges(f, i):
                return [(0.0, 1.0, "bridge")]

            @staticmethod
            def bridge_parts(f, i):
                return [np.array([[float(a[1]), float(a[0])], [float(b[1]), float(b[0])]])]

        class Spec:
            width = 10.0
        ud = sh.bridge_near(R, F(), [Spec()], self.c, 0)
        for x in ud:
            x["f"] = 0
            x.pop("i")
        n = self.c.inner(0)[1] + 1
        return profile(self.c, ud=ud, pv=kw.get("pv", [0.0] * n))

    def test_floor_beside_and_under(self):
        profs = self.deck()
        ud = profs[0]["ud"]
        self.assertEqual(len(ud), 1)
        self.assertLess(ud[0]["s0"], 385.0)
        self.assertGreater(ud[0]["s1"], 615.0)
        zT = 3.0 - sh.DECK_UNDER_M - sh.UNDER_CLEAR_M
        xs = np.arange(300.0, 700.0, 2.0)
        la, lo = self.ll(xs, np.zeros(len(xs)))
        g = self.grade(la, lo, None)
        z = g + sh.shape(self.c, profs, la, lo, g, self.grade, self.elev)
        under = (xs >= 380.0) & (xs <= 620.0)
        self.assertTrue(np.allclose(z[under], zT), "the floor all along the deck")
        self.assertLessEqual(float((np.abs(np.diff(z)) / 2.0).max()), sh.DIP_GRADE * 1.05)
        # across: under the deck's edge (the track's left side) the floor too
        ys = np.arange(0.0, 9.1, 0.5)
        la, lo = self.ll(np.full(len(ys), 500.0), ys)
        g = self.grade(la, lo, None)
        z = g + sh.shape(self.c, profs, la, lo, g, self.grade, self.elev)
        self.assertTrue(np.allclose(z, zT))

    def test_not_on_a_paved_road(self):
        n = self.c.inner(0)[1] + 1
        profs = self.deck(pv=[1.0] * n)
        xs = np.arange(300.0, 700.0, 5.0)
        la, lo = self.ll(xs, np.zeros(len(xs)))
        g = self.grade(la, lo, None)
        self.assertFalse(np.any(sh.shape(self.c, profs, la, lo, g, self.grade, self.elev)))

    def test_older_versions_use_crossings_only(self):
        self.c = straight(tv=15)
        profs = self.deck()
        xs = np.arange(300.0, 700.0, 5.0)
        la, lo = self.ll(xs, np.zeros(len(xs)))
        g = self.grade(la, lo, None)
        self.assertFalse(np.any(sh.shape(self.c, profs, la, lo, g, self.grade, self.elev)), "no crossing: none")


def all_profiles(c, hw=3.0, **perwin):
    """Every window's profile of course c (flat, rough dirt), extra fields per window: perwin[name] = {k: value}."""
    out = {}
    for k in range(c.nwin):
        a, b = c.inner(k)
        n = b - a + 1
        p = {"algo": rf.ALGO, "a": a, "b": b, "hw": [hw] * n, "ctr": [0.0] * n, "rough": [1.0] * n,
             "rock": [0.0] * n, "turn": [0.0] * n, "lake": [0.0] * n, "road": [0.0] * n, "pv": [0.0] * n}
        for name, by in perwin.items():
            if k in by:
                p[name] = by[k]
        out[k] = p
    return out


def deck_near(c, k, a_xy, b_xy, ll, width=10.0, bid="deck"):
    """bridge_near's stretches of window k for one road deck from a_xy to b_xy (plane m)."""
    class F:
        ids = [bid]
        attrs = {"class": np.array(["primary"])}

        def __len__(self):
            return 1
    a, b = ll(*a_xy), ll(*b_xy)

    class R:
        @staticmethod
        def level_ranges(f, i):
            return [(0.0, 1.0, "bridge")]

        @staticmethod
        def bridge_parts(f, i):
            return [np.array([[float(a[1]), float(a[0])], [float(b[1]), float(b[0])]])]

    class Spec:
        pass
    Spec.width = width
    ud = sh.bridge_near(R, F(), [Spec()], c, k)
    for x in ud:
        x["f"] = 0
        x.pop("i")
    return ud


@unittest.skipUnless(HAVE_NP, "numpy")
class TestAlongTheLine(unittest.TestCase):
    """Terrain 17 (the user, 2026-11-13: "The spiky section is worse"): the dips and ramps worked out along the
    track's own line, never from the course sample nearest a point. At a hairpin by a bridge, terrain 16 cut a point
    nearer the dug leg down to the dip and left the next one, nearer the other leg, as it was: a wall metres high."""

    def setUp(self):
        self.ll, self.xy = frame()
        ll = self.ll
        # east along y 0 to x 600, a hairpin (radius 15), back west along y 30
        pts = [(x, 0.0) for x in range(0, 600, 10)]
        pts += [(600.0 + 15.0 * math.sin(t), 15.0 - 15.0 * math.cos(t)) for t in np.linspace(0, math.pi, 6)]
        pts += [(x, 30.0) for x in range(590, -1, -10)]
        self.pts = [tuple(map(float, ll(x, y))) for x, y in pts]

    def course(self, tv):
        return cr.Course(self.pts, 1.0, "Hairpin", tv)

    def elev(self, lat, lon):
        return np.zeros(np.size(lat))

    def grade(self, lat, lon, nat):
        # the land rising 0.4 per m from the first leg's left edge to the hairpin's other leg; the bridge's ends 3 m up
        x, y = self.xy(np.asarray(lat).ravel(), np.asarray(lon).ravel())
        ends = (np.abs(x - 560.0) < 3.0) & ((np.abs(y + 20.0) < 3.0) | (np.abs(y - 8.0) < 3.0))
        return np.where(ends, 3.0, 0.4 * np.clip(y - 6.0, 0.0, 30.0))

    def profiles(self, c):
        ud = {k: deck_near(c, k, (560.0, -20.0), (560.0, 8.0), self.ll) for k in range(c.nwin)}
        return all_profiles(c, ud={k: v for k, v in ud.items() if v})

    def surface(self, tv, step=1.0):
        c = self.course(tv)
        profs = self.profiles(c)
        gx, gy = np.meshgrid(np.arange(520.0, 640.0, step), np.arange(-15.0, 45.0, step))
        la, lo = self.ll(gx.ravel(), gy.ravel())
        g = self.grade(la, lo, None)
        ks = [k for k in profs if profs[k].get("ud")]
        near = {k: profs[k] for k in ks}
        around = {k: profs[k] for k in sh.neighbours(c, ks)}
        dz = sh.shape(c, near, la, lo, g, self.grade, self.elev, around=around, cache={})
        return gx, gy, (g + dz).reshape(gx.shape), dz.reshape(gx.shape)

    def test_no_walls_at_the_hairpin(self):
        gx, gy, z, dz = self.surface(17)
        self.assertLess(float(dz.min()), -3.0, "the dip dug")
        jump = max(float(np.abs(np.diff(z, axis=0)).max()), float(np.abs(np.diff(z, axis=1)).max()))
        self.assertLess(jump, 1.6, "no wall anywhere: every slope under ~1:0.6")
        _, _, z16, _ = self.surface(16)
        jump16 = max(float(np.abs(np.diff(z16, axis=0)).max()), float(np.abs(np.diff(z16, axis=1)).max()))
        self.assertGreater(jump16, 3.0, "(terrain 16 stood one here, and still does)")

    def test_the_floor_under_the_deck(self):
        c = self.course(17)
        profs = self.profiles(c)
        zT = 3.0 - sh.DECK_UNDER_M - sh.UNDER_CLEAR_M
        xs = np.arange(550.0, 571.0, 1.0)
        la, lo = self.ll(xs, np.zeros(len(xs)))
        g = self.grade(la, lo, None)
        z = g + sh.shape(c, profs, la, lo, g, self.grade, self.elev, cache={})
        self.assertTrue(np.allclose(z, zT, atol=1e-6), z)

    def test_the_same_whoever_asks(self):
        """A point's change is the same asked alone, in a row or with the whole grid."""
        c = self.course(17)
        profs = self.profiles(c)
        gx, gy = np.meshgrid(np.arange(540.0, 630.0, 3.0), np.arange(-10.0, 40.0, 3.0))
        la, lo = self.ll(gx.ravel(), gy.ravel())
        g = self.grade(la, lo, None)
        whole = sh.shape(c, profs, la, lo, g, self.grade, self.elev, cache={})
        bits = np.concatenate([sh.shape(c, profs, la[i:i + 7], lo[i:i + 7], g[i:i + 7] + 1.0, self.grade, self.elev,
                                        cache={}) for i in range(0, len(la), 7)])
        self.assertTrue(np.any(whole))
        self.assertTrue(np.allclose(whole, bits, atol=1e-9))

    def test_a_ramp_meets_the_road_and_its_sides_slope(self):
        c = straight(tv=17)

        def cut_grade(lat, lon, nat):
            x, y = self.xy(np.asarray(lat).ravel(), np.asarray(lon).ravel())
            return np.clip((x - 504.0) * 2.0, 0.0, 4.0) + np.maximum(0.0, y) * 0.25 * (x > 504.0)
        n = c.inner(0)[1] + 1
        profs = all_profiles(c, jn={0: sh.joins(c, 0, [i <= 50 for i in range(n)])})
        xs = np.arange(490.0, 640.0, 0.5)
        la, lo = self.ll(xs, np.zeros(len(xs)))
        g = cut_grade(la, lo, None)
        z = g + sh.shape(c, profs, la, lo, g, cut_grade, self.elev, cache={})
        self.assertLessEqual(float((np.abs(np.diff(z)) / 0.5).max()), sh.JOIN15_GRADE * 1.05, "the ramp")
        self.assertAlmostEqual(float(z[0]), 0.0, places=6, msg="the road untouched")
        gx, gy = np.meshgrid(np.arange(500.0, 600.0, 1.0), np.arange(-30.0, 30.0, 1.0))
        la, lo = self.ll(gx.ravel(), gy.ravel())
        g = cut_grade(la, lo, None)
        zz = (g + sh.shape(c, profs, la, lo, g, cut_grade, self.elev, cache={})).reshape(gx.shape)
        self.assertTrue(np.all(zz <= g.reshape(gx.shape) + 1e-9), "only cut here (the ground above the road)")
        self.assertLess(float(np.abs(np.diff(zz, axis=0)).max()), 1.2, "its sides no wall")


@unittest.skipUnless(HAVE_NP, "numpy")
class TestDeckStretchesMerged(unittest.TestCase):
    def test_overlapping_stretches_one(self):
        a = {"id": "b", "s0": 100.0, "s1": 180.0, "a": [0, 0], "b": [1, 1], "hw": 5.0, "len": 80.0, "f": 0}
        cut = dict(a, s0=150.0, s1=180.0, len=30.0, a=[2, 2])
        other = dict(a, id="c", s0=400.0, s1=420.0)
        far = dict(a, s0=600.0, s1=620.0)
        got = sh.decks17([[cut], [a, other], [far]])
        self.assertEqual([(x["id"], x["s0"], x["s1"]) for x in got],
                         [("b", 100.0, 180.0), ("c", 400.0, 420.0), ("b", 600.0, 620.0)])
        self.assertEqual(got[0]["a"], [0, 0], "the longest part's ends")
        self.assertEqual(sh.decks17([[cut], [a]]), sh.decks17([[a], [cut]]))


@unittest.skipUnless(HAVE_NP, "numpy")
class TestBridgesKept(unittest.TestCase):
    """Terrain 17 (the user, 2026-11-13: "the bridge should be on top and dirt road below"): a bridge the course goes
    under is kept, dug under; only one too low over the paved road the course is on is made a ground road."""

    def setUp(self):
        self.ll, _ = frame()
        la, lo = self.ll(np.arange(0.0, 1001.0, 10.0), np.zeros(101))
        self.lines = [np.stack([lo, la], 1)]
        a, b = self.ll(500.0, -20.0), self.ll(500.0, 20.0)

        class F:
            ids = ["br"]
            attrs = {"class": np.array(["residential"])}

            def __len__(self):
                return 1

        class R:
            @staticmethod
            def level_ranges(f, i):
                return [(0.0, 1.0, "bridge")]

            @staticmethod
            def bridge_parts(f, i):
                return [np.array([[float(a[1]), float(a[0])], [float(b[1]), float(b[0])]])]
        self.F, self.R = F(), R

    def ground(self, paved):
        la, lo = self.ll(np.array([400.0, 600.0]), np.zeros(2))
        row = [float(lo[0]), float(la[0]), float(lo[1]), float(la[1]), 4.0, float(paved)]
        return lambda lon, lat: np.array([row])

    def flat(self, ground=None, keep=False):
        from gpsd import corridor
        return corridor.bridges_to_flatten(self.R, self.F, self.lines, ground,
                                           elev_fn=lambda la, lo: np.zeros(np.size(la)), keep_under=keep)

    def test_off_the_roads(self):
        self.assertEqual(self.flat(), [0], "(before: a crossing at grade)")
        self.assertEqual(self.flat(keep=True), [], "kept")

    def test_over_a_dirt_road(self):
        self.assertEqual(self.flat(self.ground(0)), [0], "(before: too low over the road, at grade)")
        self.assertEqual(self.flat(self.ground(0), keep=True), [], "kept")

    def test_too_low_over_a_paved_road(self):
        self.assertEqual(self.flat(self.ground(1), keep=True), [0])

    def test_terrain_18_kept_only_standing_over_the_course(self):
        """(terrain 18) Kept where the deck can stand DECK18_OVER_M over the course's ground; lower, the course meets
        it at its own height: a crossing at grade again."""
        from gpsd import corridor
        def run(elev):
            return corridor.bridges_to_flatten(self.R, self.F, self.lines, None, elev_fn=elev, keep_under=True,
                                               keep_from_m=sh.DECK18_OVER_M)
        flat = lambda la, lo: np.zeros(np.size(la))
        _, xy = frame()

        def creek(la, lo):
            x, y = xy(np.asarray(la, np.float64), np.asarray(lo, np.float64))
            return np.where((np.abs(y) < 12.0) & (np.abs(x - 500.0) < 30.0), -5.0, 0.0)
        self.assertEqual(run(flat), [0], "on the flat (its deck a metre over the course): at grade")
        self.assertEqual(run(creek), [], "over the creek the course runs in: kept")


@unittest.skipUnless(HAVE_NP, "numpy")
class TestAtGrade(unittest.TestCase):
    """Terrain 18 (the user, 2026-11-13, 1.7.20's pits by bridges' ends: "it seriously affected negativity on other
    parts"): dug only where the deck stands over the track; beside or across a bridge's end, nothing."""

    def setUp(self):
        self.ll, self.xy = frame()

    def elev(self, lat, lon):
        return np.zeros(np.size(lat))

    def grade_with(self, ends_z, x0, x1):
        def grade(lat, lon, nat):
            x, y = self.xy(np.asarray(lat).ravel(), np.asarray(lon).ravel())
            ends = ((np.abs(x - x0) < 3.0) | (np.abs(x - x1) < 3.0)) & (np.abs(y - 9.0) < 3.0)
            return np.where(ends, ends_z, 0.0)
        return grade

    def profs(self, c, x0, x1):
        return all_profiles(c, ud={k: v for k in range(c.nwin)
                                   for v in [deck_near(c, k, (x0, 9.0), (x1, 9.0), self.ll)] if v})

    def run_line(self, tv, ends_z, x0, x1):
        c = straight(tv=tv)
        grade = self.grade_with(ends_z, x0, x1)
        xs = np.arange(x0 - 150.0, x1 + 150.0, 2.0)
        la, lo = self.ll(xs, np.zeros(len(xs)))
        return xs, sh.shape(c, self.profs(c, x0, x1), la, lo, np.zeros(len(xs)), grade, self.elev, cache={})

    def test_a_deck_over_the_track_dug_under(self):
        xs, dz = self.run_line(18, 3.0, 380.0, 620.0)
        under = (xs >= 380.0) & (xs <= 620.0)
        self.assertTrue(np.allclose(dz[under], 3.0 - sh.DECK_UNDER_M - sh.UNDER_CLEAR_M), "the floor all along")

    def test_a_short_bridge_at_the_tracks_height_left(self):
        xs, dz = self.run_line(18, 0.5, 480.0, 520.0)
        self.assertFalse(np.any(dz), "the course meets the deck at its own height: nothing dug")
        _, dz17 = self.run_line(17, 0.5, 480.0, 520.0)
        self.assertLess(float(dz17.min()), -5.0, "(terrain 17 dug a pit there, and still does)")

    def test_a_long_low_bridge_only_where_it_stands_over(self):
        xs, dz = self.run_line(18, 1.0, 300.0, 700.0)
        floor = 1.0 - sh.DECK_UNDER_M - sh.UNDER_CLEAR_M
        self.assertTrue(np.all(dz[(xs >= 300.0) & (xs <= 312.0)] > floor + 0.1), "by its end: the ramp down to it")
        self.assertTrue(np.allclose(dz[(xs >= 330.0) & (xs <= 670.0)], floor), "the floor where it stands over")
        self.assertTrue(np.all(dz[(xs >= 450.0) & (xs <= 550.0)] < -1.0), "under its middle: dug")

    def test_the_parts_add_up(self):
        c = straight(tv=18)
        grade = self.grade_with(3.0, 380.0, 620.0)
        n = c.inner(0)[1] + 1
        profs = self.profs(c, 380.0, 620.0)
        profs[0]["jn"] = sh.joins(c, 0, [i <= 20 for i in range(n)])
        gx, gy = np.meshgrid(np.arange(150.0, 700.0, 4.0), np.arange(-30.0, 30.0, 4.0))
        la, lo = self.ll(gx.ravel(), gy.ravel())
        whole = sh.shape(c, profs, la, lo, np.zeros(la.size), grade, self.elev, cache={})
        dc, jc, ja = sh.shape(c, profs, la, lo, np.zeros(la.size), grade, self.elev, cache={}, parts=True)
        self.assertTrue(np.any(dc))
        self.assertTrue(np.array_equal(whole, np.minimum(dc, jc) + ja))


if __name__ == "__main__":
    unittest.main()
