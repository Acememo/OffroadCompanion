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

# (terrain 16; the user, 2026-11-12, screenshots of a low deck right over the track with no dip, one beside it along
# the track: "Bridge doesn't have the dip to clear"). Terrain 13-15 dug only where a bridge's line crosses the course at
# 20 degrees or more, and not where the course was within 4 m of any paved road (every town street). From terrain 16
# every stretch of the course a deck reaches over (its line within its half width + DECK_NEAR_M of the course line,
# crossing it or running beside it: bridge_near) gets a floor UNDER_CLEAR_M under the girders, the whole stretch and
# DECK16_PAD_M past it, unless the course is on a paved road there itself (its crisp flag "pv": BeamNG.Earth lifts its
# decks over roads).
DECK_TV = 16
DECK_NEAR_M = 8.0           # (the deck's parapet 1 m + a wide track's half width 5 m + 2 m)
DECK_STEP_M = 2.0
DECK16_PAD_M = 6.0

# (terrain 17; the user, 2026-11-13, screenshots of a short bridge the course went under turned into a block of ground
# across its dip, and of tall spikes and sheets beside the roads at a hairpin by an overpass: "the bridge should be on
# top and dirt road below", "the spiky section is worse"). From terrain 17:
#   - a bridge the course goes under is kept (corridor.bridges_to_flatten keep_under), only one too low over the paved
#     road the course is on made a ground road, and its id says so in every window (earthpatch.bridge_crossings);
#   - the dips and ramps are worked out per piece of the track's middle line, never from the course sample nearest a
#     point: each piece of a dip or ramp (every PROBE15_M along it) stands its design surface (the floor, the ramp's
#     line) across the track with SIDE17 slopes either side curving steeper outward, and the ground is cut to the
#     lowest of them and filled to the highest (ramps only), each piece's weight its own; terrain 15 and 16 took a
#     point's distance along the course from relief.nearest, which jumps from one leg of a hairpin to the other, and
#     each jump stood a wall the dip's depth high (the spikes and sheets);
#   - near the paved roads a change is held to PAVED17_SLOPE per m from the asphalt's edge (in place of a fade over
#     ASPHALT_FADE_M: a dip of metres beside a road stood a wall at the road's edge).
KEEP_DECK_TV = 17
SIDE17 = 0.33               # the slopes' rise per m at the flat's edge ...
CURVE17 = 0.015             # ... + this per m squared (they meet any hillside short of ~1:1 within ~50 m)
REACH17_M = (45.0, 15.0)    # past the track's edge: full this far, none this much further (a cliff's foot)
PAVED17_SLOPE = 1.0
CHUNK17 = 4096

# (terrain 18; the user, 2026-11-13, screenshots of 1.7.20: "The bridges work great but it seriously affected
# negativity on other parts": pits metres deep where the course crosses a road at a bridge's end or passes a bridge's
# abutment in a parking lot, the parking aisles left standing as causeways between them, and torn piles where the
# course crosses a road in a cutting). From terrain 18:
#   - a deck stretch is dug under only where the deck stands DECK18_OVER_M or more over the track's ground (its height
#     reckoned from its ends' road heights climbing at corridor.DECK_MAX_GRADE): the course passing under it. Beside or
#     across a bridge's end the course meets the deck at its own height: nothing to dig under (deck18);
#   - such a bridge the course crosses is made a ground road again (corridor.bridges_to_flatten keep_from_m);
#   - the ramps off the paved roads cut right up to the asphalt again (terrain 13-16's ASPHALT_IN_M, ASPHALT_FADE_M):
#     terrain 17's 1:1 from the asphalt's edge left the road's cut bank standing where the track meets the road, the
#     steep entrance again (and the track drawn over it a torn pile); only the dips keep that 1:1, from DIP18_HOLD_IN_M
#     past the asphalt (its kerb and sidewalk).
AT_GRADE_TV = 18
DECK18_OVER_M = 2.5
DIP18_HOLD_IN_M = 2.0

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


def bridge_near(roadsmod, f, specs, course, k):
    """The stretches of window k's context the bridges of road features f reach over: [{s0, s1 (m along the course),
    a, b (the part's ends, lon / lat), hw, len, id, i}], each a run of the course (every DECK_STEP_M) whose line passes
    within the part's half width + DECK_NEAR_M of the deck's line. Pure."""
    c0, c1 = course.context(k)
    lat = np.asarray(course.lat[c0:c1 + 1], np.float64)
    lon = np.asarray(course.lon[c0:c1 + 1], np.float64)
    if len(lat) < 2 or f is None or not len(f):
        return []
    from .corridor import Plane, _seg_dist
    pl = Plane(float(lat.mean()), float(lon.mean()))
    cxy = pl.xy(np.stack([lon, lat], 1))
    seg = np.hypot(*np.diff(cxy, axis=0).T)
    cum = np.r_[0.0, np.cumsum(seg)]
    sl = np.arange(0.0, cum[-1] + 1e-9, DECK_STEP_M)
    px = np.interp(sl, cum, cxy[:, 0])
    py = np.interp(sl, cum, cxy[:, 1])
    pts = np.stack([px, py], 1)
    s_at = c0 * courseroads.STEP_M + np.interp(sl, cum, np.arange(len(cum)) * courseroads.STEP_M)
    cls = f.attrs.get("class")
    out = []
    for i in range(len(f)):
        if cls is not None and str(cls[i]) in FOOT_CLASSES:
            continue
        sp = specs[i] if specs is not None and i < len(specs) else None
        if sp is None or not any(kk == "bridge" for _, _, kk in roadsmod.level_ranges(f, i)):
            continue
        for p in roadsmod.bridge_parts(f, i) or ():
            ll = np.asarray(p, np.float64)[:, :2]
            if len(ll) < 2:
                continue
            q = pl.xy(ll)
            lo_, hi_ = q.min(axis=0) - 60.0, q.max(axis=0) + 60.0
            if not ((pts >= lo_) & (pts <= hi_)).all(axis=1).any():
                continue
            hw = float(sp.width) / 2.0
            d = _seg_dist(pts, q[:-1], q[1:]).min(axis=1)
            hit = d <= hw + DECK_NEAR_M
            if not hit.any():
                continue
            idx = np.flatnonzero(hit)
            runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
            for r in runs:
                out.append({"s0": round(float(s_at[r[0]]), 1), "s1": round(float(s_at[r[-1]]), 1),
                            "a": [round(float(ll[0, 0]), 7), round(float(ll[0, 1]), 7)],
                            "b": [round(float(ll[-1, 0]), 7), round(float(ll[-1, 1]), 7)],
                            "hw": round(hw, 2), "len": round(float(np.hypot(*np.diff(q, axis=0).T).sum()), 1),
                            "id": str(f.ids[i]), "i": i})
    return merge_near([out])


def merge_near(lists):
    """One list of the deck stretches found in several cells (and windows): one per bridge and place (the longest part
    seen), in order along the course. Pure."""
    best = {}
    for x in (y for lst in lists for y in lst):
        key = (x["id"], int(round(x["s0"] / 10.0)))
        if key not in best or x["len"] > best[key]["len"] or \
                (x["len"] == best[key]["len"] and x["s1"] - x["s0"] > best[key]["s1"] - best[key]["s0"]):
            best[key] = x
    return sorted(best.values(), key=lambda x: (x["s0"], x["id"]))


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
    surface) up to a window's context past it, so it is given those too (needed_windows). From terrain 17 two each
    way: the dips and ramps the next windows list are read too, and their facts reach a window past them."""
    ks = set(ks)
    r = 2 if getattr(course, "tv", 1) >= KEEP_DECK_TV else 1
    return sorted({j for k in ks for j in range(k - r, k + r + 1) if 0 <= j < getattr(course, "nwin", 0)} - ks)


def shape(course, profiles, lat, lon, graded, grade_fn, elev_fn, near=None, cleared=True, cache=None, around=None,
          parts=False):
    """Metres to add to graded (BeamNG.Earth's heights at the points, any shape) for the dips under bridges and the
    ramps off paved roads (terrain FROM_TV on; zeros before). profiles: the relief windows near the points (near:
    relief.nearest's answer with them); around: the windows next to them (neighbours()), whose facts the dips and
    ramps listed in profiles read too: without them those facts would be the nearest window end's, and a point's
    height would depend on which windows were at hand (1.7.14: ground tiles that disagreed with the physics block, the
    user 2026-11-12: "it appears as if the new fixes are non collidable"). cleared: the course is cleared (its bridges
    made crossings at grade have no deck: no dip). cache: a dict kept between calls (the heights read from the
    grading). parts (terrain 18 on): (the dips' change, the ramps' cut, the ramps' fill) each, for the caller to hold
    off the paved roads each its own way (their sum: min of the first two + the third). Pure given the functions (and
    a cache filled by them)."""
    shp = np.shape(graded)
    out = np.zeros(int(np.prod(shp)) if shp else 1)
    if getattr(course, "tv", 1) < FROM_TV:
        return out.reshape(shp)
    profiles = {k: p for k, p in profiles.items() if p}
    if not profiles or not len(out):
        return out.reshape(shp)
    if getattr(course, "tv", 1) >= KEEP_DECK_TV:
        dc, jc, ja = _shape17(course, profiles, around or {}, lat, lon, grade_fn, elev_fn, cleared,
                              cache if cache is not None else {})
        if parts and getattr(course, "tv", 1) >= AT_GRADE_TV:
            return dc.reshape(shp), jc.reshape(shp), ja.reshape(shp)
        out[:] = np.minimum(dc, jc) + ja
        return out.reshape(shp)
    xs, js, ds = {}, {}, {}
    for p in profiles.values():
        for x in (p.get("ud") or ()) if getattr(course, "tv", 1) >= DECK_TV else ():
            if cleared and x.get("f"):
                continue
            ds[(x["id"], int(round(x["s0"] / 10.0)))] = x
        for x in p.get("ux") or ():
            if cleared and x.get("f"):
                continue
            xs[(x["id"], int(round(x["s"] / 5.0)))] = x
        for jn in p.get("jn") or ():
            js[(int(jn[0]), int(jn[1]))] = jn
    if not xs and not js and not ds:
        return out.reshape(shp)
    lat = np.asarray(lat, np.float64).ravel()
    lon = np.asarray(lon, np.float64).ravel()
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
        own = _OwnGround(lat[idx], lon[idx], grade_fn, elev_fn)
        if getattr(course, "tv", 1) >= DECK_TV:
            xs = {}                             # (terrain 16: the decks' stretches in their place)
        out[idx] = _earthworks(course, facts, xs, js, s, ad, hw, own, grade_fn, elev_fn, cache, cid, ds)
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
    own = _OwnGround(lat[idx], lon[idx], grade_fn, elev_fn)
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
        corr = a * (h - own.at(m)) + (1.0 - a) * (h - gc)
        fade = JOIN_SIDE_FADE[0] + JOIN_SIDE_FADE[1] * np.abs(corr)
        w = 1.0 - _smooth((ad[m] - hw[m] - JOIN_SIDE_FLAT_M) / fade)
        dz[m] += corr * w
    out[idx] = dz
    return out.reshape(shp)


def _ease(t):
    return _smooth(np.asarray(t, np.float64))


class _OwnGround:
    """The points' heights as the probes along the course have them (grade_fn on elev_fn's ground), read only where a
    dip or a ramp reaches. Every shape is worked out against these, never against the heights the caller passed:
    those are the caller's own ground (the physics block's DEM, a far ground tile's coarser one, BeamNG.Earth's
    roughening of the land), metres from the probes' in hills, so a target height from the probes set against them
    stood spikes and pits in some grounds and not in others (1.7.17, the user 2026-11-12: a row of tall spikes beside
    the road). The change worked out here (dz) is the same whoever asks, and is added to the caller's own."""

    def __init__(self, lat, lon, grade_fn, elev_fn):
        self.lat, self.lon = np.asarray(lat, np.float64), np.asarray(lon, np.float64)
        self.v = np.full(len(self.lat), np.nan)
        self.grade_fn, self.elev_fn = grade_fn, elev_fn

    def at(self, m):
        need = np.zeros(len(self.v), bool)
        need[m] = True
        need &= np.isnan(self.v)
        if need.any():
            la, lo = self.lat[need], self.lon[need]
            nat = np.asarray(self.elev_fn(la, lo), np.float64).ravel()
            self.v[need] = np.asarray(self.grade_fn(la, lo, nat), np.float64).ravel()
        return self.v[m]


def deck_dip(course, facts, x, grade_fn, elev_fn):
    """Terrain 16's dip for deck stretch x: (floor height zT, depth at most, its ramp (m), probes s, their graded
    heights) or None (deep enough already, or the course on a paved road all along it). Pure given the functions."""
    end = (len(course.lat) - 1) * courseroads.STEP_M
    f0, f1 = x["s0"] - DECK16_PAD_M, x["s1"] + DECK16_PAD_M
    sf = np.arange(max(0.0, f0), min(end, f1) + 1e-9, PROBE15_M)
    if not len(sf):
        return None
    pv = facts.at(sf)["pv"]
    if np.all(pv >= 0.5):
        return None
    ends = np.asarray([x["a"], x["b"]], np.float64)
    nat = np.asarray(elev_fn(ends[:, 1], ends[:, 0]), np.float64)
    z_ends = np.asarray(grade_fn(ends[:, 1], ends[:, 0], nat), np.float64).ravel()
    zT = float(z_ends.min()) - DECK_UNDER_M - UNDER_CLEAR_M
    gf = _graded(course, facts, sf, grade_fn, elev_fn)
    depth = min(DIP_MAX_M, float(np.max(gf - zT)))
    if depth < DIP_MIN_M:
        return None
    ramp = max(DIP_RAMP_MIN_M, 1.5 * depth / DIP_GRADE)
    sp = np.arange(max(0.0, f0 - ramp), min(end, f1 + ramp) + 1e-9, PROBE15_M)
    gc = _graded(course, facts, sp, grade_fn, elev_fn)
    return zT, depth, ramp, sp, gc


def _earthworks(course, facts, xs, js, s, ad, hw, own, grade_fn, elev_fn, cache, cid, ds=None):
    """Terrain 15's dips and ramps at the points (s along the course, ad from the track's middle, hw its half width
    there, g their graded heights): a design surface along the track, flat FLAT15 past its edges, sloping SIDE15 out,
    the ground cut down to it (a dip: never filled) or cut and filled to it (a ramp), easing in and out along the
    course; own: the points' heights as the probes have them (_OwnGround). Pure given the functions (and the cache
    they fill)."""
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
        gm = own.at(m)
        cut = np.minimum(gm, H + SIDE15 * xl) - gm              # (<= 0: only ever down)
        e = np.clip(u / 0.5, 0.0, 1.0)                           # (none where the dip has eased out)
        dz[m] = np.minimum(dz[m], e * cut)
    # (terrain 16) under and beside the decks: the floor zT all along the stretch the deck reaches over and past it
    for key in sorted(ds or {}):
        x = ds[key]
        ck = (cid, "d16", key)
        if ck not in cache:
            cache[ck] = deck_dip(course, facts, x, grade_fn, elev_fn)
        r = cache[ck]
        if r is None:
            continue
        zT, depth, ramp, sp, gc = r
        f0, f1 = x["s0"] - DECK16_PAD_M, x["s1"] + DECK16_PAD_M
        m = (s >= f0 - ramp) & (s <= f1 + ramp)
        if not m.any():
            continue
        sm = s[m]
        out_d = np.maximum(0.0, np.maximum(f0 - sm, sm - f1))
        g_edge = np.interp(np.clip(sm, f0, f1), sp, gc)
        u = np.clip(g_edge - zT, 0.0, DIP_MAX_M) * (1.0 - _ease(out_d / ramp))
        H = np.interp(sm, sp, gc) - u
        xl = np.maximum(0.0, ad[m] - hw[m] - FLAT15_DIP_M)
        gm = own.at(m)
        cut = np.minimum(gm, H + SIDE15 * xl) - gm
        e = np.clip(u / 0.5, 0.0, 1.0)
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
        gm = own.at(m)
        target = np.clip(gm, H - SIDE15 * xl, H + SIDE15 * xl)
        # (easing in from the road's edge, out where the ramp has met the ground)
        e = _ease((tm - (t0 - 4.0)) / 4.0) * (1.0 - _ease((tm - (t0 + 0.75 * L)) / (0.25 * L)))
        dz[m] += e * (target - gm)
    return dz


# -- terrain 17 -----------------------------------------------------------------------------------------------------
def decks17(lists):
    """One deck stretch per bridge and run of the course: the stretches of the same bridge that overlap (one window's
    cut short by its context's end, another's whole) as one over all of them, its ends (a, b) the longest part's.
    Pure."""
    by = {}
    for x in sorted((y for lst in lists for y in lst), key=lambda y: (y["id"], y["s0"], y["s1"], -y["len"])):
        by.setdefault(x["id"], []).append(x)
    out = []
    for bid in sorted(by):
        run = None
        for x in by[bid]:
            if run is not None and x["s0"] <= run["s1"] + DECK_STEP_M:
                run["s1"] = max(run["s1"], x["s1"])
                run["f"] = max(run["f"], int(x.get("f", 0)))
                if x["len"] > run["len"]:
                    run.update(a=x["a"], b=x["b"], hw=x["hw"], len=x["len"])
                continue
            run = {"id": bid, "s0": x["s0"], "s1": x["s1"], "a": x["a"], "b": x["b"], "hw": x["hw"],
                   "len": x["len"], "f": int(x.get("f", 0))}
            out.append(run)
    return sorted(out, key=lambda x: (x["s0"], x["id"]))


def _line17(course, facts, sp):
    """The track's middle line at sp (m along the course): lat, lon, half widths, paved (0..1)."""
    f = facts.at(sp)
    la, lo = course_at(course, sp, f["ctr"])
    return la, lo, f["hw"], f["pv"]


def deck17(course, facts, x, grade_fn, elev_fn):
    """Terrain 17's dip under deck stretch x along its line: (lat, lon, hw, H (the design surface), w (its weight))
    every PROBE15_M, or None. Pure given the functions."""
    r = deck_dip(course, facts, x, grade_fn, elev_fn)
    if r is None:
        return None
    zT, depth, ramp, sp, gc = r
    f0, f1 = x["s0"] - DECK16_PAD_M, x["s1"] + DECK16_PAD_M
    out_d = np.maximum(0.0, np.maximum(f0 - sp, sp - f1))
    g_edge = np.interp(np.clip(sp, f0, f1), sp, gc)
    u = np.clip(g_edge - zT, 0.0, DIP_MAX_M) * (1.0 - _ease(out_d / ramp))
    la, lo, hw, pv = _line17(course, facts, sp)
    # (none where the dip has eased out, nor on a paved road: BeamNG.Earth lifts its decks over those)
    w = np.clip(u / 0.5, 0.0, 1.0) * (1.0 - _ease(pv))
    return la, lo, hw, gc - u, w, FLAT15_DIP_M


def deck18(course, facts, x, grade_fn, elev_fn):
    """Terrain 18's dip under deck stretch x: deck17's over the part of it where the deck stands DECK18_OVER_M or more
    over the track's ground (off the paved roads), or None (nowhere: the course meets the deck at its own height, by a
    bridge's end, or beside it). The deck's height: its ends' road heights climbing at corridor.DECK_MAX_GRADE, the
    lower. Pure given the functions."""
    from .corridor import DECK_MAX_GRADE, Plane
    end = (len(course.lat) - 1) * courseroads.STEP_M
    sf = np.arange(max(0.0, x["s0"]), min(end, x["s1"]) + 1e-9, PROBE15_M)
    if not len(sf):
        return None
    f = facts.at(sf)
    la, lo = course_at(course, sf, f["ctr"])
    nat = np.asarray(elev_fn(la, lo), np.float64)
    gf = np.asarray(grade_fn(la, lo, nat), np.float64).ravel()
    ends = np.asarray([x["a"], x["b"]], np.float64)
    zn = np.asarray(elev_fn(ends[:, 1], ends[:, 0]), np.float64)
    za, zb = (float(v) for v in np.asarray(grade_fn(ends[:, 1], ends[:, 0], zn), np.float64).ravel())
    pl = Plane(float(ends[0, 1]), float(ends[0, 0]))
    a, b = pl.xy(ends[:1])[0], pl.xy(ends[1:])[0]
    v = b - a
    L2 = max(float(v @ v), 1e-9)
    p = pl.xy(np.stack([lo, la], 1))
    t = np.clip(((p - a) @ v) / L2, 0.0, 1.0)
    length = max(float(x["len"]), math.sqrt(L2))
    deck = np.minimum(za + DECK_MAX_GRADE * t * length, zb + DECK_MAX_GRADE * (1.0 - t) * length)
    over = (deck - gf >= DECK18_OVER_M) & (f["pv"] < 0.5)
    if not over.any():
        return None
    return deck17(course, facts, dict(x, s0=float(sf[over].min()), s1=float(sf[over].max())), grade_fn, elev_fn)


def join17(course, facts, jn, grade_fn, elev_fn):
    """Terrain 17's ramp off a paved road at join jn along its line, as deck17's, or None."""
    r = join_ramp(course, facts, jn, grade_fn, elev_fn, JOIN15_GRADE)
    if r is None:
        return None
    t0, L, z0, z1 = r["t0"], r["L"], r["z0"], r["z1"]
    t = np.arange(t0 - 4.0, t0 + L + 1e-9, PROBE15_M)
    sp = jn[0] * courseroads.STEP_M + int(jn[1]) * t
    end = (len(course.lat) - 1) * courseroads.STEP_M
    ok = (sp >= 0) & (sp <= end)
    if ok.sum() < 2:
        return None
    t, sp = t[ok], sp[ok]
    H = z0 + (z1 - z0) * _ease((t - t0) / L)
    w = _ease((t - (t0 - 4.0)) / 4.0) * (1.0 - _ease((t - (t0 + 0.75 * L)) / (0.25 * L)))
    la, lo, hw, _ = _line17(course, facts, sp)
    return la, lo, hw, H, w, FLAT15_JOIN_M


def _side17(xl):
    return SIDE17 * xl + CURVE17 * xl * xl


def _works17(piece, lat, lon, own, fill):
    """One dip's or ramp's (piece: deck17's / join17's) cut (<= 0) and fill (>= 0, fill only) at the points: per piece
    of its line the design surface across it, cut and fill each weighted by the piece's weight, the deepest cut and
    the highest fill of the pieces. Continuous in the points (no nearest anything). Pure given own."""
    la, lo, hw, H, w, flat = piece
    n = len(lat)
    cut, add = np.zeros(n), np.zeros(n)
    if len(la) < 2 or not np.any(w > 0):
        return cut, add
    from .corridor import Plane
    pl = Plane(float(la[len(la) // 2]), float(lo[len(lo) // 2]))   # (the piece's own: the same whoever asks)
    q = pl.xy(np.stack([lo, la], 1))
    reach = float(np.max(hw)) + flat + REACH17_M[0] + REACH17_M[1]
    pxy = pl.xy(np.stack([lon, lat], 1))
    lo_, hi_ = q.min(axis=0) - reach, q.max(axis=0) + reach
    cand = np.flatnonzero(((pxy >= lo_) & (pxy <= hi_)).all(axis=1))
    if not len(cand):
        return cut, add
    a, b = q[:-1], q[1:]
    v = b - a
    L2 = np.maximum((v * v).sum(axis=1), 1e-12)
    for c0 in range(0, len(cand), CHUNK17):
        ci = cand[c0:c0 + CHUNK17]
        P = pxy[ci]
        rx, ry = P[:, None, 0] - a[None, :, 0], P[:, None, 1] - a[None, :, 1]
        tr = (rx * v[None, :, 0] + ry * v[None, :, 1]) / L2[None, :]
        t = np.clip(tr, 0.0, 1.0)
        Hk = H[:-1][None, :] + t * (H[1:] - H[:-1])[None, :]
        hk = hw[:-1][None, :] + t * (hw[1:] - hw[:-1])[None, :]
        wk = w[:-1][None, :] + t * (w[1:] - w[:-1])[None, :]
        # (from the piece's strip: the track and its flat beside this piece only; past its ends the surface slopes
        # away along the track as well as across it, so the track takes its own piece's height, never a lower one's
        # a few metres back, and round a bend the strips' corners meet without a ridge)
        ln = np.sqrt(L2)[None, :]
        perp = np.abs(rx * v[None, :, 1] - ry * v[None, :, 0]) / ln
        xl = np.hypot(np.maximum(0.0, perp - hk - flat), np.abs(tr - t) * ln)
        wk = wk * (1.0 - _ease((xl - REACH17_M[0]) / REACH17_M[1]))
        near = (wk > 0).any(axis=1)
        if not near.any():
            continue
        ci, Hk, xl, wk = ci[near], Hk[near], xl[near], wk[near]
        gp = own.at(ci)[:, None]
        sd = _side17(xl)
        cut[ci] = np.min(wk * np.minimum(0.0, Hk + sd - gp), axis=1)
        if fill:
            add[ci] = np.max(wk * np.maximum(0.0, Hk - sd - gp), axis=1)
    return cut, add


def _shape17(course, profiles, around, lat, lon, grade_fn, elev_fn, cleared, cache):
    """Terrain 17's dips and ramps at the points (shape()'s): the deck stretches and joins every window at hand lists
    (profiles and around), merged, each worked out along its own line (_works17). Pure given the functions (and the
    cache they fill)."""
    lat = np.asarray(lat, np.float64).ravel()
    lon = np.asarray(lon, np.float64).ravel()
    out = np.zeros(len(lat))
    every = dict(profiles)
    for k, p in around.items():
        if p:
            every.setdefault(k, p)
    decks = [x for x in decks17([p.get("ud") or () for p in every.values()]) if not (cleared and x["f"])]
    js = {}
    for p in every.values():
        for jn in p.get("jn") or ():
            js[(int(jn[0]), int(jn[1]))] = jn
    if not decks and not js:
        return out, out.copy(), out.copy()
    facts = relief._Facts(every)
    # (the track's look is in the key: BeamNG.Earth's grading of the track, which the shapes are worked out on, wears
    # it or not by it, and a shape kept from before the look changed was another ground's)
    cid = (getattr(course, "cid", ""), getattr(course, "rough", None))
    own = _OwnGround(lat, lon, grade_fn, elev_fn)
    dcut, cut, add = np.zeros(len(lat)), np.zeros(len(lat)), np.zeros(len(lat))
    v18 = getattr(course, "tv", 1) >= AT_GRADE_TV
    for x in decks:
        ck = (cid, "d18" if v18 else "d17", x["id"], x["s0"], x["s1"], tuple(x["a"]), tuple(x["b"]))
        if ck not in cache:
            cache[ck] = (deck18 if v18 else deck17)(course, facts, x, grade_fn, elev_fn)
        if cache[ck] is not None:
            c, _ = _works17(cache[ck], lat, lon, own, False)
            dcut = np.minimum(dcut, c)
    for key in sorted(js):
        ck = (cid, "j17", key)
        if ck not in cache:
            cache[ck] = join17(course, facts, js[key], grade_fn, elev_fn)
        if cache[ck] is not None:
            c, a = _works17(cache[ck], lat, lon, own, True)
            cut = np.minimum(cut, c)
            add = np.maximum(add, a)
    return dcut, cut, add
