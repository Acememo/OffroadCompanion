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


BUILD = os.path.join(os.path.dirname(os.path.dirname(HERE)), "tools", "build_exe.py")
EARTH_ROOT = os.environ.get("EARTH_ROOT") or os.path.abspath(os.path.join(HERE, "..", "..", "..", "ref"))


@unittest.skipUnless(os.path.isfile(BUILD) and os.path.isdir(os.path.join(EARTH_ROOT, "server")),
                     "the source tree's tools and a BeamNG.Earth checkout")
class TestExeData(unittest.TestCase):
    def test_earths_data_in_the_exe(self):
        """Every data file and folder BeamNG.Earth's own .exe build adds goes into ours (1.8.2: the server's data
        folder, its billboards, direction signs' styles and places, read from <modules>/data)."""
        import re
        spec = importlib.util.spec_from_file_location("egps_build_exe", BUILD)
        bx = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bx)
        server = os.path.join(EARTH_ROOT, "server")
        files = set(bx.earth_data_files(EARTH_ROOT))
        dirs = dict(bx.earth_data_dirs(EARTH_ROOT))
        with open(os.path.join(EARTH_ROOT, "tools", "build_app.py"), encoding="utf-8") as f:
            named = re.findall(r"os\.path\.join\(server, '([^']+)'\)", f.read())
        for n in named:
            p = os.path.join(server, n)
            if os.path.isfile(p):
                self.assertIn(p, files, n)
            elif os.path.isdir(p):
                self.assertIn(p, dirs, n)
        if os.path.isdir(os.path.join(server, "data")):
            self.assertEqual(dirs.get(os.path.join(server, "data")), "data")
