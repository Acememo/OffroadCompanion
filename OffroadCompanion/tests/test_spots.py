"""Where spectators gather (gpsd/spots.py): the jumps exactly where the track terrain makes them (relief.py), paved
crossings from the relief profiles."""
import math
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(HERE))

from gpsd import courseroads as cr  # noqa: E402
from gpsd import spots  # noqa: E402

try:
    import numpy as np
    from gpsd import relief as rf
    HAVE_NP = True
except ImportError:
    HAVE_NP = False


@unittest.skipUnless(HAVE_NP, "numpy (to compare with relief.py)")
class TestSameAsRelief(unittest.TestCase):
    def test_constants(self):
        self.assertEqual((spots.BIN_M, spots.P_FEATURE, spots.P_KICKER), (rf.BIN_M, rf.P_FEATURE, rf.P_KICKER))
        self.assertEqual(spots.STEP, rf.STEP)

    def test_hash_bit_for_bit(self):
        rnd = random.Random(5)
        for _ in range(3000):
            a, b = rnd.randint(-2_000_000, 2_000_000), rnd.randint(-2_000_000, 2_000_000)
            salt = rnd.choice((21, 22, 23, 24, 7, 300))
            self.assertEqual(spots.hash01(a, b, salt), float(rf._hash(np.array([a]), np.array([b]), salt)[0]))

    def test_kicks_are_the_reliefs(self):
        # a 30 km course in Baja: every kicker of relief._bin_features (its bump's peak) is one of kicks()
        lat0, lon0 = 31.02, -115.43
        pts = [(lat0 + 0.002 * math.sin(i / 40.0), lon0 + i * 0.0001) for i in range(3000)]
        c = cr.Course(pts)
        s = np.arange(0.0, (c.n - 1) * cr.STEP_M, 0.5)
        h = rf._bin_features(c, s, np.zeros(len(s)))
        got = spots.kicks(c.lat, c.lon, 0.0, float(s[-1]))
        self.assertGreater(len(got), 5)
        for pos, size in got:
            i = int(round(pos / 0.5))
            self.assertGreater(h[i], 0.25, f"a kicker's ramp at {pos}")
            near = h[max(0, i - 60):i + 60]
            self.assertAlmostEqual(float(near.max()), float(h[i]), delta=0.05, msg=f"its top at {pos}")
        # and every positive feature of relief's is one of ours
        peaks = [float(s[i]) for i in range(1, len(s) - 1) if h[i] > 0.25 and h[i] >= h[i - 1] and h[i] >= h[i + 1]]
        for p in peaks:
            self.assertTrue(any(abs(p - q) < 3.0 for q, _ in got), f"relief's kicker at {p} found")
        self.assertEqual([], spots.kicks(c.lat, c.lon, 0.0, float(s[-1]), rock_at=lambda s_: 0.9), "none in rocks")


class TestCrossings(unittest.TestCase):
    def test_a_paved_road_across(self):
        rough = [1.0] * 30 + [0.6, 0.2, 0.0, 0.0, 0.0, 0.2, 0.6] + [1.0] * 30
        got = spots.crossings(rough, i0=100)
        self.assertEqual(len(got), 1)
        self.assertAlmostEqual(got[0], (100 + 33) * cr.STEP_M, delta=cr.STEP_M)
        along = [1.0] * 10 + [0.0] * 40 + [1.0] * 10
        self.assertEqual(spots.crossings(along), [], "along a paved road: not a crossing")
        self.assertEqual(spots.crossings([0.0] * 5 + [1.0] * 20), [], "dirt on one side only")


if __name__ == "__main__":
    unittest.main()
