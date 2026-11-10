"""Offroad Companion updates itself (the user, 2026-11-09: "Is there a way to add an autoupdate feature?").

At each start of the .exe (app_launcher.run), before anything else starts: GitHub's latest Offroad Companion release
(REPO's releases/latest: never a draft or a pre-release) is compared with this copy's VERSION. When it is newer, a
pop-up asks whether to install it now (yes / no; BeamNG.Earth's own launcher.update_popup). Yes downloads that
release's OffroadCompanion-<version>.exe beside this one, checks its size and the SHA-256 digest GitHub publishes for
the release asset (a file without one, or one that does not match, is deleted, never run), notes it in STAGED beside
it, and starts it with the same arguments; this one ends. No starts this version, and it asks again next time.

The running .exe is never touched (Windows cannot replace a running .exe): a shortcut to it keeps working, because
every start of the old file hands over to the downloaded one (hand_over: the note and the file's digest checked
again). A new copy that dies at once (an antivirus, Windows Smart App Control, which runs only signed apps) is
forgotten and this one runs; with Smart App Control that version is not offered again (BLOCKED).

The same scheme as BeamNG.Earth's own updater (its server/selfupdate.py and launcher.update_at_start / hand_over), with
this project's releases instead of BeamNG.Earth's: the BeamNG.Earth inside comes with Offroad Companion's releases, so
the two always match (the same ground for everyone on a BeamMP server). The BeamMP server zip is not updated here: a
host replaces it by hand. Offline, GitHub not answering, a source copy, --no-update-check or
OFFROAD_COMPANION_NO_UPDATE=1: nothing asked, this version starts. One request to api.github.com per start (60 an hour
are allowed without a token).
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request

REPO = "Acememo/OffroadCompanion"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE_URL = f"https://github.com/{REPO}/releases"
ASSET_PREFIX = f"https://github.com/{REPO}/releases/download/"
ASSET_RE = re.compile(r"OffroadCompanion-(\d+\.\d+\.\d+)\.exe")
STAGED = "OffroadCompanion-update.json"         # beside the downloaded file: {"version", "path", "sha256"}
BLOCKED = "OffroadCompanion-update-blocked.json"
NO_UPDATE_ENV = "OFFROAD_COMPANION_NO_UPDATE"
CHECK_TIMEOUT_S = 8         # GitHub's answer waited for this long at most (offline: the game starts without delay)
DOWNLOAD_TIMEOUT_S = 60
CHUNK = 1 << 16
HANDOVER_CHECK_S = 5.0      # the new copy must still run this long after its start (else: this one runs)
TITLE = "Offroad Companion update"


class UpdateError(RuntimeError):
    """The update could not be downloaded or checked (the message says why, for the player)."""


# -- versions -------------------------------------------------------------------------------------------------------
def parse(v):
    """(major, minor, patch) of "1.7.9" / "v1.7.9", or None (anything else: a pre-release, a dev build)."""
    m = re.fullmatch(r"\s*v?(\d+)\.(\d+)\.(\d+)\s*", str(v or ""))
    return tuple(int(g) for g in m.groups()) if m else None


def newer(latest, current):
    a, b = parse(latest), parse(current)
    return a is not None and b is not None and a > b


# -- GitHub ---------------------------------------------------------------------------------------------------------
def _ssl_context():
    try:
        import netfetch                 # BeamNG.Earth's: Windows' own certificate check (truststore)
        return netfetch.windows_ssl_context()
    except Exception:
        return None


def _request(url, accept=None, current=None):
    headers = {"User-Agent": f"OffroadCompanion/{current or '?'} (+{PAGE_URL})"}
    if accept:
        headers["Accept"] = accept
    return urllib.request.Request(url, headers=headers)


def get_json(url, current=None, timeout=CHECK_TIMEOUT_S):
    req = _request(url, "application/vnd.github+json", current)
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
        return json.loads(resp.read(4 << 20).decode("utf-8", "replace"))


def pick(release):
    """(version, name, url, size, sha256) of the release's .exe, or None. Only a published release (not a draft or a
    pre-release) whose tag is a plain version, an asset named OffroadCompanion-<that version>.exe under this
    project's release downloads, with GitHub's SHA-256 digest, counts."""
    if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
        return None
    version = str(release.get("tag_name") or "").lstrip("v")
    if parse(version) is None:
        return None
    for a in release.get("assets") or ():
        if not isinstance(a, dict):
            continue
        name, url, digest = str(a.get("name") or ""), str(a.get("browser_download_url") or ""), str(a.get("digest") or "")
        m = ASSET_RE.fullmatch(name)
        if not m or m.group(1) != version or not url.startswith(ASSET_PREFIX):
            continue
        if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
            continue
        return version, name, url, int(a.get("size") or 0), digest[7:].lower()
    return None


def check(current, get=None):
    """{"current", "latest", "url"} when GitHub's latest release is newer than current and has a checked .exe, else
    None (up to date, offline, no such file, this version blocked by Windows). Never raises."""
    if parse(current) is None:
        return None
    try:
        release = (get or get_json)(LATEST_API, current)
    except Exception:
        return None
    got = pick(release)
    if got is None or not newer(got[0], current):
        return None
    return {"current": current, "latest": got[0], "url": f"{PAGE_URL}/tag/v{got[0]}", "release": release}


# -- the files beside the running .exe --------------------------------------------------------------------------------
def packaged_path(frozen=None, executable=None):
    """The running .exe, or None (a source copy)."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    p = executable or sys.executable
    return p if frozen and str(p).lower().endswith(".exe") else None


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _remove(p):
    try:
        os.remove(p)
    except OSError:
        pass


def download(current, path, release, opener=None, progress=None):
    """The release's .exe downloaded beside path (the running .exe), checked, and noted (STAGED). -> (version, its
    path). Raises UpdateError."""
    got = pick(release)
    if got is None:
        raise UpdateError("the latest release has no checked download for Windows")
    version, name, url, size, digest = got
    if not newer(version, current):
        raise UpdateError(f"already up to date ({current})")
    folder = os.path.dirname(os.path.abspath(path))
    dest = os.path.join(folder, name)
    if os.path.normcase(os.path.abspath(dest)) == os.path.normcase(os.path.abspath(path)):
        raise UpdateError("the new file has this file's name")
    if not (os.path.isfile(dest) and sha256_of(dest) == digest):
        part = dest + ".part"
        try:
            opener = opener or (lambda u: urllib.request.urlopen(_request(u, current=current),
                                                                 timeout=DOWNLOAD_TIMEOUT_S, context=_ssl_context()))
            with opener(url) as resp:
                final = resp.geturl() if hasattr(resp, "geturl") else url
                if not str(final).startswith("https://"):
                    raise UpdateError("the download was redirected off https")
                done = 0
                with open(part, "wb") as f:
                    while True:
                        chunk = resp.read(CHUNK)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if progress:
                            progress(done, size)
        except UpdateError:
            _remove(part)
            raise
        except Exception as e:
            _remove(part)
            raise UpdateError(f"the download failed ({e})") from e
        if (size and os.path.getsize(part) != size) or sha256_of(part) != digest:
            _remove(part)
            raise UpdateError("the downloaded file did not match GitHub's checksum (deleted)")
        os.replace(part, dest)
    tmp = os.path.join(folder, STAGED + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"version": version, "path": name, "sha256": digest}, f)
    os.replace(tmp, os.path.join(folder, STAGED))
    return version, dest


def staged(current, path):
    """The downloaded newer copy to start instead of this one, or None. Its digest checked again; the note removed
    when that file is gone or changed (kept when it is not newer: the new copy reads it too, and the old one, started
    again from the player's shortcut, still hands over)."""
    if not path:
        return None
    folder = os.path.dirname(os.path.abspath(path))
    note = os.path.join(folder, STAGED)
    try:
        with open(note, encoding="utf-8") as f:
            d = json.load(f)
        version, name, digest = str(d["version"]), str(d["path"]), str(d["sha256"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    new = os.path.join(folder, os.path.basename(name))
    if not newer(version, current) or os.path.normcase(os.path.abspath(new)) == os.path.normcase(os.path.abspath(path)):
        return None
    if not ASSET_RE.fullmatch(os.path.basename(name)) or not (os.path.isfile(new) and sha256_of(new) == digest):
        _remove(note)
        return None
    return new


def drop_staged(path, blocked_by=None):
    """Forget the downloaded copy (it would not start): this one runs from now on. blocked_by: its version is not
    offered again (BLOCKED)."""
    folder = os.path.dirname(os.path.abspath(path))
    note = os.path.join(folder, STAGED)
    if blocked_by:
        try:
            with open(note, encoding="utf-8") as f:
                version = str(json.load(f)["version"])
            with open(os.path.join(folder, BLOCKED), "w", encoding="utf-8") as f:
                json.dump({"version": version, "by": str(blocked_by)}, f)
        except (OSError, ValueError, KeyError, TypeError):
            pass
    _remove(note)


def blocked_version(path):
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(path)), BLOCKED), encoding="utf-8") as f:
            return str(json.load(f)["version"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


# -- at the start of the .exe -----------------------------------------------------------------------------------------
def disabled(argv, environ=None):
    environ = os.environ if environ is None else environ
    cut = argv.index("--") if "--" in argv else len(argv)
    return "--no-update-check" in argv[:cut] or environ.get(NO_UPDATE_ENV) == "1"


def hand_over(current, path, argv, launcher=None, popen=None, out=print):
    """A newer copy downloaded beside this one: start it with these arguments instead. True when it was started (this
    one then ends)."""
    new = staged(current, path)
    if not new:
        return False
    is_win = os.name == "nt"
    out(f"  Starting the updated Offroad Companion: {os.path.basename(new)}")
    env = dict(os.environ)
    try:
        if launcher is not None and hasattr(launcher, "clean_env"):
            env = launcher.clean_env()
    except Exception:
        pass
    try:
        proc = (popen or subprocess.Popen)([new] + list(argv), env=env, cwd=os.path.dirname(new),
                                           **({"creationflags": subprocess.CREATE_NEW_CONSOLE} if is_win
                                              else {"start_new_session": True}))
    except OSError as e:
        code = str(e)
    else:
        try:
            code = proc.wait(timeout=HANDOVER_CHECK_S)
        except subprocess.TimeoutExpired:
            return True
        if code == 0:
            return True
    sac = False
    try:
        sac = bool(launcher and launcher.smart_app_control_on()) or "4551" in str(code)
    except Exception:
        sac = "4551" in str(code)
    if sac:
        msg = (f"  Windows Smart App Control blocked the updated Offroad Companion ({os.path.basename(new)}). It only "
               "runs apps from a verified publisher, and Offroad Companion is not code-signed. This version keeps "
               "working, and that version will not be offered again: download it from GitHub yourself if you want it.")
    else:
        msg = (f"  The updated Offroad Companion ({os.path.basename(new)}) closed right after starting ({code}). "
               "Starting this version instead. An antivirus may have blocked it.")
    out(msg)
    drop_staged(path, blocked_by="smart_app_control" if sac else None)
    return False


def update_at_start(current, path, argv, launcher=None, ask=None, get=None, opener=None, start=None, out=print):
    """Before anything starts: a newer release on GitHub? Ask (a pop-up), download it, start it. True when the new
    copy was started (this one then ends). Offline, up to date, declined or failed: False (this version starts)."""
    if not path or disabled(argv):
        return False
    got = check(current, get)
    if not got or got["latest"] == blocked_version(path):
        return False
    text = (f"Offroad Companion {got['latest']} is out (you have {got['current']}).\n\n"
            "Install it now, before the game starts?\n\n"
            "Yes downloads it and starts the new version.\nNo starts this version.\n\n"
            "On a BeamMP server, everyone should use the same version.")
    out(f"  Update        Offroad Companion {got['latest']} is out (you have {got['current']})")
    yes = None
    try:
        if ask is not None:
            yes = ask(text)
        elif launcher is not None and hasattr(launcher, "update_popup"):
            old = getattr(launcher, "UPDATE_TITLE", None)
            launcher.UPDATE_TITLE = TITLE
            try:
                yes = launcher.update_popup(text)
            finally:
                if old is not None:
                    launcher.UPDATE_TITLE = old
    except Exception:
        yes = None
    if yes is None and sys.stdin and sys.stdin.isatty():
        try:
            yes = input("  Install it now, before the game starts? [Y/n] ").strip().lower() in ("", "y", "yes")
        except (EOFError, OSError, KeyboardInterrupt):
            yes = False
    if not yes:
        out(f"  Starting this version. (The new one: {got['url']})")
        return False
    last = [-1]

    def progress(done, total):
        if total:
            pct = done * 100 // total
            if pct != last[0] and pct % 5 == 0:
                last[0] = pct
                sys.stdout.write(f"\r  Downloading... {pct}% ({done >> 20} of {total >> 20} MB)")
                sys.stdout.flush()
    try:
        version, _ = download(current, path, got["release"], opener=opener, progress=progress)
    except Exception as e:
        out("")
        out(f"  The update could not be downloaded: {e}. Starting this version instead.")
        return False
    out("")
    out(f"  Update        Offroad Companion {version} downloaded")
    return (start or (lambda: hand_over(current, path, argv, launcher, out=out)))()
