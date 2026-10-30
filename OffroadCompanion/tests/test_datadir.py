"""Where the data goes (gpsd/datadir.py): asked once, kept on the system drive or moved to a folder chosen elsewhere
(Offroad Companion's data and BeamNG.Earth's map downloads), followed by paintfile.base_dir() from then on."""
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(HERE))

from gpsd import datadir, paintfile  # noqa: E402


class FakeAppPaths:
    """BeamNG.Earth's apppaths: its remembered cache folder, its folder window."""

    def __init__(self, default, picked=None):
        self.default, self.saved, self.picked = default, None, picked

    def default_cache_dir(self):
        return self.default

    def saved_cache_dir(self):
        return self.saved

    def set_cache_dir(self, path):
        self.saved = path
        return path, None

    def ask_path(self, question, want, accept, ask=None, say=print, **kw):
        return accept(self.picked) if self.picked else None


def answers(*seq):
    it = iter(seq)
    return lambda prompt="": next(it)


class TestDataDir(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="egps-dd-")
        self.home = os.path.join(self.root, "C", "OffroadCompanion")
        self.earth = os.path.join(self.root, "C", ".cache", "beamng-earth")
        os.makedirs(os.path.join(self.home, "windows", "abc"))
        with open(os.path.join(self.home, "windows", "abc", "w0.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(self.home, "launcher.json"), "w") as f:
            f.write('{"user_dir": "X"}')
        os.makedirs(os.path.join(self.earth, "dem"))
        with open(os.path.join(self.earth, "dem", "t.png"), "wb") as f:
            f.write(b"x" * 1000)
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop("EARTHGPS_DIR", None)
        self.dflt = mock.patch.object(paintfile, "default_dir", lambda: self.home)
        self.dflt.start()
        paintfile._WHERE.clear()
        self.said = []

    def tearDown(self):
        self.dflt.stop()
        self.env.stop()
        paintfile._WHERE.clear()

    def say(self, m):
        self.said.append(m)

    def test_kept_on_the_system_drive_and_not_asked_again(self):
        ap = FakeAppPaths(self.earth)
        got = datadir.setup(ap, ask=answers(""), say=self.say, home=self.home)
        self.assertEqual(got, self.home)
        self.assertEqual(paintfile.base_dir(), self.home)
        got = datadir.setup(ap, ask=answers(), say=self.say, home=self.home)      # (asking now would raise)
        self.assertEqual(got, self.home, "remembered: not asked again")

    def test_moved_to_another_drive(self):
        other = os.path.join(self.root, "E", "Games")
        ap = FakeAppPaths(self.earth, picked=other)
        got = datadir.setup(ap, ask=answers("f", ""), say=self.say, home=self.home)
        ours = os.path.join(other, datadir.OURS)
        cache = os.path.join(other, datadir.EARTH_CACHE)
        self.assertEqual(got, ours)
        self.assertTrue(os.path.isfile(os.path.join(ours, "windows", "abc", "w0.json")), "the planned ground moved")
        self.assertTrue(os.path.isfile(os.path.join(ours, "launcher.json")), "the remembered folders too")
        self.assertTrue(os.path.isfile(os.path.join(cache, "dem", "t.png")), "BeamNG.Earth's downloads moved")
        self.assertFalse(os.path.exists(os.path.join(self.home, "windows")), "nothing left behind")
        self.assertTrue(os.path.isfile(os.path.join(self.home, paintfile.LOCATION_FILE)), "the pointer stays home")
        self.assertEqual(ap.saved, cache, "BeamNG.Earth told where its cache is now")
        paintfile._WHERE.clear()
        self.assertEqual(paintfile.base_dir(), ours, "everything follows it")
        self.assertEqual(datadir.setup(ap, ask=answers(), say=self.say, home=self.home), ours)

    def test_start_empty_there(self):
        other = os.path.join(self.root, "E")
        ap = FakeAppPaths(self.earth, picked=other)
        got = datadir.setup(ap, ask=answers("f", "n"), say=self.say, home=self.home)
        self.assertEqual(got, os.path.join(other, datadir.OURS))
        self.assertTrue(os.path.isfile(os.path.join(self.home, "windows", "abc", "w0.json")), "left where it was")
        self.assertEqual(ap.saved, os.path.join(other, datadir.EARTH_CACHE))

    def test_a_path_typed_at_the_question(self):
        other = os.path.join(self.root, "F", "data")
        got = datadir.setup(FakeAppPaths(self.earth), ask=answers(other, ""), say=self.say, home=self.home)
        self.assertEqual(got, os.path.join(other, datadir.OURS))

    def test_unreachable_drive_asks_again(self):
        gone = os.path.join(self.root, "nothing-here", "OffroadCompanion")
        datadir.remember(self.home, gone)
        with mock.patch.object(datadir, "writable", lambda p: None):
            got = datadir.setup(FakeAppPaths(self.earth), ask=answers(""), say=self.say, home=self.home)
        self.assertTrue(any("can't be reached" in m for m in self.said))
        self.assertEqual(got, gone, "kept (plug it in) unless another is chosen")

    def test_nothing_moved_while_running_elsewhere(self):
        other = os.path.join(self.root, "E")
        ap = FakeAppPaths(self.earth, picked=other)
        datadir.setup(ap, ask=answers("f"), say=self.say, home=self.home, busy=True)
        self.assertTrue(os.path.isfile(os.path.join(self.home, "windows", "abc", "w0.json")))
        self.assertTrue(any("nothing is moved" in m for m in self.said))

    def test_no_one_to_answer(self):
        got = datadir.setup(FakeAppPaths(self.earth), ask=answers(), say=self.say, home=self.home, interactive=False)
        self.assertEqual(got, self.home)
        self.assertIsNone(datadir.location(self.home), "nothing remembered: asked at a start with a window")

    def test_pick_again_moves_from_the_chosen_folder(self):
        e = os.path.join(self.root, "E")
        ap = FakeAppPaths(self.earth, picked=e)
        datadir.setup(ap, ask=answers("f", ""), say=self.say, home=self.home)
        g = os.path.join(self.root, "G")
        ap.picked = g
        got = datadir.setup(ap, pick_again=True, ask=answers("f", ""), say=self.say, home=self.home)
        self.assertEqual(got, os.path.join(g, datadir.OURS))
        self.assertTrue(os.path.isfile(os.path.join(got, "windows", "abc", "w0.json")))
        self.assertTrue(os.path.isfile(os.path.join(g, datadir.EARTH_CACHE, "dem", "t.png")))


if __name__ == "__main__":
    unittest.main()
