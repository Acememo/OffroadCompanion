"""The track round the trees (courseroads.weave_shifts, terrain version 4): where the course line runs into trees, the
track moves to the nearest free strip at about the line's height, eased in and out; with no room it stays (the trees on
it are taken off: earthpatch's vegetation hook, test_paint)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(HERE))

from gpsd import courseroads as cr  # noqa: E402


def flat(n):
    kk = len(cr.side_offsets())
    return ([0.0] * n, [[0.0] * kk for _ in range(n)], [[0.0] * kk for _ in range(n)],
            [0.0] * n, [[0.0] * kk for _ in range(n)], [[0.0] * kk for _ in range(n)])


class TestWeave(unittest.TestCase):
    def test_round_a_tree(self):
        n = 21
        zc, zl, zr, cc, cl, crr = flat(n)
        cc[10], cl[10][0] = 9.0, 9.0                   # a tree on the line, its crown 2 m to the left
        got = cr.weave_shifts([True] * n, [0.0] * n, zc, zl, zr, cc, cl, crr)
        self.assertLess(got[10], 0, "round it on the right, the free side")
        self.assertLessEqual(abs(got[10]), cr.WEAVE_MAX_M)
        self.assertEqual(got[:6], [0.0] * 6, "straight on away from it")
        self.assertEqual(got[15:], [0.0] * 6)
        self.assertTrue(abs(got[7]) < abs(got[9]), "eased in")

    def test_no_room_stays(self):
        n = 21
        zc, zl, zr, cc, cl, crr = flat(n)
        cc[10] = 9.0
        cl[10] = [9.0] * len(cl[10])
        crr[10] = [9.0] * len(crr[10])
        self.assertEqual(cr.weave_shifts([True] * n, [0.0] * n, zc, zl, zr, cc, cl, crr), [0.0] * n)

    def test_not_up_a_bank(self):
        n = 21
        zc, zl, zr, cc, cl, crr = flat(n)
        cc[10] = 9.0
        zl[10] = [5.0] * len(zl[10])                  # the left side a bank, the right side trees
        crr[10] = [9.0] * len(crr[10])
        self.assertEqual(cr.weave_shifts([True] * n, [0.0] * n, zc, zl, zr, cc, cl, crr)[10], 0.0)

    def test_older_versions_never_weave(self):
        self.assertEqual(cr.WEAVE_FROM_TV, 4)


if __name__ == "__main__":
    unittest.main()
