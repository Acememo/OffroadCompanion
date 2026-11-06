"""Offroad Companion as one program (app_launcher.py, the .exe's start): its arguments, and that the course painter gets
into BeamNG.Earth's server and the worker processes it starts (from source, with a BeamNG.Earth checkout: EARTH_ROOT,
default ../../../ref; tools/build_exe.py runs the same check on the built .exe)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
COMPANION = os.path.dirname(HERE)
sys.path.insert(0, COMPANION)
EARTH_ROOT = os.environ.get("EARTH_ROOT") or os.path.abspath(os.path.join(COMPANION, "..", "..", "ref"))

import app_launcher as al  # noqa: E402


class TestArgs(unittest.TestCase):
    def test_own_options_taken_out(self):
        mine, rest = al.split_args(["--pick-user-dir", "--no-game", "--", "--pick-user-dir"])
        self.assertEqual(mine, ["--pick-user-dir"])
        self.assertEqual(rest, ["--no-game", "--", "--pick-user-dir"], "after -- they are the server's")

    def test_server_options(self):
        self.assertEqual(al.with_server_options(["--no-game"]), ["--no-game", "--"] + al.SERVER_OPTIONS)
        self.assertEqual(al.with_server_options(["--", "--verbose"]), ["--"] + al.SERVER_OPTIONS + ["--verbose"])
        self.assertIn("--update-check", al.SERVER_OPTIONS, "BeamNG.Earth's update notice: it comes with Offroad "
                                                           "Companion")


class TestDataFolder(unittest.TestCase):
    def test_chosen_folder_for_everything_it_starts(self):
        from unittest import mock
        got = {}

        def setup(apppaths, pick_again=False, **kw):
            got["pick_again"] = pick_again
            return "/E/OffroadCompanion"

        class L:
            @staticmethod
            def server_port_busy():
                return False
        fake = type("M", (), {"setup": staticmethod(setup)})
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EARTHGPS_DIR", None)
            with mock.patch.object(al, "ours", lambda n: fake), mock.patch.object(al, "helper_running", lambda: False):
                self.assertEqual(al.data_folder(L, pick_again=True), "/E/OffroadCompanion")
                self.assertEqual(os.environ["EARTHGPS_DIR"], "/E/OffroadCompanion", "the server and helper follow it")
        self.assertTrue(got["pick_again"])
        self.assertEqual(al.split_args(["--pick-data-dir", "--no-game"])[0], ["--pick-data-dir"])


class TestClosingNeatly(unittest.TestCase):
    """The user, 2026-10-28: BeamMP's launcher kept running after the game and the window were closed."""

    def test_leftover_beammp_found_by_its_command_line(self):
        class R:
            stdout = ("1204\t\"C:\\BeamMP\\BeamMP-Launcher.exe\" --no-launch\r\n"
                      "2210\t\"C:\\BeamMP\\BeamMP-Launcher.exe\"\r\n"          # (the player's own: it starts the game)
                      "garbage\r\n").encode()
        calls = []

        def run(cmd, **kw):
            calls.append(cmd)
            return R()
        got = al.beammp_leftovers("BeamMP-Launcher.exe", run=run)
        self.assertEqual([p for p, _ in got], [1204], "only one started for a game (--no-launch)")
        self.assertIn("BeamMP-Launcher.exe", calls[0][-1])

    def test_server_and_beammp_kept_together(self):
        import types
        started = []

        class P:
            def __init__(self, pid):
                self.pid = pid
        launcher = types.SimpleNamespace(start_server=lambda *a, **k: P(11), GAME_GONE_S=30)
        bmp = types.ModuleType("bmplaunch")
        bmp.start = lambda *a, **k: P(22)
        sys.modules["bmplaunch"] = bmp
        try:
            al.keep_together(launcher)
            al.GROUP.add = lambda pid: started.append(pid) or True
            launcher.start_server("u", [], "log")
            bmp.start("exe", "u", "log")
        finally:
            del sys.modules["bmplaunch"]
        self.assertEqual(started, [11, 22], "both put in the group that ends with this program")
        self.assertEqual(launcher.GAME_GONE_S, al.GAME_GONE_S_WIN if os.name == "nt" else 30)


@unittest.skipUnless(os.path.isfile(os.path.join(EARTH_ROOT, "launcher.py")), "a BeamNG.Earth checkout")
class TestPainterInTheServer(unittest.TestCase):
    def test_no_earth_update_offered(self):
        """BeamNG.Earth 1.8.2's launcher asks at every start whether to install a newer BeamNG.Earth (its own .exe,
        downloaded beside ours): never in Offroad Companion."""
        launcher = type("L", (), {})()
        launcher.hand_over = lambda: True
        launcher.update_at_start = lambda args: True
        al.no_earth_updates(launcher)
        self.assertFalse(launcher.hand_over())
        self.assertFalse(launcher.update_at_start(object()))
        if os.path.isfile(os.path.join(EARTH_ROOT, "launcher.py")):
            sys.path.insert(0, EARTH_ROOT)
            try:
                import launcher as real
            finally:
                sys.path.remove(EARTH_ROOT)
            for name in ("hand_over", "main") + (("update_at_start",) if hasattr(real, "update_popup") else ()):
                self.assertTrue(callable(getattr(real, name, None)), f"BeamNG.Earth's launcher.{name} (what we replace)")

    def test_selftest(self):
        env = dict(os.environ, EARTHGPS_DIR=tempfile.mkdtemp(prefix="oc-app-"))
        env.pop("OFFROAD_COMPANION_PAINTER", None)
        r = subprocess.run([sys.executable, os.path.join(COMPANION, "app_launcher.py"), "--earth", EARTH_ROOT,
                            "--selftest"], capture_output=True, text=True, timeout=300, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        got = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertTrue(got["main"]["painter"] and got["worker"]["painter"], "in the server and its workers")
        from gpsd import earthpatch
        self.assertEqual(got["main"]["code"], earthpatch.gps_code_id(), "the same ground code as a source install")


if __name__ == "__main__":
    unittest.main()
