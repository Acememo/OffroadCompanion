"""Setup and start with a BeamNG.drive user folder moved out of AppData (the user's D:\\BeamNGUser\\current) and the
companion unzipped inside a BeamNG.Earth source folder (D:\\BeamngEarth\\companion)."""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
COMPANION = os.path.dirname(HERE)
sys.path.insert(0, COMPANION)

from gpsd import beamngdirs  # noqa: E402

FAKE_START = '''
import json, os, sys
EARTHD = "earthd"
def main():
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "started.json"), "w") as f:
        json.dump({"argv": sys.argv[1:], "earthd": EARTHD, "cwd": os.getcwd(),
                   "root": os.environ.get("EARTHGPS_EARTH_ROOT")}, f)
'''


class Layout:
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="egps-layout-")
        self.earth = os.path.join(self.tmp, "D", "BeamngEarth")
        os.makedirs(os.path.join(self.earth, "server"))
        for f in ("install.py", "server/earthd.py", "BeamNG.Earth-1.5.4-beta.exe"):
            open(os.path.join(self.earth, f), "w").close()
        with open(os.path.join(self.earth, "VERSION"), "w") as f:
            f.write("1.5.4-beta\n")
        with open(os.path.join(self.earth, "start.py"), "w") as f:
            f.write(FAKE_START)
        self.companion = os.path.join(self.earth, "companion")
        shutil.copytree(COMPANION, self.companion, ignore=shutil.ignore_patterns("__pycache__", "cache"))
        os.makedirs(os.path.join(self.companion, "mod"), exist_ok=True)
        with open(os.path.join(self.companion, "mod", "offroad_companion.zip"), "wb") as f:
            f.write(b"PK-gps-mod-v2")
        self.user = os.path.join(self.tmp, "D", "BeamNGUser")
        os.makedirs(os.path.join(self.user, "current", "mods"))
        self.local = os.path.join(self.tmp, "AppData", "Local")
        default = os.path.join(self.local, "BeamNG", "BeamNG.drive", "current")
        os.makedirs(default)                                  # the empty default folder (no mods / settings)
        with open(os.path.join(self.local, "BeamNG", "BeamNG.drive.ini"), "w", encoding="utf-8-sig") as f:
            f.write("installPath = C:\\Steam\\BeamNG.drive\n" + f"userFolder = {self.user}\n")
        with open(os.path.join(self.earth, ".beamng_earth.json"), "w") as f:
            json.dump({"user_dir": default, "version": "1.5.4-beta"}, f)       # Earth's installer's default
        self.cfgdir = os.path.join(self.tmp, "egps")
        self.env = {"LOCALAPPDATA": self.local, "EARTHGPS_DIR": self.cfgdir}


class TestUserDir(unittest.TestCase):
    def test_moved_user_folder_wins(self):
        L = Layout()
        with mock.patch.dict(os.environ, L.env), mock.patch.object(beamngdirs, "IS_WIN", True):
            self.assertEqual(beamngdirs.game_setting(), os.path.join(L.user, "current"))
            c = beamngdirs.candidates(None, L.earth)
            self.assertEqual(c[0][0], os.path.join(L.user, "current"))
            out = io.StringIO()
            with redirect_stdout(out):
                got = beamngdirs.find(None, L.earth, ask=False)
            self.assertEqual(got, os.path.join(L.user, "current"))
        self.assertEqual(beamngdirs.as_current(L.user), os.path.join(L.user, "current"))
        self.assertEqual(beamngdirs.as_current(os.path.join(L.user, "current")), os.path.join(L.user, "current"))

    def test_the_folder_chosen_before_is_not_asked_again(self):
        """Several real user folders (old game versions' too): the one chosen before is used at once, no question;
        --pick-user-dir (pick_again) asks again."""
        L = Layout()
        for v in ("0.35", "0.36"):                                   # (real old folders: they have mods)
            os.makedirs(os.path.join(L.local, "BeamNG.drive", v, "mods"))
        chosen = os.path.join(L.user, "current")
        asked = []

        def ask(prompt=""):
            asked.append(prompt)
            return "2"
        with mock.patch.dict(os.environ, L.env), mock.patch.object(beamngdirs, "IS_WIN", True), \
                mock.patch("builtins.input", ask), mock.patch.object(sys.stdin, "isatty", lambda: True):
            out = io.StringIO()
            with redirect_stdout(out):
                got = beamngdirs.find(chosen, L.earth)
            self.assertEqual(got, chosen)
            self.assertEqual(asked, [], "not asked")
            self.assertIn("chosen before", out.getvalue())
            real = [c for c in beamngdirs.candidates(chosen, L.earth) if beamngdirs.looks_like_user_dir(c[0])]
            if len(real) > 1:
                with redirect_stdout(io.StringIO()):
                    again = beamngdirs.find(chosen, L.earth, pick_again=True)
                self.assertEqual(len(asked), 1, "asked when picking again")
                self.assertEqual(again, real[1][0])
            # a folder chosen before that is gone: asked as before (or the best one found)
            with redirect_stdout(io.StringIO()):
                beamngdirs.find(os.path.join(L.tmp, "gone"), L.earth)

    def test_setup_uses_the_existing_earth_and_the_moved_folder(self):
        L = Layout()
        calls = []
        with mock.patch.dict(os.environ, L.env), mock.patch.object(beamngdirs, "IS_WIN", True):
            sys.path.insert(0, L.companion)
            for m in [k for k in sys.modules if k == "setup_earth_source" or k.startswith("gpsd")]:
                del sys.modules[m]
            import setup_earth_source as S
            S.beamngdirs.IS_WIN = True
            with mock.patch.object(S.subprocess, "call", lambda cmd, cwd=None: calls.append((cmd, cwd)) or 0), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(S.main([]), 0)
            sys.path.remove(L.companion)
        cmd, cwd = calls[0]
        self.assertEqual(cwd, L.earth, "BeamNG.Earth's own folder: nothing downloaded")
        self.assertEqual(cmd[1], os.path.join(L.earth, "install.py"))
        self.assertEqual(cmd[cmd.index("--user-dir") + 1], os.path.join(L.user, "current"))
        with open(os.path.join(L.user, "current", "mods", "offroad_companion.zip"), "rb") as f:
            self.assertEqual(f.read(), b"PK-gps-mod-v2", "the GPS mod copied into the moved folder's mods")
        with open(os.path.join(L.cfgdir, "launcher.json")) as f:
            cfg = json.load(f)
        self.assertEqual((cfg["earth"], cfg["user_dir"]), (L.earth, os.path.join(L.user, "current")))

    def test_start_passes_the_user_folder(self):
        L = Layout()
        with mock.patch.dict(os.environ, L.env), mock.patch.object(beamngdirs, "IS_WIN", True):
            sys.path.insert(0, L.companion)
            for m in [k for k in sys.modules if k in ("start_earth_with_tracks", "setup_earth_source", "start")
                      or k.startswith("gpsd")]:
                del sys.modules[m]
            import start_earth_with_tracks as T
            T.beamngdirs.IS_WIN = True
            cwd = os.getcwd()
            old_path = list(sys.path)
            try:
                started = []
                with mock.patch.object(sys, "argv", ["x", "--", "--verbose"]), redirect_stdout(io.StringIO()), \
                        mock.patch.object(T, "start_companion", lambda: started.append(1)):
                    T.main()
                self.assertEqual(started, [1], "the Offroad Companion started in the same window")
            finally:
                os.chdir(cwd)
                sys.path[:] = old_path
                sys.modules.pop("start", None)
        with open(os.path.join(L.earth, "started.json")) as f:
            got = json.load(f)
        self.assertEqual(got["argv"][:2], ["--user-dir", os.path.join(L.user, "current")])
        self.assertEqual(got["argv"][2:], ["--", "--verbose"])
        self.assertTrue(got["earthd"].endswith("earth_tracks_server.py"))
        self.assertEqual(got["root"], L.earth)
        self.assertTrue(os.path.isfile(os.path.join(L.user, "current", "mods", "offroad_companion.zip")))


class TestEarthVersion(unittest.TestCase):
    """setup downloads only the BeamNG.Earth this companion was made for (the user, 2026-10-25: "should only download
    the source of the BeamNG.Earth version it's compatible with")."""

    def _ses(self):
        import setup_earth_source as ses
        return ses

    def test_which_versions(self):
        ses = self._ses()
        self.assertTrue(ses.compatible(ses.EARTH_VERSION))
        for v in ("1.8.2-beta", "1.8.1-beta", "1.8.0-beta", "1.7.3-beta", "1.7.2-beta", "1.7.2-beta.dev.37", "1.7.1-beta", "1.7.0-beta", "1.6.3-beta", "1.6.2-beta", "v1.6.1-beta", "1.6.0-beta", "1.5.4-beta", "v1.5.5-beta", "1.6.2"):
            self.assertTrue(ses.compatible(v), v)
        for v in ("1.8.3-beta", "1.9.0-beta", "1.7.4-beta", "1.6.4-beta", "1.6.20", "2.0.0", "1.4.35-beta", "", None, "local"):
            self.assertFalse(ses.compatible(v), v)

    def test_downloads_the_one_it_was_made_for(self):
        ses = self._ses()
        got = []

        def fake_get(url, accept=None):
            got.append(url)
            raise OSError("offline")
        tmp = tempfile.mkdtemp(prefix="egps-dl-")
        args = ses.argparse.Namespace(version=None, zip=None, dir=tmp, any_version=False)
        with mock.patch.object(ses, "get", fake_get), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                ses.fetch(args)
        self.assertEqual(got, [ses.ZIP.format(tag="v" + ses.EARTH_VERSION)], "that release's source, not the newest")
        self.assertIn(ses.release_zip("v" + ses.EARTH_VERSION), str(cm.exception), "the address to get it by hand")
        args.version = "1.9.0-beta"
        got.clear()
        with mock.patch.object(ses, "get", fake_get), self.assertRaises(SystemExit) as cm:
            ses.fetch(args)
        self.assertEqual(got, [], "a version it was not made for: not downloaded")
        self.assertIn("--any-version", str(cm.exception))

    def test_a_copy_of_another_version_is_passed_over(self):
        ses = self._ses()
        L = Layout()
        with open(os.path.join(L.earth, "VERSION"), "w") as f:
            f.write("1.9.0-beta\n")
        said = []
        with mock.patch.object(ses, "HERE", L.companion):
            self.assertIsNone(ses.existing_earth({}, out=said.append))
            self.assertTrue(said and "1.9.0-beta" in said[0] and ses.EARTH_VERSION in said[0])
            with open(os.path.join(L.earth, "VERSION"), "w") as f:
                f.write("1.6.1-beta\n")
            self.assertEqual(ses.existing_earth({}), os.path.abspath(L.earth), "one it works with: used")


class TestVersion(unittest.TestCase):
    def test_one_version_everywhere(self):
        """OffroadCompanion/VERSION is the companion's (its requests, its hello) and the game app's (main.lua M.VERSION);
        the release zips are named after it (tools/package.py)."""
        import re
        from gpsd import fetch
        with open(os.path.join(COMPANION, "VERSION"), encoding="utf-8") as f:
            v = f.read().strip()
        self.assertRegex(v, r"^\d+\.\d+\.\d+$")
        self.assertEqual(fetch.VERSION, v)
        self.assertIn(f"/{v} ", fetch.USER_AGENT)
        main_lua = os.path.join(os.path.dirname(COMPANION), "mod", "offroad_companion", "lua", "ge", "extensions",
                                "offroadCompanion", "main.lua")
        if os.path.isfile(main_lua):
            with open(main_lua, encoding="utf-8") as f:
                m = re.search(r"M\.VERSION = '([^']+)'", f.read())
            self.assertEqual(m.group(1), v, "the game app's version")


class TestRename(unittest.TestCase):
    def test_layouts_keep_the_app_under_its_new_name(self):
        import json
        import tempfile
        import setup_earth_source as ses
        d = tempfile.mkdtemp(prefix="oc-lay-")
        lay_dir = os.path.join(d, "settings", "ui_apps", "layouts", "default")
        os.makedirs(lay_dir)
        lay = {"apps": [{"appName": "earthGps", "directive": "earthGps", "domElement": "<earth-gps></earth-gps>",
                         "name": "BeamNG.Earth: GPS", "placement": {"left": "5px"}},
                        {"appName": "tacho2", "directive": "tacho2"}], "type": "uilayout"}
        with open(os.path.join(lay_dir, "beamngEarth.uilayout.json"), "w") as f:
            json.dump(lay, f)
        with open(os.path.join(lay_dir, "other.uilayout.json"), "w") as f:
            json.dump({"apps": [{"appName": "tacho2"}]}, f)
        self.assertEqual(ses.migrate_layouts(d), 1)
        with open(os.path.join(lay_dir, "beamngEarth.uilayout.json")) as f:
            got = json.load(f)
        a = got["apps"][0]
        self.assertEqual((a["appName"], a["directive"], a["name"]), ("offroadCompanion", "offroadCompanion",
                                                                     "Offroad Companion"))
        self.assertEqual(a["placement"], {"left": "5px"}, "where the player put it")
        self.assertEqual(got["apps"][1]["appName"], "tacho2")
        self.assertEqual(ses.migrate_layouts(d), 0, "once")

    def test_the_old_folder_and_its_tracks(self):
        import tempfile
        import setup_earth_source as ses
        d = tempfile.mkdtemp(prefix="oc-old-")
        old, new = os.path.join(d, "companion"), os.path.join(d, "OffroadCompanion")
        os.makedirs(os.path.join(old, "tracks"))
        os.makedirs(os.path.join(new, "tracks"))
        open(os.path.join(old, "earth_gpsd.py"), "w").close()
        for fn in ("Mine.gpx", "README.txt", "Both.gpx"):
            with open(os.path.join(old, "tracks", fn), "w") as f:
                f.write("old " + fn)
        with open(os.path.join(new, "tracks", "Both.gpx"), "w") as f:
            f.write("new")
        n, aside = ses.migrate_old_folder(new)
        self.assertEqual(n, 1)
        with open(os.path.join(new, "tracks", "Mine.gpx")) as f:
            self.assertEqual(f.read(), "old Mine.gpx", "the player's track brought over")
        with open(os.path.join(new, "tracks", "Both.gpx")) as f:
            self.assertEqual(f.read(), "new", "never overwritten")
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.isfile(os.path.join(aside, "tracks", "Mine.gpx")), "the old folder renamed, kept")
        self.assertEqual(ses.migrate_old_folder(new), (0, None), "once")

    def test_the_data_folder_moves_to_the_new_name(self):
        import importlib
        import tempfile
        from gpsd import paintfile
        d = tempfile.mkdtemp(prefix="oc-data-")
        old = os.path.join(d, "beamng-earth-gps")
        os.makedirs(os.path.join(old, "windows"))
        open(os.path.join(old, "launcher.json"), "w").close()
        env = {"XDG_CACHE_HOME": d}
        with mock.patch.dict(os.environ, env), mock.patch.object(os, "name", "posix"):
            os.environ.pop("EARTHGPS_DIR", None)
            paintfile._MOVED.clear()
            got = paintfile.base_dir()
        paintfile._MOVED.clear()
        self.assertEqual(got, os.path.join(d, "offroad-companion"))
        self.assertTrue(os.path.isfile(os.path.join(got, "launcher.json")), "everything moved along")
        self.assertFalse(os.path.exists(old))


class TestModActive(unittest.TestCase):
    def test_turned_back_on_after_beammp(self):
        """Joining a BeamMP server turns off the mods it does not send and leaves them off: the GPS mod's entry in the
        game's mods/db.json is turned back on at start, nothing else changed."""
        import json
        import tempfile
        import setup_earth_source as ses
        d = tempfile.mkdtemp(prefix="egps-db-")
        os.makedirs(os.path.join(d, "mods"))
        db = {"header": {"version": 1.1}, "mods": {
            "offroad_companion": {"active": False, "fullpath": "/mods/offroad_companion.zip"},
            "othermod": {"active": False}}}
        with open(os.path.join(d, "mods", "db.json"), "w") as f:
            json.dump(db, f)
        self.assertTrue(ses.ensure_gps_mod_active(d))
        with open(os.path.join(d, "mods", "db.json")) as f:
            got = json.load(f)
        self.assertTrue(got["mods"]["offroad_companion"]["active"])
        self.assertFalse(got["mods"]["othermod"]["active"], "other mods left as they are")
        self.assertEqual(got["header"], db["header"])
        self.assertFalse(ses.ensure_gps_mod_active(d), "already on: nothing to do")
        self.assertFalse(ses.ensure_gps_mod_active(os.path.join(d, "nowhere")))


class TestModCopies(unittest.TestCase):
    def test_other_copies_moved_aside_and_build_read(self):
        import tempfile
        import zipfile
        import setup_earth_source as ses
        import earth_gpsd
        d = tempfile.mkdtemp(prefix="egps-mods-")
        mods = os.path.join(d, "mods")
        os.makedirs(os.path.join(mods, "repo"))

        def mk(path, build, ours=True):
            with zipfile.ZipFile(path, "w") as z:
                if ours:
                    z.writestr(ses.MOD_MARK, f"M.BUILD = '{build}'\n")
                else:
                    z.writestr("lua/ge/extensions/other/main.lua", "x")
        src_dir = os.path.join(d, "companion", "mod")
        os.makedirs(src_dir)
        mk(os.path.join(src_dir, "offroad_companion.zip"), "2026-10-22 06:25")
        mk(os.path.join(mods, "offroad_companion (1).zip"), "2026-10-22 04:50")
        mk(os.path.join(mods, "repo", "earthgps_old.zip"), "2026-10-21 10:00")
        mk(os.path.join(mods, "someone_elses.zip"), "", ours=False)
        with zipfile.ZipFile(os.path.join(mods, "beamng_earth_gps.zip"), "w") as z:     # (the mod's old name)
            z.writestr("lua/ge/extensions/earthGps/main.lua", "M.BUILD = '2026-10-23 19:40'\n")
        old_zip = ses.mod_zip
        ses.mod_zip = lambda: os.path.join(src_dir, "offroad_companion.zip")
        try:
            ses.install_gps_mod(d)
        finally:
            ses.mod_zip = old_zip
        left = sorted(os.listdir(mods))
        self.assertIn("offroad_companion.zip", left)
        self.assertNotIn("offroad_companion (1).zip", left, "the browser's copy moved aside")
        self.assertIn("someone_elses.zip", left, "other mods untouched")
        self.assertEqual(os.listdir(os.path.join(mods, "repo")), [])
        self.assertEqual(sorted(os.listdir(os.path.join(mods, ses.ASIDE))),
                         sorted(["offroad_companion (1).zip", "earthgps_old.zip", "beamng_earth_gps.zip"]),
                         "the mod under its old name too (the game would run both apps)")
        self.assertEqual(earth_gpsd.bundled_mod_build(os.path.join(mods, "offroad_companion.zip")), "2026-10-22 06:25")


class TestOneWindow(unittest.TestCase):
    """run_offroad_companion starts the Offroad Companion too (the user, 2026-10-22: one window instead of two)."""

    def test_companion_child_and_already_running(self):
        import start_earth_with_tracks as T
        calls = []

        class P:
            def __init__(self, cmd, cwd=None):
                calls.append(cmd)

            def poll(self):
                return None
        with mock.patch.object(T, "companion_running", lambda port=47614: False), \
                mock.patch("subprocess.Popen", P), mock.patch("atexit.register", lambda f: None), \
                redirect_stdout(io.StringIO()):
            self.assertIsNotNone(T.start_companion())
        self.assertTrue(calls[0][1].endswith("earth_gpsd.py") and calls[0][2:] == ["--log-prefix", "Offroad"])
        calls.clear()
        with mock.patch.object(T, "companion_running", lambda port=47614: True), mock.patch("subprocess.Popen", P), \
                redirect_stdout(io.StringIO()):
            self.assertIsNone(T.start_companion(), "one already running: that one")
        self.assertEqual(calls, [])



if __name__ == "__main__":
    unittest.main()
