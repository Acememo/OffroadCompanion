"""Wheel ruts along the dirt track where it blends into the ground (inside BeamNG.Earth's server: numpy, Pillow).

The track is BeamNG.Earth's dirt road material. On light desert sand (San Felipe) it is the ground's own colour and
cannot be seen from the driver's seat, while elsewhere it shows fine (the user, 2026-10-21: "only for where there
would be low contrast between the road and the terrain, I like the current look of the dirt road on other
sections"). The ground in BeamNG.Earth is satellite imagery, so the contrast is judged from the imagery under the
track: BeamNG.Earth's own imagery cache on disk (<cache>/imagery/<source>/<z>/<x>/<y>.jpg, read only, never
fetched here) sampled every STEP_M along each piece of track, its colour compared with the dirt road's (CIELAB
distance, DIRT_REF). Where it is within DE_MAX for at least MIN_RUN_M, two darker rut strips are laid along the
track (extra road pieces of material RUT_MATERIAL, drawn by BeamNG.Earth over the dirt like road markings).
Imagery not cached yet: no ruts there this time (the tile is built again later, with the imagery).

mode "auto" (that), "on" (ruts all along the track), "off".
"""
import math
import os
import threading
import time
from collections import OrderedDict

import numpy as np

RUT_MATERIAL = "egps_ruts"
DIRT_REF = (166, 143, 113)  # the dirt road material's mean colour in daylight (sRGB)
DE_MAX = 20.0               # CIELAB distance under which the track does not stand out
STEP_M = 8.0
MIN_RUN_M = 40.0            # shorter stretches of low contrast: no ruts (no flicker of short pieces)
GAP_M = 24.0                # a short stretch of good contrast inside a low one: ruts carry on over it
RUT_W = 0.55                # m, each rut strip
RUT_TL = 6.0                # m, texture length
RUT_P = 19                  # render priority: over the dirt (21)
ZOOMS = (16, 15, 14, 13)
PREFER = ("md6in", "naip", "naipusda", "usgs", "eox2023", "eox2016")
MEM_TILES = 96
MISS_TTL_S = 10.0           # a tile not cached yet is looked for again after this


def _lin(c):
    c = np.asarray(c, np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lab(rgb):
    """sRGB (..., 3) 0-255 -> CIELAB (D65). Pure."""
    r, g, b = np.moveaxis(_lin(rgb), -1, 0)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b)
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return np.where(t > 216 / 24389, np.cbrt(t), (24389 / 27 * t + 16) / 116)
    fx, fy, fz = f(x), f(y), f(z)
    return np.stack([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)], axis=-1)


def delta_e(rgb, ref=DIRT_REF):
    """CIE76 distance of colours (N, 3) from ref. Pure."""
    return np.linalg.norm(lab(rgb) - lab(np.asarray(ref, np.float64)), axis=-1)


def mercator_px(lat, lon, z):
    n = 256.0 * (1 << z)
    phi = math.radians(max(-85.05, min(85.05, lat)))
    return (lon + 180.0) / 360.0 * n, (1 - math.log(math.tan(phi) + 1 / math.cos(phi)) / math.pi) / 2 * n


class CachedImagery:
    """BeamNG.Earth's imagery tiles on disk, read only: rgb(lats, lons) -> (N, 3), NaN where none is cached."""

    def __init__(self, root):
        self.root = root
        self.lock = threading.Lock()
        self.tiles = OrderedDict()
        self.missing = {}
        self._srcs, self._srcs_at = [], -1e9

    def sources(self):
        now = time.monotonic()
        if not self._srcs or now - self._srcs_at > 60.0:      # (none yet: looked for every time, it is cheap)
            try:
                names = [d for d in os.listdir(self.root) if os.path.isdir(os.path.join(self.root, d))]
            except OSError:
                names = []
            rank = {n: i for i, n in enumerate(PREFER)}
            self._srcs = sorted(names, key=lambda n: (rank.get(n, len(PREFER)), n))
            self._srcs_at = now
        return self._srcs

    def tile(self, src, z, x, y):
        key = (src, z, x, y)
        with self.lock:
            if key in self.tiles:
                self.tiles.move_to_end(key)
                return self.tiles[key]
            if time.monotonic() - self.missing.get(key, -1e9) < MISS_TTL_S:
                return None
        path = os.path.join(self.root, src, str(z), str(x), f"{y}.jpg")
        a = None
        if os.path.isfile(path):
            try:
                from PIL import Image
                with Image.open(path) as im:
                    a = np.asarray(im.convert("RGB"), np.uint8)
            except Exception:
                a = None
        with self.lock:
            if a is None:
                self.missing[key] = time.monotonic()
                if len(self.missing) > 4096:
                    self.missing.clear()
            else:
                self.tiles[key] = a
                while len(self.tiles) > MEM_TILES:
                    self.tiles.popitem(last=False)
        return a

    def rgb(self, lats, lons):
        out = np.full((len(lats), 3), np.nan)
        srcs = self.sources()
        for i, (la, lo) in enumerate(zip(lats, lons)):
            for z in ZOOMS:
                px, py = mercator_px(float(la), float(lo), z)
                tx, ty = int(px // 256), int(py // 256)
                for src in srcs:
                    t = self.tile(src, z, tx, ty)
                    if t is None:
                        continue
                    h, w = t.shape[:2]
                    u = int((px - tx * 256) * w / 256.0)
                    v = int((py - ty * 256) * h / 256.0)
                    patch = t[max(0, v - 1):v + 2, max(0, u - 1):u + 2].reshape(-1, 3)
                    out[i] = patch.mean(axis=0)
                    break
                else:
                    continue
                break
        return out


def resample(n, step):
    """Points every step along a polyline n (k, 3) with the ends: xy (m, 2), s (m,), z (m,). Pure."""
    seg = np.hypot(*np.diff(n[:, :2], axis=0).T)
    cum = np.r_[0.0, np.cumsum(seg)]
    if cum[-1] <= 0:
        return n[:1, :2], np.zeros(1), n[:1, 2]
    s = np.r_[np.arange(0.0, cum[-1], step), cum[-1]]
    xy = np.stack([np.interp(s, cum, n[:, 0]), np.interp(s, cum, n[:, 1])], axis=1)
    return xy, s, np.interp(s, cum, n[:, 2])


def along(n, s0, s1):
    """The nodes of polyline n (k, 3) between arc lengths s0 and s1, with the ends interpolated: the track's own
    nodes, so a rut lies on the track's surface (BeamNG.Earth's road decals take their nodes' heights over its
    terrain meshes: ruts resampled every STEP_M cut into crests and floated over dips, the user 2026-10-21). Pure."""
    seg = np.hypot(*np.diff(n[:, :2], axis=0).T)
    cum = np.r_[0.0, np.cumsum(seg)]
    s0, s1 = max(0.0, float(s0)), min(float(cum[-1]), float(s1))
    if s1 - s0 <= 1e-6:
        return n[:0]

    def at(sv):
        return np.array([np.interp(sv, cum, n[:, k]) for k in range(3)])
    inner = n[(cum > s0 + 1e-6) & (cum < s1 - 1e-6)]
    return np.vstack([at(s0)[None, :], inner, at(s1)[None, :]])


def runs(low, s, min_run=MIN_RUN_M, gap=GAP_M):
    """(i0, i1) index ranges (inclusive) of the low stretches: gaps shorter than gap closed, runs shorter than
    min_run dropped. Pure."""
    low = np.asarray(low, bool).copy()
    idx = np.flatnonzero(low)
    if len(idx) == 0:
        return []
    for a, b in zip(idx[:-1], idx[1:]):
        if b - a > 1 and s[b] - s[a] <= gap:
            low[a:b] = True
    out, i = [], 0
    while i < len(low):
        if not low[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(low) and low[j + 1]:
            j += 1
        if s[j] - s[i] >= min_run:
            out.append((i, j))
        i = j + 1
    return out


def offset(xy, d):
    """The polyline xy shifted d m to its left (d: one number, or one per node). Pure."""
    t = np.gradient(xy, axis=0)
    t /= np.maximum(np.hypot(*t.T), 1e-9)[:, None]
    return xy + np.stack([-t[:, 1], t[:, 0]], axis=1) * np.reshape(np.asarray(d, np.float64), (-1, 1))


# The rutted sections (relief.rut_weight, terrain 5): the ruts drawn there whatever the contrast, braided as many wheels
# leave them (the user, 2026-10-29: photos of rutted Baja tracks): BRAIDS more pairs beside the main one, each wandering
# a little across the track (BRAID_WANDER_M, every BRAID_WAVE_M or so), hashed from the place so everyone sees the same.
RUTTED = 0.3                # rut_weight from which a stretch counts as rutted
BRAIDS = ((0.38, 0.8), (-0.3, 0.65))     # (offset from the main pair, m; share of the length it runs)
BRAID_WANDER_M, BRAID_WAVE_M = 0.3, 30.0
BRAID_RUN_M = 70.0          # the braids come and go over about this
BRAID_STEP_M = 3.0


def _global_xy(lat, lon):
    from .relief import global_xy
    return global_xy(lat, lon)


def _vnoise(x, y, salt):
    from .relief import vnoise
    return vnoise(x, y, salt)


ON_LINE_M = 25.0            # a dirt piece this close to the course line (beyond its half width) is on the course (a
                            # dirt road it follows is its from this far off: courseroads.FOLLOW_UNPAVED_M)


def _seg_dist(p, a, b):
    d = b - a
    L2 = np.maximum((d * d).sum(axis=1), 1e-12)
    t = np.clip(((p[:, None, :] - a[None, :, :]) * d[None, :, :]).sum(axis=2) / L2[None, :], 0, 1)
    q = a[None, :, :] + t[:, :, None] * d[None, :, :]
    return np.hypot(*(q - p[:, None, :]).transpose(2, 0, 1))


def rut_chunks(chunks, frame, imagery, mode="auto", course_xy=(), track_material="m_dirt_road", rutted_fn=None):
    """Rut strips (chunks in BeamNG.Earth's road-tile form) along the dirt pieces among chunks (track_material: their
    material, or a set of them) that lie on the
    course (course_xy: its line(s) in the frame, (k, 2) each): the dirt track laid for it, or a dirt road it
    follows. (A road tile's pieces carry no feature id but on bridge decks, so the course is found by place.)
    rutted_fn(xy (k, 2) frame m) -> (k,) rut weight (relief.ruts_at): its rutted sections get ruts whatever the contrast,
    braided (Off: none anywhere)."""
    if mode == "off" or not len(course_xy):
        return []
    mats = {track_material} if isinstance(track_material, str) else set(track_material)
    ca = np.concatenate([c[:-1] for c in course_xy if len(c) >= 2])
    cb = np.concatenate([c[1:] for c in course_xy if len(c) >= 2])
    out = []
    for c in chunks:
        if c.get("deck") or c.get("m") not in mats:
            continue
        n = np.asarray(c.get("n") or [], np.float64)
        if n.ndim != 2 or len(n) < 2:
            continue
        xy, s, z = resample(n, STEP_M)
        if len(s) < 2:
            continue
        w = float(c.get("w") or 4.0)
        on = _seg_dist(xy, ca, cb).min(axis=1) <= w / 2 + ON_LINE_M
        if not on.any():
            continue
        rut = np.zeros(len(xy), bool)
        if rutted_fn is not None:
            rut = on & (np.asarray(rutted_fn(xy), np.float64) >= RUTTED)
        if mode == "on":
            low = on
        elif imagery is None:
            if not rut.any():
                continue
            low = np.zeros(len(xy), bool)      # (no photo to judge the contrast by: the rutted sections only)
        else:
            la, lo, _ = frame.enu_to_geodetic(xy[:, 0], xy[:, 1], np.zeros(len(xy)))
            rgb = imagery.rgb(np.atleast_1d(la), np.atleast_1d(lo))
            de = delta_e(np.nan_to_num(rgb, nan=0.0))
            low = on & np.isfinite(rgb).all(axis=1) & (de < DE_MAX)
        low = low | rut
        half = float(min(0.95, max(0.55, w * 0.2)))
        strips = []
        for i0, i1 in runs(low, s, MIN_RUN_M if mode == "auto" else 0.0):
            part = along(n, s[i0], s[i1])          # the track's own nodes (its heights), cut to the run
            if len(part) >= 2:
                strips += [(part, half), (part, -half)]
        # braids over the rutted runs, beside the main pair: where each runs and how it wanders are noises of the place
        # on the Earth (not of the tile or the world's frame), so everyone sees the same
        for i0, i1 in runs(rut, s, MIN_RUN_M):
            part = along(n, s[i0], s[i1])
            if len(part) < 2:
                continue
            bxy, _bs, bz = resample(part, BRAID_STEP_M)
            if len(bxy) < 3:
                continue
            la, lo, _ = frame.enu_to_geodetic(bxy[:, 0], bxy[:, 1], np.zeros(len(bxy)))
            gx, gy = _global_xy(np.atleast_1d(la), np.atleast_1d(lo))
            nodes = np.column_stack([bxy, bz])
            for k, (db, share) in enumerate(BRAIDS):
                present = _vnoise(gx / BRAID_RUN_M, gy / BRAID_RUN_M, 61 + k) < share
                wander = BRAID_WANDER_M * (2.0 * _vnoise(gx / BRAID_WAVE_M, gy / BRAID_WAVE_M, 71 + k) - 1.0)
                j = 0
                while j < len(nodes):
                    if not present[j]:
                        j += 1
                        continue
                    e = j
                    while e + 1 < len(nodes) and present[e + 1]:
                        e += 1
                    if e - j >= 2:
                        sl = slice(j, e + 1)
                        for sgn in (1, -1):
                            strips.append((nodes[sl], sgn * (half + db) + wander[sl]))
                    j = e + 1
        for part, d in strips:
            p = offset(part[:, :2], d)
            r = {"m": RUT_MATERIAL, "w": RUT_W, "tl": RUT_TL, "p": RUT_P,
                 "n": [[round(float(a), 3), round(float(b), 3), round(float(h), 3)] for (a, b), h in zip(p, part[:, 2])]}
            # laid over the ground like the track (BeamNG.Earth's road mesh drapes every piece not "fixed": only
            # bridge decks and tunnel floors are; a rut marked fixed kept its nodes' heights and floated,
            # the user 2026-10-21)
            if c.get("fixed"):
                r["fixed"] = True
            out.append(r)
    return out
