"""The cut banks beside the course's dirt track (gpsd/banks.py): a sloping bank where BeamNG.Earth's grading stood a
bare step of ground, and nothing else touched.

Pure: numpy only, with a stand-in for BeamNG.Earth's grading (its wall rule: grading.WALL_CUT_M; test_paint.py checks
the banks inside BeamNG.Earth's own grading).
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
    from gpsd import banks as bk
    from gpsd import courseroads as cr
    from gpsd import relief as rf

LAT0, LON0 = 31.02, -115.43
CORE = rf.DEFAULT_HALF_M + 1.0      # the track's core: its half width and the shoulder


def frame():
    kx = math.radians(1) * cr.R_EARTH * math.cos(math.radians(LAT0))
    ky = math.radians(1) * cr.R_EARTH

    def ll(x, y):
        return LAT0 + np.asarray(y, np.float64) / ky, LON0 + np.asarray(x, np.float64) / kx

    def xy(lat, lon):
        return (np.asarray(lon) - LON0) * kx, (np.asarray(lat) - LAT0) * ky
    return ll, xy


def world(tv=None):
    """3 km due east (left: north, +y): flat to 1 km; 1-2 km a steep hillside rising to the north (0.9 m per m: a 3 m
    cut at the core's edge); 2-3 km a gentle one (0.3 m per m: 1 m, under the wall rule). A stand-in for BeamNG.Earth's
    grading of the track along y = 0: flat over the core at the line's height, then a wall's step where the cut at the
    core's edge is deeper than 2 m (a 2 m strip at the road's level, the ground up over 0.8 m), a 1:2 slope back to the
    ground otherwise (5 .. 12 m)."""
    ll, xy = frame()
    course = cr.Course([tuple(map(float, ll(x, 0.0))) for x in range(0, 3001, 50)], tv=tv)

    def slope(x):
        return np.where((x > 1000) & (x < 2000), 0.9, np.where(x >= 2000, 0.3, 0.0))

    def ground(lat, lon):
        x, y = xy(np.asarray(lat, np.float64), np.asarray(lon, np.float64))
        return 0.01 * x + slope(x) * np.maximum(y, 0.0)

    def grade(lat, lon, nat):
        x, y = xy(np.asarray(lat, np.float64), np.asarray(lon, np.float64))
        nat = np.asarray(nat, np.float64)
        zr = 0.01 * x
        cut = slope(x) * CORE
        u = np.abs(y) - CORE
        T = np.clip(2.0 * np.abs(nat - zr), 5.0, 12.0)
        gentle = zr + (nat - zr) * np.clip(u / T, 0, 1)
        wall = np.where(u < 2.0, zr, zr + (nat - zr) * np.clip(u / 12.0, 0, 1))
        out = np.where((cut > 2.0) & (y > 0), wall, gentle)
        return np.where(u <= 0, zr, out)

    profs = {k: rf.window_profile(course, k, [], lambda *a: [], lambda la, lo: ground(la, lo).tolist())
             for k in range(course.nwin)}
    return ll, xy, course, profs, ground, grade


@unittest.skipUnless(HAVE_NP, "numpy")
class TestBanks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        w = world()
        cls.course, cls.profs = w[2], w[3]
        cls.ll, cls.xy, cls.ground, cls.grade = (staticmethod(f) for f in (w[0], w[1], w[4], w[5]))

    def run_at(self, xs, ys, course=None):
        la, lo = self.ll(np.asarray(xs, np.float64), np.asarray(ys, np.float64))
        nat = self.ground(la, lo)
        g = self.grade(la, lo, nat)
        return g, bk.banks(course or self.course, self.profs, la, lo, nat, g, self.grade, self.ground), nat

    def test_the_step_becomes_a_bank(self):
        ys = np.arange(0.0, 26.0, 0.25)
        g, out, nat = self.run_at(np.full(len(ys), 1500.3), ys)
        # BeamNG.Earth's: a 2 m strip, then a jump
        face = np.diff(g) / 0.25
        self.assertGreater(face.max(), 3.0, "the step (the stand-in)")
        rise = np.diff(out) / 0.25
        self.assertLess(rise.max(), 1.5, "a bank, no face")
        self.assertGreater(rise[(ys[1:] > CORE + 2.5) & (ys[1:] < CORE + 8)].min(), bk.BANK_GRADE - 0.05,
                           "rising from the strip")
        self.assertTrue(np.all(out <= nat + 1e-9), "never over the natural ground: a cut")
        far = ys >= CORE + 2.0 + bk.REACH_M
        self.assertTrue(np.allclose(out[far], g[far]), "the hillside as it was past the bank")
        core = ys <= CORE + 2.0 - bk.PROBE_STEP_M      # (where the grading leaves the road's level: to a probe)
        self.assertTrue(np.allclose(out[core], g[core], atol=1e-6), "the track and its strip untouched")
        self.assertLess(np.abs(np.diff(out)).max(), 0.4, "no seam")

    def test_nothing_else_touched(self):
        xs = np.arange(0.0, 3000.0, 7.0)
        for y in (-12.0, -5.0, 0.0, 2.0):            # the other side, the track
            g, out, _ = self.run_at(xs, np.full(len(xs), y))
            self.assertTrue(np.array_equal(g, out), f"y {y}")
        for x0 in (500.0, 2500.0):                     # flat ground, the gentle hillside's 1:2 slope
            ys = np.arange(0.0, 20.0, 0.5)
            g, out, _ = self.run_at(np.full(len(ys), x0), ys)
            self.assertTrue(np.array_equal(g, out), f"x {x0}")

    def test_another_roads_ground_stays(self):
        ys = np.arange(CORE + 4.0, CORE + 11.0, 0.5)
        la, lo = self.ll(np.full(len(ys), 1500.0), ys)
        nat = self.ground(la, lo)
        g = nat + 1.0                                   # (another road's fill on the hillside)
        out = bk.banks(self.course, self.profs, la, lo, nat, g, self.grade, self.ground)
        self.assertTrue(np.array_equal(g, out))

    def test_the_same_change_on_another_ground(self):
        """A caller whose ground is metres off the probes' (a far ground tile's coarser elevation) gets the same bank
        change, never a spike (the user, 2026-11-12)."""
        ys = np.arange(0.0, 26.0, 0.25)
        la, lo = self.ll(np.full(len(ys), 1500.3), ys)
        nat = self.ground(la, lo)
        g = self.grade(la, lo, nat)
        mine = bk.banks(self.course, self.profs, la, lo, nat, g, self.grade, self.ground) - g
        off = 2.5 * np.sin(ys / 3.0)
        theirs = bk.banks(self.course, self.profs, la, lo, nat + off, g + off, self.grade, self.ground) - (g + off)
        self.assertGreater(np.abs(mine).max(), 0.5)
        self.assertTrue(np.allclose(mine, theirs, atol=1e-9))

    def test_the_same_whoever_asks(self):
        ys = np.arange(0.0, 20.0, 0.3)
        xs = np.full(len(ys), 1234.5)
        _, one, _ = self.run_at(xs, ys)
        both = np.concatenate([xs, np.arange(1000.0, 2000.0, 3.1)])
        ally = np.concatenate([ys, np.full(len(both) - len(ys), 9.0)])
        _, many, _ = self.run_at(both, ally)
        self.assertTrue(np.array_equal(one, many[:len(ys)]), "a point's bank depends only on the course")

    def test_version_1_keeps_the_step(self):
        old = cr.Course([tuple(map(float, self.ll(x, 0.0))) for x in range(0, 3001, 50)], tv=1)
        ys = np.arange(0.0, 20.0, 0.25)
        g, out, _ = self.run_at(np.full(len(ys), 1500.3), ys, course=old)
        self.assertTrue(np.array_equal(g, out))


if __name__ == "__main__":
    unittest.main()
