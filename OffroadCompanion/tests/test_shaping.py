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

if __name__ == "__main__":
    unittest.main()
