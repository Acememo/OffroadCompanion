"""The release zips (tools/package.py): the game mod's entries dated in the past in every time zone (past_stamp)."""
import importlib.util
import os
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "tools", "package.py")


@unittest.skipUnless(os.path.isfile(TOOL), "the source tree's tools")
class TestStamps(unittest.TestCase):
    def test_in_the_past_everywhere(self):
        spec = importlib.util.spec_from_file_location("egps_package", TOOL)
        pkg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pkg)
        now = time.time()
        stamp = pkg.past_stamp(now)
        self.assertLess(stamp, time.gmtime(now - 12 * 3600)[:6], "before now at UTC-12, the most western time")
        self.assertGreater(stamp, time.gmtime(now - 24 * 3600)[:6], "and not much older than the file")


if __name__ == "__main__":
    unittest.main()
