"""The course's ground shaped for where it goes, terrain version 13 (the user, 2026-11-12):

  under a bridge   "when the dirt path passes below a bridge make ample room with a big depression that goes down and
                   up smoothly and leaves enough clearance for trophy trucks to pass under the bridge". BeamNG.Earth
                   lays a bridge's deck from its abutments and keeps it only DECK_CLEAR over the ground under it, so
                   where the course's own track runs under a low road bridge the deck nearly sat on the track. Here the
                   track's ground under a kept bridge is lowered to UNDER_CLEAR_M under the deck's girders (the deck
                   reckoned at its lower abutment's road height, which it never goes below): a flat floor under the
                   deck and DIP_FLOOR_PAD_M past it, eased banks no steeper than DIP_GRADE either way along the course,
                   and sloped sides across it (on a dirt road the course follows too). A bridge the course passes
                   under on a paved road is BeamNG.Earth's to clear (it lifts its decks over the roads beneath), and a
                   bridge the clear course makes a crossing at grade (corridor.bridges_to_flatten) has no deck.

  road entrances   "some parts of the road have dirt road entrances that are way too steep": where the course leaves or
                   joins a paved road that BeamNG.Earth cut into a hillside (or raised on a fill), its grading left the
                   course's ground at the natural height right to the road's cut bank, a step of metres. Here the track
                   ramps from the road's level to its own ground at JOIN_GRADE at most (the shortest such ramp, up to
                   JOIN_MAX_M), cutting a notch through the bank, its sides sloping back to the ground beside.

Where: the relief windows' profiles name the crossings (window "ux": the bridges, from BeamNG.Earth's map) and the
joins ("jn": the samples where the course comes off a paved road); every window lists those in its context too, so a
point's shape never depends on which windows were at hand. How deep or high: BeamNG.Earth's own grading (grade_fn) at
the bridge's ends and along the course, the same in every process. Pure numpy given the functions.
"""
import math

import numpy as np

from . import courseroads, relief

FROM_TV = 13

# under a bridge
DECK_UNDER_M = 2.2          # roadmesh.DECK_DEPTH (1.2) + GIRDER_D (1.0): the deck's underside under its road
UNDER_CLEAR_M = 5.0         # m from the track to the girders (a trophy truck is ~2.8 m, and it comes in bouncing)
DIP_MIN_M = 0.3             # shallower than this: left as it is
DIP_MAX_M = 8.0
DIP_GRADE = 0.10            # the banks down and up, steepest (a smoothstep's middle)
DIP_RAMP_MIN_M = 30.0
DIP_FLOOR_PAD_M = 5.0       # the floor past the deck's edge (+ its parapet, 1 m), each side
DIP_SIDE_FLAT_M = 2.5       # across: flat this far past the track's edge ...
DIP_SIDE_FADE = (6.0, 2.5)  # ... then back to the ground over this many m + this per m of depth
CROSS_MIN_DEG = 20.0        # a bridge crossed shallower than this runs along the course: none
FOOT_CLASSES = {"footway", "path", "cycleway", "steps", "pedestrian", "bridleway", "corridor"}

# road entrances
JOIN_GRADE = 0.12           # the ramp off a paved road, steepest
JOIN_STEEP = 0.25           # the ground already no steeper than this (rise per m over 2 m): left as it is
JOIN_LEVEL_M = 0.15         # the road's level: within this of its height at the join
JOIN_PROBE_M = 2.0
JOIN_MAX_M = 80.0
JOIN_MIN_M = 20.0
JOIN_SEARCH_M = 16.0        # the road's level is looked for this far out from the join sample
JOIN_SIDE_FLAT_M = 1.5
JOIN_SIDE_FADE = (5.0, 1.5)  # m + m per m of change
JOIN_NEAR_M = 4.0           # a sample this near a paved road (past its half width): on it
# (terrain 15; the user, 2026-11-12, a screenshot of a deep trench beside the road where the course left it: "the fix
# didn't fix the steepness correctly, it should not affect the road and needs to be smoother than a huge hole", and
# "the bridges are having enough clearance on the middle not on the edges"). From terrain 15 the dips and ramps are an
# earthwork's: a design surface along the track (the ramp's line, the dip's floor) flat across the track and FLAT15_M
# past its edges, then sloping back at SIDE15 (1:3) to wherever it meets the ground, the ground cut down to it or
# filled up to it there and nowhere else. Terrain 13 and 14 moved every point near the track by the change its own
# height asked for: beside a hillside that dug a pit, beside a road's cut bank a trench.
ENVELOPE_TV = 15
SIDE15 = 0.33               # rise per m of the slopes beside the design surface (1:3)
FLAT15_JOIN_M = 2.0         # the ramp's flat past the track's edges
FLAT15_DIP_M = 6.0          # the dip's floor past the track's edges (room beside the track under the whole deck)
DIP15_FLOOR_PAD_M = 8.0     # the floor past the deck's edge (+ its parapet), along the course, each side
JOIN15_GRADE = 0.10         # the ramp off a paved road, steepest
PROBE15_M = 2.0

ASPHALT_IN_M = 0.3          # never on a paved road's asphalt (relief.paved_clear with these: the shoulder is shaped)
ASPHALT_FADE_M = 1.0


def _smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


# -- what the windows list (planning) -------------------------------------------------------------------------------
def joins(course, k, near_paved):
    """Window k's joins: [[sample on the paved road, +1 / -1 the way off it along the course]] for every change between
    on a paved road (near_paved, per context sample: within its half width + JOIN_NEAR_M) and off it in the window's
    context. Pure."""
    c0, c1 = course.context(k)
    pv = [bool(v) for v in near_paved]
    out = []
    for i in range(len(pv) - 1):
        if pv[i] != pv[i + 1]:
            out.append([c0 + i, 1] if pv[i] else [c0 + i + 1, -1])
    return out


def bridge_crossings(roadsmod, f, specs, course, k):
    """The bridges of road features f (a map cell's; specs: roads.road_specs) crossing the course in window k's
    context: [{s (m along the course), sin (of the angle), a, b (the bridge part's ends, lon / lat), hw (its half width,
    m), len (m), id, i (feature index)}]. Pure."""
    c0, c1 = course.context(k)
    lat = np.asarray(course.lat[c0:c1 + 1], np.float64)
    lon = np.asarray(course.lon[c0:c1 + 1], np.float64)
    if len(lat) < 2 or f is None or not len(f):
        return []
    from .corridor import Plane, _cross
    pl = Plane(float(lat.mean()), float(lon.mean()))
    cxy = pl.xy(np.stack([lon, lat], 1))
    c1s, c2s = cxy[:-1], cxy[1:]
    cls = f.attrs.get("class")
    sin_min = math.sin(math.radians(CROSS_MIN_DEG))
    out = []
    for i in range(len(f)):
        if cls is not None and str(cls[i]) in FOOT_CLASSES:
            continue
        sp = specs[i] if specs is not None and i < len(specs) else None
        if sp is None:
            continue
        if not any(kk == "bridge" for _, _, kk in roadsmod.level_ranges(f, i)):
            continue
        for p in roadsmod.bridge_parts(f, i) or ():
            ll = np.asarray(p, np.float64)[:, :2]
            if len(ll) < 2:
                continue
            q = pl.xy(ll)
            X = _cross(c1s, c2s, q[:-1], q[1:])
            if not X.any():
                continue
            seg = np.hypot(*np.diff(q, axis=0).T)
            for ci, bj in np.argwhere(X):
                u = c2s[ci] - c1s[ci]
                v = q[bj + 1] - q[bj]
                cr = u[0] * v[1] - u[1] * v[0]
                sn = abs(cr) / max(1e-9, float(np.hypot(*u) * np.hypot(*v)))
                if sn < sin_min:
                    continue
                w = q[bj] - c1s[ci]
                t = (w[0] * v[1] - w[1] * v[0]) / cr if cr else 0.5
                out.append({"s": round((c0 + int(ci) + float(np.clip(t, 0, 1))) * courseroads.STEP_M, 1),
                            "sin": round(float(sn), 3),
                            "a": [round(float(ll[0, 0]), 7), round(float(ll[0, 1]), 7)],
                            "b": [round(float(ll[-1, 0]), 7), round(float(ll[-1, 1]), 7)],
                            "hw": round(float(sp.width) / 2.0, 2), "len": round(float(seg.sum()), 1),
                            "id": str(f.ids[i]), "i": i})
    return merge_crossings([out])           # (a bridge over a sample: the segments either side both cross it)


def merge_crossings(lists):
    """One list of the crossings found in several cells: one per bridge and place (the longest part seen: a bridge
    split by the cells' clipping), in order along the course. Pure."""
    best = {}
    for x in (y for lst in lists for y in lst):
        key = (x["id"], int(round(x["s"] / 5.0)))
        if key not in best or x["len"] > best[key]["len"]:
            best[key] = x
    return sorted(best.values(), key=lambda x: (x["s"], x["id"]))


# -- the shape at points --------------------------------------------------------------------------------------------
def course_at(course, s, off):
    """lat, lon of the points off m left of the course line at s m along it (each in its own sample's plane: the same
    whichever others are asked with it). Pure."""
    lat_all = np.asarray(course.lat, np.float64)
    lon_all = np.asarray(course.lon, np.float64)
    n = len(lat_all)
    step = courseroads.STEP_M
    s = np.clip(np.asarray(s, np.float64), 0.0, (n - 1) * step)
    i = np.minimum((s / step).astype(np.int64), max(0, n - 2))
    t = s / step - i
    j = np.minimum(i + 1, n - 1)
    lat0, lon0 = lat_all[i], lon_all[i]
    kx = np.radians(1.0) * courseroads.R_EARTH * np.cos(np.radians(lat0))
    ky = np.radians(1.0) * courseroads.R_EARTH
    dx, dy = (lon_all[j] - lon0) * kx, (lat_all[j] - lat0) * ky
    L = np.maximum(np.hypot(dx, dy), 1e-9)
    nx, ny = -dy / L, dx / L
    o = np.asarray(off, np.float64)
    return lat0 + (dy * t + ny * o) / ky, lon0 + (dx * t + nx * o) / kx


def _graded(course, facts, s, grade_fn, elev_fn):
    """BeamNG.Earth's graded heights in the track's middle at s."""
    f = facts.at(np.asarray(s, np.float64))
    la, lo = course_at(course, s, f["ctr"])
    nat = np.asarray(elev_fn(la, lo), np.float64)
    return np.asarray(grade_fn(la, lo, nat), np.float64).ravel()


def dip_depth(course, facts, x, grade_fn, elev_fn):
    """How far (m) the track's ground under crossing x goes down: to UNDER_CLEAR_M under the girders of a deck at its
    lower end's road height. 0: deep enough already, or the course on a paved road there. Pure given the functions."""
    f = facts.at(np.asarray([x["s"]], np.float64))
    if f["rough"][0] < 0.5:            # (on a paved road: BeamNG.Earth lifts its decks over those)
        return 0.0
    ends = np.asarray([x["a"], x["b"]], np.float64)
    nat = np.asarray(elev_fn(ends[:, 1], ends[:, 0]), np.float64)
    z_ends = np.asarray(grade_fn(ends[:, 1], ends[:, 0], nat), np.float64).ravel()
    z_p = float(_graded(course, facts, [x["s"]], grade_fn, elev_fn)[0])
    want = float(z_ends.min()) - DECK_UNDER_M - UNDER_CLEAR_M
    d = min(DIP_MAX_M, max(0.0, z_p - want))
    return round(d, 2) if d >= DIP_MIN_M else 0.0


def dip_along(x, depth, s):
    """The dip's depth at s m along the course (its middle's). Pure."""
    floor = (x["hw"] + 1.0 + DIP_FLOOR_PAD_M) / max(x["sin"], 0.34)
    ramp = max(DIP_RAMP_MIN_M, 1.5 * depth / DIP_GRADE)
    return depth * (1.0 - _smooth((np.abs(np.asarray(s, np.float64) - x["s"]) - floor) / ramp))


def dip_reach(x, depth):
    return (x["hw"] + 1.0 + DIP_FLOOR_PAD_M) / max(x["sin"], 0.34) + max(DIP_RAMP_MIN_M, 1.5 * depth / DIP_GRADE)


def join_ramp(course, facts, jn, grade_fn, elev_fn, grade=JOIN_GRADE):
    """A join's ramp: {t0, L, z0, z1, t, g}: from t0 m past the join sample (where the ground leaves the road's level)
    over L m, from the road's height z0 (a sample back, on the road) to the ground's z1 (t, g: the graded heights along
    the track's middle every JOIN_PROBE_M from a sample back); None when the ground there is no steeper than JOIN_STEEP. Pure given the
    functions."""
    i, sgn = int(jn[0]), int(jn[1])
    s0 = i * courseroads.STEP_M
    # (from the sample before, on the road: the join sample itself may be the track's end, bent out to the road's edge,
    # its middle beside the road; the track's middle runs from the road's middle there to its own)
    t = np.arange(-courseroads.STEP_M, JOIN_SEARCH_M + JOIN_MAX_M + 1e-9, JOIN_PROBE_M)
    s = s0 + sgn * t
    end = (len(course.lat) - 1) * courseroads.STEP_M
    ok = (s >= 0) & (s <= end)
    if ok.sum() < 4:
        return None
    t, s = t[ok], s[ok]
    g = _graded(course, facts, s, grade_fn, elev_fn)
    z0 = float(g[0])
    off = np.abs(g - z0) > JOIN_LEVEL_M
    if not off.any():
        return None
    first = int(np.argmax(off))
    if t[first] > JOIN_SEARCH_M:
        return None
    t0 = float(t[max(0, first - 1)])
    look = (t >= t0) & (t <= t0 + 40.0)
    steep = np.abs(np.diff(g[look])) / JOIN_PROBE_M if look.sum() > 1 else np.zeros(1)
    if float(steep.max()) <= JOIN_STEEP:
        return None
    best = None
    for L in np.arange(JOIN_MIN_M, JOIN_MAX_M + 1e-9, 10.0):
        m = np.flatnonzero(np.abs(t - (t0 + L)) < 1e-6)
        if not len(m):
            break
        best = {"t0": t0, "L": float(L), "z0": z0, "z1": float(g[m[0]]), "t": t, "g": g}
        if 1.5 * abs(best["z1"] - z0) / L <= grade:
            break
    return best


def neighbours(course, ks):
    """The windows next to windows ks not among them: shape() reads the course's facts (its track's middle, width,
    surface) up to a window's context past it, so it is given those too (needed_windows)."""
    ks = set(ks)
    return sorted({j for k in ks for j in (k - 1, k + 1) if 0 <= j < getattr(course, "nwin", 0)} - ks)


def shape(course, profiles, lat, lon, graded, grade_fn, elev_fn, near=None, cleared=True, cache=None, around=None):
    """Metres to add to graded (BeamNG.Earth's heights at the points, any shape) for the dips under bridges and the
    ramps off paved roads (terrain FROM_TV on; zeros before). profiles: the relief windows near the points (near:
    relief.nearest's answer with them); around: the windows next to them (neighbours()), whose facts the dips and
    ramps listed in profiles read too: without them those facts would be the nearest window end's, and a point's
    height would depend on which windows were at hand (1.7.14: ground tiles that disagreed with the physics block, the
    user 2026-11-12: "it appears as if the new fixes are non collidable"). cleared: the course is cleared (its bridges
    made crossings at grade have no deck: no dip). cache: a dict kept between calls (the heights read from the
    grading). Pure given the functions (and a cache filled by them)."""
    shp = np.shape(graded)
    out = np.zeros(int(np.prod(shp)) if shp else 1)
    if getattr(course, "tv", 1) < FROM_TV:
        return out.reshape(shp)
    profiles = {k: p for k, p in profiles.items() if p}
    if not profiles or not len(out):
        return out.reshape(shp)
    xs, js = {}, {}
    for p in profiles.values():
        for x in p.get("ux") or ():
            if cleared and x.get("f"):
                continue
            xs[(x["id"], int(round(x["s"] / 5.0)))] = x
        for jn in p.get("jn") or ():
            js[(int(jn[0]), int(jn[1]))] = jn
    if not xs and not js:
        return out.reshape(shp)
    lat = np.asarray(lat, np.float64).ravel()
    lon = np.asarray(lon, np.float64).ravel()
    g_all = np.asarray(graded, np.float64).ravel()
    idx, d, s = near if near is not None else relief.nearest(course, profiles, lat, lon)
    if not len(idx):
        return out.reshape(shp)
    every = dict(profiles)
    for k, p in (around or {}).items():
        if p:
            every.setdefault(k, p)
    facts = relief._Facts(every)
    f = facts.at(s)
    ad = np.abs(d - f["ctr"])
    hw = f["hw"]
    cache = cache if cache is not None else {}
    cid = getattr(course, "cid", "")
    if getattr(course, "tv", 1) >= ENVELOPE_TV:
        out[idx] = _earthworks(course, facts, xs, js, s, ad, hw, g_all[idx], grade_fn, elev_fn, cache, cid)
        return out.reshape(shp)
    dz = np.zeros(len(idx))
    # under the bridges
    for key in sorted(xs):
        x = xs[key]
        ck = (cid, "x", key)
        if ck not in cache:
            cache[ck] = dip_depth(course, facts, x, grade_fn, elev_fn)
        depth = cache[ck]
        if depth <= 0.0:
            continue
        m = np.abs(s - x["s"]) <= dip_reach(x, depth)
        if not m.any():
            continue
        u = dip_along(x, depth, s[m])
        fade = DIP_SIDE_FADE[0] + DIP_SIDE_FADE[1] * u
        w = 1.0 - _smooth((ad[m] - hw[m] - DIP_SIDE_FLAT_M) / fade)
        dz[m] = np.minimum(dz[m], -u * w)
    # off the paved roads
    g = g_all[idx]
    for key in sorted(js):
        jn = js[key]
        ck = (cid, "j", key)
        if ck not in cache:
            cache[ck] = join_ramp(course, facts, jn, grade_fn, elev_fn)
        r = cache[ck]
        if r is None:
            continue
        t0, L, z0, z1, sgn = r["t0"], r["L"], r["z0"], r["z1"], int(jn[1])
        t = (s - jn[0] * courseroads.STEP_M) * sgn
        m = (t >= t0) & (t <= t0 + L)
        if not m.any():
            continue
        tm = t[m]
        h = z0 + (z1 - z0) * _smooth((tm - t0) / L)
        gc = np.interp(tm, r["t"], r["g"])
        # (near the road the ground itself is set to the ramp: the cut bank goes, whichever way it runs across the
        # track; further on the track's own cross shape is moved to it, so it meets the ground where the ramp ends)
        a = 1.0 - _smooth((tm - t0 - 0.5 * L) / (0.3 * L))
        corr = a * (h - g[m]) + (1.0 - a) * (h - gc)
        fade = JOIN_SIDE_FADE[0] + JOIN_SIDE_FADE[1] * np.abs(corr)
        w = 1.0 - _smooth((ad[m] - hw[m] - JOIN_SIDE_FLAT_M) / fade)
        dz[m] += corr * w
    out[idx] = dz
    return out.reshape(shp)


def _ease(t):
    return _smooth(np.asarray(t, np.float64))


def _earthworks(course, facts, xs, js, s, ad, hw, g, grade_fn, elev_fn, cache, cid):
    """Terrain 15's dips and ramps at the points (s along the course, ad from the track's middle, hw its half width
    there, g their graded heights): a design surface along the track, flat FLAT15 past its edges, sloping SIDE15 out,
    the ground cut down to it (a dip: never filled) or cut and filled to it (a ramp), easing in and out along the
    course. Pure given the functions (and the cache they fill)."""
    dz = np.zeros(len(s))
    # under the bridges: the floor UNDER_CLEAR_M under the girders all the way under the deck and past it
    for key in sorted(xs):
        x = xs[key]
        ck = (cid, "x15", key)
        if ck not in cache:
            depth = dip_depth(course, facts, x, grade_fn, elev_fn)
            floor = (x["hw"] + 1.0 + DIP15_FLOOR_PAD_M) / max(x["sin"], 0.34)
            ramp = max(DIP_RAMP_MIN_M, 1.5 * depth / DIP_GRADE)
            sp = np.arange(-(floor + ramp), floor + ramp + 1e-9, PROBE15_M) + x["s"]
            end = (len(course.lat) - 1) * courseroads.STEP_M
            sp = sp[(sp >= 0) & (sp <= end)]
            gc = _graded(course, facts, sp, grade_fn, elev_fn) if depth > 0 and len(sp) else np.zeros(len(sp))
            cache[ck] = (depth, floor, ramp, sp, gc)
        depth, floor, ramp, sp, gc = cache[ck]
        if depth <= 0.0 or len(sp) < 2:
            continue
        m = np.abs(s - x["s"]) <= floor + ramp
        if not m.any():
            continue
        u = depth * (1.0 - _ease((np.abs(s[m] - x["s"]) - floor) / ramp))
        H = np.interp(s[m], sp, gc) - u
        xl = np.maximum(0.0, ad[m] - hw[m] - FLAT15_DIP_M)
        cut = np.minimum(g[m], H + SIDE15 * xl) - g[m]          # (<= 0: only ever down)
        e = np.clip(u / 0.5, 0.0, 1.0)                           # (none where the dip has eased out)
        dz[m] = np.minimum(dz[m], e * cut)
    # off the paved roads: the ramp's line from the road's level to the ground's
    for key in sorted(js):
        jn = js[key]
        ck = (cid, "j15", key)
        if ck not in cache:
            cache[ck] = join_ramp(course, facts, jn, grade_fn, elev_fn, JOIN15_GRADE)
        r = cache[ck]
        if r is None:
            continue
        t0, L, z0, z1 = r["t0"], r["L"], r["z0"], r["z1"]
        t = (s - jn[0] * courseroads.STEP_M) * int(jn[1])
        m = (t >= t0 - 4.0) & (t <= t0 + L)
        if not m.any():
            continue
        tm = t[m]
        H = z0 + (z1 - z0) * _ease((tm - t0) / L)
        xl = np.maximum(0.0, ad[m] - hw[m] - FLAT15_JOIN_M)
        target = np.clip(g[m], H - SIDE15 * xl, H + SIDE15 * xl)
        # (easing in from the road's edge, out where the ramp has met the ground)
        e = _ease((tm - (t0 - 4.0)) / 4.0) * (1.0 - _ease((tm - (t0 + 0.75 * L)) / (0.25 * L)))
        dz[m] += e * (target - g[m])
    return dz
