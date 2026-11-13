"""The ground under the course as it is in the real place (the user, 2026-10-28: "sandy sections like in baja, but only
on places where there would be sand or sandy section irl, also some mud on some parts when around water ... loose dirt
where it would be and hard dirt where it would be irl ... Realism is my most wanted feature so don't over do it").

BeamNG.Earth gives every 2 m sample of the physics ground a BeamNG ground model from the land cover (server
surface.py: bare land loose dirt, shrubland dusty dirt, grass, wetland mud, steep ground rock) and paints the roads over
it, the course's dirt track as plain dirt. Along the course (its track and CORRIDOR_M beside it) this puts the ground
the place has instead, from what is mapped and measured there, never at random:

    sand        dry washes (streams and rivers mapped intermittent, in dry country), sandy canyon floors (the ground
                rising on both sides, in bare desert), beaches (within BEACH_M of the sea)
    mud         the banks of rivers, streams, lakes and ponds that hold water all year (BANK_M), and wetlands
    gravel      a creek bed in green country (intermittent streams outside the desert), the track over rocky ground
    hard dirt   graded dirt roads the course follows, dry lake beds (playas: packed hard), tracks through green
                country
    loose dirt  a desert track's sides and the sand pushed to the outside of its turns; its racing line is packed
                (dusty dirt)

Everything else (paved roads, the steep rock, snow, the ground away from the course) stays as BeamNG.Earth made it.

The facts come from the course's relief windows (relief.window_profile, from terrain version FROM_TV): per sample of
the course, the canyon rise, a mapped dirt road followed, the share of dry land (WorldCover bare / sparse and shrubland
around the track) and of wetland, and the water around the window (Overture's water, BeamNG.Earth's pinned release:
window_facts). They are planned once per course and kept, like the rest of the course's ground, so every computer
with the same ground code gets the same sand and mud. Pure numpy.
"""
import math

import numpy as np

FROM_TV = 3                 # the terrain version the course's ground surfaces came in with
CORRIDOR_M = 20.0           # beside the track's edge: the natural ground's rules reach this far
BANK_M = 6.0                # mud this far from water that is there all year (past a line's half width)
BEACH_M = 45.0              # sand this far inland from the sea
WASH_MARGIN_M = 2.5         # a dry wash's sand this far past its mapped half width
CANYON_SAND = 0.6           # the canyon fact (both sides rise 3 .. 12 m) from which a desert floor is sand
CANYON_REACH_M = 6.0        # ... across the floor this far past the track's edge
ARID = 0.5                  # the share of dry land (bare / shrubland) from which the place is dry country
WETLAND = 0.5
ROCKY = 0.55                # the rock fact from which the track runs on gravel
PACKED_SHARE = 0.45         # a desert track's middle (this share of its half width) is packed: the racing line
EDGE_IN_M, EDGE_OUT_M = 0.6, 1.5    # a track's sides: loose from this far inside its edge to this far outside
TURN_DEG = 2.0              # a turn of this many degrees per sample or more piles loose dirt on its outside
# the land cover around the track (ESA WorldCover classes): dry land and wetland
DRY_CLASSES = (60, 20)      # bare / sparse vegetation, shrubland
WET_CLASSES = (90, 95)      # herbaceous wetland, mangroves
# (terrain 4; the user, 2026-10-28, a screenshot of scrub growing only along the track: "vegetation like this should
# only be present where there is also vegetation around the course, and if there is vegetation on the track, some
# parts of it should be without it, either where the tires go through it, the almost the whole lane, or two small
# lanes. Lets keep performance in mind"). BeamNG.Earth's ground cover (its groundcover.lua) grows on the GRASS, LAWN
# and DUSTY layers only: terrain 3 packed a desert track's middle as DUSTY, so scrub grew on the racing line of a bare
# desert. From terrain 4 the track carries those layers only where the land beside it is covered (COVER of the land
# cover classes beside it: trees, shrubs, grass, crops) and never where the wheels go: its middle strip between the
# wheel paths (a two-track's hump, on a track wide enough for two lanes) and its edges; the wheel paths bare. Which
# stretches keep a grassy middle, a long hash of the course's place (LANES_M), so some run bare wall to wall. Nothing
# new is drawn: the same layers, so the same cost.
COVER_TV = 4
COVER_CLASSES = (10, 20, 30, 40)    # tree cover, shrubland, grassland, cropland
GRASS_CLASSES = (10, 30, 40)        # ... of them the green ones (their middle strip: short grass; shrubland's: scrub)
COVER = 0.5                         # the share of covered land beside the track from which it has plants
MIDDLE_M = 0.8                      # the middle strip (a two-track's hump) this far either side of the middle
MIDDLE_FROM_HW = 2.6                # ... on a track at least this wide (half width: room for two wheel paths)
EDGE_COVER_M = 0.5                  # the plants reach this far in over the track's edge
LANES_M = 260.0                     # stretches this long either keep a grassy middle or run bare
LANES_P = 0.6                       # ... the share that keeps it
LAND_OFFS_M = (0.0, 12.0, 30.0)     # the land cover read on the course line and this far either side
WATER_PAD_M = 90.0          # the water around a window kept this far past its samples
# Overture water (subtype, class): lines' half widths (m) by kind
LINE_HALF_M = {"river": 7.0, "stream": 2.0, "canal": 3.0}
RIVER_SUBTYPES = ("river", "stream", "canal")
LAKE_SUBTYPES = ("lake", "pond", "reservoir", "water")
SEA_SUBTYPES = ("ocean", "sea")
SKIP_CLASSES = ("drain", "ditch", "fish_pass", "fountain", "swimming_pool", "reflecting_pool")
M_PER_DEG = 111320.0
# (terrain 7: the track's sections, variety.py: sand traps, rock sections, gravel, rock crawls)
VARIETY_TV = 7
# (terrain 14; the user, 2026-11-12, a screenshot of the track in blocks of sand and dirt a few metres long, square
# edges: "Can we do something to make the terrain transitions look more natural"). The facts the ground's kinds are
# chosen by flickered from sample to sample (10 m) about their thresholds, and every boundary was a straight line: across
# the track where a fact crossed its threshold, along it at a fixed distance from its edge. From terrain 14 the facts
# are smoothed along the course over ~100 m (window_facts, relief.window_profile), each threshold is moved about by a
# noise of the place (DITHER: patches tens of metres across, so a change comes as ragged tongues of one ground into
# the other) and every distance by another (JITTER: the track's edge, its loose sides, a wash's sand, a bank's mud
# wander by a metre or so).
NATURAL_TV = 14
DITHER_M, DITHER_A = 35.0, 0.45     # the thresholds' noise: its size (m), its swing (of a 0 .. 1 fact, peak to peak)
JITTER_M = 9.0                      # the distances' noise: its size (m) ...
JITTER = {"track": 0.8, "packed": 0.12, "berm": 0.8, "canyon": 2.5, "wash": 1.5, "beach": 10.0, "bank": 2.0,
          "variety": 1.2}           # ... and its swing (m, peak to peak; packed: of the half width's share)
WASH_NEAR_M = (3.0, 15.0)   # the course line this near a dry wash's edge: in it .. not by it
SEA_NEAR_M = (20.0, 60.0)


def _ramp_(v, lo, hi):
    t = np.clip((np.asarray(v, np.float64) - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3 - 2 * t)

# the ground models these surfaces need beyond BeamNG.Earth's (surface.MATERIALS): TerrainMaterials the mod's level
# file defines (levels/beamng_earth/art/terrains/offroad_companion.materials.json). Named bngEarth...: BeamNG.Earth 1.7.1
# switches the base maps of every TerrainMaterial so named to the ground photo size chosen (terrain.applyBaseSize); a
# layer left at another size would not match the texture set's (1.6.3: ocGroundSand, ocGroundGravel)
EXTRA_MATERIALS = (("bngEarthGroundOcSand", "SAND"), ("bngEarthGroundOcGravel", "GRAVEL"))


def water_kind(subtype, cls, intermittent, salt, polygon):
    """(kind, half width m) of an Overture water feature for the ground beside it: "wash" (a dry streambed: the river
    or stream is mapped intermittent), "bank" (water there all year: rivers, streams, lakes, ponds), "sea"; None for
    the rest (drains, ditches, pools; salt or dry lakes: relief's lake fact, their beds stay packed)."""
    sub, cl = str(subtype or "").lower(), str(cls or "").lower()
    if cl in SKIP_CLASSES:
        return None
    if sub in SEA_SUBTYPES or cl in SEA_SUBTYPES:
        return ("sea", 0.0) if polygon else None
    river = sub in RIVER_SUBTYPES or cl in RIVER_SUBTYPES
    half = 0.0 if polygon else LINE_HALF_M.get(cl, LINE_HALF_M.get(sub, 2.0))
    if river:
        return ("wash", half) if intermittent else ("bank", half)
    if sub in LAKE_SUBTYPES or cl in LAKE_SUBTYPES:
        if intermittent or salt:
            return None
        return ("bank", 0.0) if polygon else None
    return None


# -- planning: the facts of a window -----------------------------------------------------------------------------
def _clip_ring(ring, box):
    """A polygon ring (k, 2) clipped to box (x0, y0, x1, y1) (Sutherland-Hodgman). Pure."""
    pts = [tuple(p) for p in np.asarray(ring, np.float64)]
    x0, y0, x1, y1 = box
    for axis, lim, keep_lo in ((0, x0, False), (0, x1, True), (1, y0, False), (1, y1, True)):
        if not pts:
            break
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            ci = cur[axis] <= lim if keep_lo else cur[axis] >= lim
            pi = prev[axis] <= lim if keep_lo else prev[axis] >= lim
            if ci != pi:
                t = (lim - prev[axis]) / (cur[axis] - prev[axis])
                out.append((prev[0] + t * (cur[0] - prev[0]), prev[1] + t * (cur[1] - prev[1])))
            if ci:
                out.append(cur)
        pts = out
    return np.asarray(pts, np.float64).reshape(-1, 2)


def _clip_line(line, box):
    """The parts of a polyline (k, 2) inside box (x0, y0, x1, y1): [(m, 2)] (Liang-Barsky per segment). Pure."""
    x0, y0, x1, y1 = box
    line = np.asarray(line, np.float64)
    parts, cur = [], []
    for a, b in zip(line[:-1], line[1:]):
        d = b - a
        t0, t1 = 0.0, 1.0
        ok = True
        for p, q in ((-d[0], a[0] - x0), (d[0], x1 - a[0]), (-d[1], a[1] - y0), (d[1], y1 - a[1])):
            if p == 0:
                if q < 0:
                    ok = False
                    break
                continue
            r = q / p
            if p < 0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
            if t0 > t1:
                ok = False
                break
        if not ok:
            if len(cur) >= 2:
                parts.append(np.asarray(cur))
            cur = []
            continue
        pa, pb = a + t0 * d, a + t1 * d
        if not cur or np.hypot(*(np.asarray(cur[-1]) - pa)) > 1e-12:
            if len(cur) >= 2:
                parts.append(np.asarray(cur))
            cur = [tuple(pa)]
        cur.append(tuple(pb))
        if t1 < 1.0:
            parts.append(np.asarray(cur))
            cur = []
    if len(cur) >= 2:
        parts.append(np.asarray(cur))
    return parts


def window_facts(lat, lon, x, y, tx, ty, pl, canyon, road, s0, s1, land_fn=None, waters_fn=None, tv=FROM_TV):
    """The ground's facts of a window's samples s0 .. s1 - 1 (relief.window_profile's context arrays: positions,
    plane coordinates, unit directions, its plane, the canyon rise and road flags per sample): {canyon, road, arid,
    wetl, waters}. waters: [{k: wash | bank | sea, w: half width, poly: 0 / 1, ll: [[lon, lat]...]}], the water around
    the window, clipped to its box. Pure given the functions (they raise while their data is missing)."""
    from .relief import _mean
    n = len(lat)
    r = 5 if tv >= NATURAL_TV else 2        # (terrain 14: smoothed along the course over ~100 m: NATURAL_TV)

    def out(v, nd=3):
        return [round(float(u), nd) for u in np.asarray(v)[s0:s1]]
    facts = {"canyon": out(_mean(np.asarray(canyon, np.float64), 4 if tv >= NATURAL_TV else 2)), "road": out(road, 2)}
    if land_fn is not None:
        qx, qy = [x], [y]
        for o in LAND_OFFS_M[1:]:
            for sgn in (1.0, -1.0):
                qx.append(x - ty * sgn * o)
                qy.append(y + tx * sgn * o)
        qla, qlo = pl.ll(np.concatenate(qx), np.concatenate(qy))
        cls = np.asarray(land_fn(np.asarray(qla).tolist(), np.asarray(qlo).tolist()), np.int64).reshape(len(qx), n)
        dry = np.isin(cls, DRY_CLASSES).mean(axis=0)
        wet = np.isin(cls, WET_CLASSES).mean(axis=0)
        facts["arid"] = out(_mean(dry, r))
        facts["wetl"] = out(_mean(wet, r))
        if tv >= COVER_TV:                  # (terrain 4: the plants beside the track, not on its line)
            beside = cls[1:]
            facts["cover"] = out(_mean(np.isin(beside, COVER_CLASSES).mean(axis=0), r))
            facts["grass"] = out(_mean(np.isin(beside, GRASS_CLASSES).mean(axis=0), r))
    if waters_fn is not None:
        pad_la = WATER_PAD_M / M_PER_DEG
        pad_lo = pad_la / max(0.05, math.cos(math.radians(float(np.mean(lat)))))
        box = (float(np.min(lon)) - pad_lo, float(np.min(lat)) - pad_la, float(np.max(lon)) + pad_lo,
               float(np.max(lat)) + pad_la)
        ws = []
        for k, w, poly, ll in waters_fn(box[1], box[0], box[3], box[2]) or ():
            ll = np.asarray(ll, np.float64).reshape(-1, 2)
            if len(ll) < 2:
                continue
            parts = [_clip_ring(ll, box)] if poly else _clip_line(ll, box)
            for p in parts:
                if len(p) >= (3 if poly else 2):
                    ws.append({"k": k, "w": round(float(w), 2), "poly": 1 if poly else 0,
                               "ll": [[round(float(a), 7), round(float(b), 7)] for a, b in p]})
        ws.sort(key=lambda d: (d["k"], d["ll"][0], len(d["ll"])))
        facts["waters"] = ws
        if tv >= VARIETY_TV:                # (terrain 7: how near the course line runs to a dry wash, to the sea)
            dist = water_distances(ws, lat, lon)
            rw = 3 if tv >= NATURAL_TV else 1
            facts["washn"] = out(_mean(1.0 - _ramp_(dist["wash"], *WASH_NEAR_M), rw))
            facts["sean"] = out(_mean(1.0 - _ramp_(dist["sea"], *SEA_NEAR_M), rw))
    return facts


# -- the ground at a block's samples -----------------------------------------------------------------------------
def _seg_dist(px, py, ax, ay, bx, by):
    """(P,) distances of the points to the nearest of the segments a -> b (each (S,)). Pure."""
    best = np.full(len(px), np.inf)
    CH = 256
    for j0 in range(0, len(ax), CH):
        sl = slice(j0, j0 + CH)
        dx, dy = (bx[sl] - ax[sl])[None], (by[sl] - ay[sl])[None]
        L2 = np.maximum(dx * dx + dy * dy, 1e-12)
        t = np.clip(((px[:, None] - ax[sl][None]) * dx + (py[:, None] - ay[sl][None]) * dy) / L2, 0, 1)
        ex, ey = px[:, None] - (ax[sl][None] + t * dx), py[:, None] - (ay[sl][None] + t * dy)
        best = np.minimum(best, np.sqrt(ex * ex + ey * ey).min(axis=1))
    return best


def _inside(px, py, rx, ry):
    """0 / 1 per point: inside the ring (even-odd). Pure."""
    ins = np.zeros(len(px), bool)
    xb, yb = np.roll(rx, -1), np.roll(ry, -1)
    for i in range(len(rx)):
        c = (ry[i] > py) != (yb[i] > py)
        if c.any():
            xi = rx[i] + (py[c] - ry[i]) * (xb[i] - rx[i]) / ((yb[i] - ry[i]) or 1e-30)
            ins[c] ^= px[c] < xi
    return ins


def water_distances(waters, lat, lon):
    """{kind: (P,) distance (m) to the nearest such water's edge (0 inside a polygon), past its half width} for the
    points. Pure."""
    lat0 = float(np.mean(lat)) if len(lat) else 0.0
    kx = M_PER_DEG * math.cos(math.radians(lat0))
    lon0 = float(np.mean(lon)) if len(lon) else 0.0
    px, py = (np.asarray(lon) - lon0) * kx, (np.asarray(lat) - lat0) * M_PER_DEG
    out = {k: np.full(len(px), np.inf) for k in ("wash", "bank", "sea")}
    seen = set()
    for w in waters:
        key = (w["k"], w["poly"], tuple(map(tuple, w["ll"])))
        if key in seen:                     # (the same water in two windows)
            continue
        seen.add(key)
        ll = np.asarray(w["ll"], np.float64)
        rx, ry = (ll[:, 0] - lon0) * kx, (ll[:, 1] - lat0) * M_PER_DEG
        reach = {"wash": WASH_MARGIN_M, "bank": BANK_M, "sea": BEACH_M}[w["k"]] + float(w["w"]) + 1.0
        m = (px >= rx.min() - reach) & (px <= rx.max() + reach) & (py >= ry.min() - reach) & (py <= ry.max() + reach)
        if not m.any():
            continue
        sel = np.flatnonzero(m)
        if w["poly"]:
            ax, ay, bx, by = rx, ry, np.roll(rx, -1), np.roll(ry, -1)
        else:
            ax, ay, bx, by = rx[:-1], ry[:-1], rx[1:], ry[1:]
        d = _seg_dist(px[sel], py[sel], ax, ay, bx, by) - float(w["w"])
        if w["poly"]:
            d = np.where(_inside(px[sel], py[sel], rx, ry), 0.0, d)
        d = np.maximum(d, 0.0)
        out[w["k"]][sel] = np.minimum(out[w["k"]][sel], d)
    return out


def course_surfaces(idx, lat, lon, course, profiles, mats, near=None):
    """idx (BeamNG.Earth's material per block sample, any shape; mats: material name -> its index, as surface.py's
    MATERIALS plus EXTRA_MATERIALS) with the course's ground (the module doc) along it. near: relief.nearest's answer
    for these points (computed when None). Courses of terrain versions before FROM_TV: unchanged. Pure."""
    from . import relief
    shape = np.shape(idx)
    out = np.asarray(idx).ravel().copy()
    profiles = {k: p for k, p in profiles.items() if p}
    if not profiles or not len(out) or getattr(course, "tv", 1) < FROM_TV:
        return out.reshape(shape)
    lat = np.asarray(lat, np.float64).ravel()
    lon = np.asarray(lon, np.float64).ravel()
    pts, d, s = near if near is not None else relief.nearest(course, profiles, lat, lon)
    if not len(pts):
        return out.reshape(shape)
    f = relief._Facts(profiles).at(s)
    dd = d - f["ctr"]
    ad = np.abs(dd)
    hw = f["hw"]
    M = mats
    here = out[pts]
    keep = np.isin(here, [M[k] for k in ("ASPHALT", "COBBLE", "SNOW") if k in M]) | (f["rough"] < 0.5)
    corridor = (ad <= hw + CORRIDOR_M) & ~keep
    if not corridor.any():
        return out.reshape(shape)
    sel = np.flatnonzero(corridor)
    pts, dd, ad, hw, here = pts[sel], dd[sel], ad[sel], hw[sel], here[sel]
    f = {k: v[sel] for k, v in f.items()}
    waters = [w for p in profiles.values() for w in (p.get("waters") or ())]
    dist = water_distances(waters, lat[pts], lon[pts])
    # (terrain 14: ragged boundaries, NATURAL_TV; zeros before)
    th, jit = _natural(lat[pts], lon[pts], getattr(course, "tv", 1) >= NATURAL_TV)
    arid = f["arid"] + th(1) >= ARID
    track = ad <= hw + 0.3 + jit(2, "track")
    rock = here == M.get("ROCK", -1)
    new = here.copy()
    # the track itself: packed or loose by the country it crosses
    desert = track & arid
    new[desert] = np.where(ad[desert] <= hw[desert] * (PACKED_SHARE + jit(3, "packed")[desert]), M["DUSTY"],
                           M["LOOSE"])
    new[track & ~arid] = M["DIRT"]
    new[track & (f["rock"] + th(4) >= ROCKY)] = M["GRAVEL"]
    road = track & (f["road"] + th(5) >= 0.5)
    new[road] = np.where(arid[road] & (ad[road] > hw[road] - EDGE_IN_M), M["LOOSE"], M["DIRT"])
    new[track & (f["lake"] + th(6) >= 0.5)] = M["DIRT"]            # a dry lake bed: packed hard
    # loose dirt pushed to the outside of the desert's turns
    outside = np.where(f["turn"] > 0, dd < 0, dd > 0) & (np.abs(f["turn"]) >= TURN_DEG)
    berm = arid & outside & (ad > hw - EDGE_IN_M) & (ad <= hw + EDGE_OUT_M + jit(7, "berm")) & ~rock
    new[berm] = M["LOOSE"]
    # the natural ground (on the track and beside it)
    canyon = arid & (f["canyon"] + th(8) >= CANYON_SAND) & (ad <= hw + CANYON_REACH_M + jit(9, "canyon")) & \
        (f["lake"] < 0.5) & ~rock
    new[canyon] = M["SAND"]
    wash = (dist["wash"] <= WASH_MARGIN_M + jit(10, "wash")) & ~rock
    new[wash] = np.where(arid[wash], M["SAND"], M["GRAVEL"])
    beach = (dist["sea"] <= BEACH_M + jit(11, "beach")) & ~rock
    new[beach] = M["SAND"]
    bank = ((dist["bank"] <= BANK_M + jit(12, "bank")) | (f["wetl"] + th(13) >= WETLAND)) & ~rock
    new[bank] = M["MUD"]
    if getattr(course, "tv", 1) >= VARIETY_TV:
        new = _variety(new, M, course, ad, hw, f, s[sel] if np.ndim(s) else s, rock, jit(14, "variety"))
    if getattr(course, "tv", 1) >= COVER_TV:
        new = _cover(new, here, M, track, arid, ad, hw, f, s[sel] if np.ndim(s) else s, rock)
    out[pts] = new
    return out.reshape(shape)


def _natural(lat, lon, on):
    """(th(salt), jit(salt, kind)): per point, a threshold's shift (DITHER) and a distance's (JITTER[kind]), each its own
    noise of the place; zeros when not on (before NATURAL_TV). Pure."""
    n = len(lat)
    if not on or not n:
        z = np.zeros(n)
        return (lambda salt: z), (lambda salt, kind: z)
    from . import relief
    gx, gy = relief.global_xy(lat, lon)

    def th(salt):
        return (relief.fbm(gx / DITHER_M, gy / DITHER_M, 900 + salt, 2) - 0.5) * DITHER_A * 2.0

    def jit(salt, kind):
        return (relief.fbm(gx / JITTER_M, gy / JITTER_M, 950 + salt, 2) - 0.5) * JITTER[kind] * 2.0
    return th, jit


def _variety(new, M, course, ad, hw, f, s, rock, jitter=0.0):
    """Terrain 7's sections (variety.py) on the ground: a sand trap's sand over the track and past its edges, a rock
    section's rock over the track with loose gravel at its edges, gravel over the track, a crawl's rock; never on mud or
    BeamNG.Earth's own steep rock (it stays). Pure."""
    from . import variety
    s = np.broadcast_to(np.asarray(s, np.float64), np.shape(ad))
    ws, wr, wg = variety.weights(course, s, f)
    auto = getattr(course, "rough", "on") == "auto"
    wc = variety.crawl_weight(course, s, f) if auto else np.zeros(len(s))
    free = (new != M["MUD"]) & ~rock
    on = variety.BARE_W
    j = jitter
    g = free & (wg * (1 - wc) >= on) & (ad <= hw + variety.GRAVEL_REACH_M + j)
    new[g] = M["GRAVEL"]
    r = free & (wr * (1 - wc) >= on)
    new[r & (ad <= hw + variety.ROCK_EDGE_M + j)] = M["GRAVEL"]
    new[r & (ad <= hw + 0.5 * j)] = M["ROCK"]
    sd = free & (ws * (1 - wc) >= on) & (ad <= hw + variety.SAND_REACH_M + j)
    new[sd] = M["SAND"]
    c = free & (wc >= on) & (ad <= hw + variety.CRAWL_REACH_M + j)
    new[c] = M["ROCK"]
    return new


def _lanes(s):
    """Per sample distance s (m): 1 where the stretch keeps a grassy middle (hashed from its index along the course:
    the same for everyone), else 0. Pure."""
    b = np.floor(np.asarray(s, np.float64) / LANES_M).astype(np.int64)
    with np.errstate(over="ignore"):
        x = (b.astype(np.uint64) * np.uint64(0x9E3779B97F4A7C15)) ^ np.uint64(0xC2B2AE3D27D4EB4F)
        x ^= x >> np.uint64(31)
        x *= np.uint64(0xBF58476D1CE4E5B9)
        x ^= x >> np.uint64(29)
    return ((x >> np.uint64(11)).astype(np.float64) / float(1 << 53)) < LANES_P


def _cover(new, here, M, track, arid, ad, hw, f, s, rock):
    """Terrain 4's plants on the track (COVER_TV's note): none of the covered layers on a track through bare land; where
    the land beside is covered, its layer on the middle strip (stretches that keep one) and over the edges, the wheel
    paths bare. Pure."""
    covered = {M[k] for k in ("GRASS", "LAWN", "DUSTY") if k in M}
    # the track never takes a covered layer of its own (terrain 3's packed desert middle was DUSTY)
    own = track & np.isin(new, list(covered))
    new[own] = M["DIRT"]
    plants = track & (f["cover"] >= COVER) & ~rock & (f["road"] < 0.5) & np.isin(new, [M["DIRT"], M["LOOSE"]])
    if not plants.any():
        return new
    green = f["grass"] >= 0.5 * np.maximum(f["cover"], 1e-9)
    layer = np.where(green, M.get("LAWN", M["GRASS"]), M["DUSTY"])
    middle = plants & (ad <= MIDDLE_M) & (hw >= MIDDLE_FROM_HW) & _lanes(s)
    edge = plants & (ad >= hw - EDGE_COVER_M)
    new[middle | edge] = layer[middle | edge]
    return new
