"""appupdate.py: the .exe's own update from GitHub's releases (checked, downloaded beside it, handed over to)."""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import appupdate as up  # noqa: E402

NEW = b"MZ new offroad companion " * 1000


def release(version="1.8.0", body=NEW, name=None, digest=True, prerelease=False, url=None):
    name = name or f"OffroadCompanion-{version}.exe"
    a = {"name": name, "size": len(body),
         "browser_download_url": url or f"{up.ASSET_PREFIX}v{version}/{name}"}
    if digest:
        a["digest"] = "sha256:" + hashlib.sha256(body).hexdigest()
    return {"tag_name": "v" + version, "draft": False, "prerelease": prerelease,
            "assets": [{"name": "English-Guide.pdf", "size": 3, "digest": "sha256:" + "0" * 64,
                        "browser_download_url": up.ASSET_PREFIX + "v" + version + "/English-Guide.pdf"},
                       {"name": f"OffroadCompanion-BeamMP-Server-{version}.zip", "size": 3,
                        "digest": "sha256:" + "1" * 64,
                        "browser_download_url": up.ASSET_PREFIX + "v" + version + "/x.zip"}, a]}


class Resp(io.BytesIO):
    def __init__(self, body, url="https://objects.githubusercontent.com/x"):
        super().__init__(body)
        self.url = url

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class TestVersions(unittest.TestCase):
    def test_newer(self):
        self.assertTrue(up.newer("1.7.10", "1.7.9"))
        self.assertTrue(up.newer("v1.8.0", "1.7.9"))
        self.assertFalse(up.newer("1.7.9", "1.7.9"))
        self.assertFalse(up.newer("1.7.8", "1.7.9"))
        self.assertFalse(up.newer("1.8.0-beta", "1.7.9"), "not a plain version: never offered")
        self.assertFalse(up.newer("1.8.0", "?"))


class TestCheck(unittest.TestCase):
    def test_pick_only_a_checked_exe_of_this_project(self):
        self.assertEqual(up.pick(release())[:3], ("1.8.0", "OffroadCompanion-1.8.0.exe",
                                                  up.ASSET_PREFIX + "v1.8.0/OffroadCompanion-1.8.0.exe"))
        self.assertIsNone(up.pick(release(digest=False)), "no SHA-256 from GitHub: not offered")
        self.assertIsNone(up.pick(release(url="https://example.com/OffroadCompanion-1.8.0.exe")), "elsewhere: no")
        self.assertIsNone(up.pick(release(name="OffroadCompanion-1.7.0.exe")), "another version's file: no")
        self.assertIsNone(up.pick(release(prerelease=True)), "a pre-release: no")
        self.assertIsNone(up.pick(dict(release(), draft=True)), "a draft: no")
        self.assertIsNone(up.pick("x"))

    def test_check(self):
        got = up.check("1.7.9", get=lambda url, cur: release())
        self.assertEqual((got["current"], got["latest"]), ("1.7.9", "1.8.0"))
        self.assertTrue(got["url"].endswith("/releases/tag/v1.8.0"))
        self.assertIsNone(up.check("1.8.0", get=lambda url, cur: release()), "up to date")
        self.assertIsNone(up.check("1.8.1", get=lambda url, cur: release()), "newer than GitHub's (a dev copy)")

        def offline(url, cur):
            raise OSError("no network")
        self.assertIsNone(up.check("1.7.9", get=offline), "offline: nothing, no error")
        self.assertIsNone(up.check("1.7.9", get=lambda url, cur: {"message": "API rate limit exceeded"}))

    def test_disabled(self):
        self.assertTrue(up.disabled(["--no-update-check"], {}))
        self.assertTrue(up.disabled([], {up.NO_UPDATE_ENV: "1"}))
        self.assertFalse(up.disabled(["--", "--no-update-check"], {}), "a server option after --: not ours")
        self.assertFalse(up.disabled(["--no-game"], {}))


class TestFiles(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="oc-up-")
        self.exe = os.path.join(self.dir, "OffroadCompanion-1.7.9.exe")
        with open(self.exe, "wb") as f:
            f.write(b"MZ old")
        self.said = []

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_packaged_path(self):
        self.assertIsNone(up.packaged_path(frozen=False, executable=self.exe), "from source: nothing")
        self.assertEqual(up.packaged_path(frozen=True, executable=self.exe), self.exe)
        self.assertIsNone(up.packaged_path(frozen=True, executable="/usr/bin/python3"))

    def test_download_checked_and_staged(self):
        v, path = up.download("1.7.9", self.exe, release(), opener=lambda u: Resp(NEW))
        self.assertEqual(v, "1.8.0")
        self.assertEqual(os.path.basename(path), "OffroadCompanion-1.8.0.exe")
        with open(path, "rb") as f:
            self.assertEqual(f.read(), NEW)
        with open(self.exe, "rb") as f:
            self.assertEqual(f.read(), b"MZ old", "the running .exe is never touched")
        self.assertEqual(up.staged("1.7.9", self.exe), path, "the old copy hands over to it")
        self.assertIsNone(up.staged("1.8.0", path), "the new copy runs itself")
        self.assertIsNone(up.staged("1.8.0", self.exe))

    def test_bad_download_deleted(self):
        with self.assertRaises(up.UpdateError):
            up.download("1.7.9", self.exe, release(), opener=lambda u: Resp(NEW[:-1] + b"X"))
        self.assertEqual(sorted(os.listdir(self.dir)), ["OffroadCompanion-1.7.9.exe"], "nothing left, nothing staged")
        with self.assertRaises(up.UpdateError):
            up.download("1.7.9", self.exe, release(), opener=lambda u: Resp(NEW, url="http://x/y"))
        self.assertEqual(sorted(os.listdir(self.dir)), ["OffroadCompanion-1.7.9.exe"], "off https: refused")

        def broken(u):
            raise OSError("connection reset")
        with self.assertRaises(up.UpdateError):
            up.download("1.7.9", self.exe, release(), opener=broken)
        self.assertEqual(sorted(os.listdir(self.dir)), ["OffroadCompanion-1.7.9.exe"])

    def test_changed_file_not_started(self):
        _, path = up.download("1.7.9", self.exe, release(), opener=lambda u: Resp(NEW))
        with open(path, "ab") as f:
            f.write(b"tampered")
        self.assertIsNone(up.staged("1.7.9", self.exe), "its digest no longer matches: never run")
        self.assertFalse(os.path.exists(os.path.join(self.dir, up.STAGED)), "and forgotten")

    def test_hand_over(self):
        up.download("1.7.9", self.exe, release(), opener=lambda u: Resp(NEW))
        started = []

        class Proc:
            def __init__(self, code):
                self.code = code

            def wait(self, timeout):
                if self.code is None:
                    raise subprocess.TimeoutExpired("x", timeout)
                return self.code

        def popen(code):
            def f(cmd, **kw):
                started.append(cmd)
                return Proc(code)
            return f
        self.assertTrue(up.hand_over("1.7.9", self.exe, ["--no-game"], popen=popen(None), out=self.said.append))
        self.assertEqual(os.path.basename(started[0][0]), "OffroadCompanion-1.8.0.exe")
        self.assertEqual(started[0][1:], ["--no-game"], "the same arguments")
        # the new copy dies at once (an antivirus): forgotten, this one runs
        self.assertFalse(up.hand_over("1.7.9", self.exe, [], popen=popen(1), out=self.said.append))
        self.assertIsNone(up.staged("1.7.9", self.exe))
        self.assertIsNone(up.blocked_version(self.exe))
        # Smart App Control: that version not offered again
        up.download("1.7.9", self.exe, release(), opener=lambda u: Resp(NEW))
        self.assertFalse(up.hand_over("1.7.9", self.exe, [], popen=popen(4551), out=self.said.append))
        self.assertEqual(up.blocked_version(self.exe), "1.8.0")
        self.assertFalse(up.update_at_start("1.7.9", self.exe, [], ask=lambda t: self.fail("asked"),
                                            get=lambda u, c: release(), out=self.said.append))

    def test_update_at_start(self):
        asked, started = [], []
        get = lambda u, c: release()            # noqa: E731
        # no: this version starts, nothing downloaded
        self.assertFalse(up.update_at_start("1.7.9", self.exe, [], ask=lambda t: asked.append(t) or False, get=get,
                                            opener=lambda u: self.fail("downloaded"), out=self.said.append))
        self.assertIn("1.8.0", asked[0])
        self.assertIn("BeamMP", asked[0])
        # yes: downloaded, checked, started
        ok = up.update_at_start("1.7.9", self.exe, [], ask=lambda t: True, get=get, opener=lambda u: Resp(NEW),
                                start=lambda: started.append(1) or True, out=self.said.append)
        self.assertTrue(ok and started)
        self.assertTrue(os.path.isfile(os.path.join(self.dir, "OffroadCompanion-1.8.0.exe")))
        # a failed download: this version starts
        os.remove(os.path.join(self.dir, "OffroadCompanion-1.8.0.exe"))
        self.assertFalse(up.update_at_start("1.7.9", self.exe, [], ask=lambda t: True, get=get,
                                            opener=lambda u: Resp(b"short"), start=lambda: self.fail("started"),
                                            out=self.said.append))
        # turned off, or from source: not even asked
        self.assertFalse(up.update_at_start("1.7.9", self.exe, ["--no-update-check"], ask=lambda t: self.fail("asked"),
                                            get=get, out=self.said.append))
        self.assertFalse(up.update_at_start("1.7.9", None, [], ask=lambda t: self.fail("asked"), get=get,
                                            out=self.said.append))


class TestLauncher(unittest.TestCase):
    def test_wired_in_and_outside_the_painter_code(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(here, "app_launcher.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn('ours("appupdate")', src)
        self.assertIn("if self_update(launcher, argv):", src)
        # (gpsd/*.py is the painter's code fingerprint, shared ground's: the updater stays out of it)
        self.assertFalse(os.path.exists(os.path.join(here, "gpsd", "appupdate.py")))
        sys.path.insert(0, os.path.join(os.path.dirname(here), "tools"))
        import build_exe
        self.assertIn("appupdate.py", build_exe.KEEP_FILES)


if __name__ == "__main__":
    unittest.main()
