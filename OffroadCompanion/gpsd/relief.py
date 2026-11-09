"""Rough ground along the course's dirt track (the user, 2026-10-22: "some trails on the 30 m coverage are too flat and
boring to drive and incentivize just cutting parts of the road ... the roughness, maybe some rocks on the narrow
canyons, ... on salt lakes it's fine ... the seed from the global coordinates, so if I drive somewhere and a friend
on his computer drives there it is the same").

The elevation data is 30 m (Copernicus): a desert track on it is a smooth sheet, and BeamNG.Earth grades it smoother
still. Real desert race courses are not: whoop sections, washes crossing the course, kickers, sand piled on the
outside of the turns, broken ground, rock ledges in the canyons. This adds that relief to the ground's heights along
the course, where the course is on dirt (its own track, or a dirt / gravel road it follows; never on asphalt, and
fading out where it crosses a paved road), as metres added to BeamNG.Earth's graded heights (earthpatch.py hooks
grading.Grader.apply: the physics block, the road tiles' mesh and the near ground tiles all take their heights from
there, so the tyres, the dirt track and the drawn ground agree).

    whoops      rolling bumps across the track ~10.5 m apart (two waves: irregular), in whoop sections found by a
                noise over the ground (~35 % of a course), a little diagonal; smaller rollers everywhere
    washes      dips across the course and beyond it, and kickers (a ramp up, a short drop) every few hundred metres
    berms       sand piled on the outside of the turns, a low windrow along the edges, the track floor a little worn in
    broken      bumps of 4-9 m over the whole track, more in rocky places
    ledges      stepped rock in canyons and on hillsides (the ground rising on both sides / one side of the course)
    rocks       boulders beside the track in canyons and rocky hillsides (BeamNG.Earth's vegetation items: they collide
                near the car like its own rocks)
    playas      on a dry or salt lake (water mapped intermittent or salt) the relief is mostly left out

The player's setting scales it all (earthpatch.ROUGH: mild, rough, extra). "auto" (the user, 2026-10-22: "uses all the
variance from all the other roughness modes ... fast mild sections, rough sections and very rough all in the same
setting ... rough close to the danger markers and sometimes some rocks that fit the environment, the amount of rocks
also decided deterministically"), course_auto below:
    sections    a noise over the course's place on the Earth (AUTO_ZONE_M: sections of 1-3 km) picks fast (smoother
                than mild), mild, rough or extra for each stretch, blending over ~100 m
    hazards     the course file's DANGER waypoints: extra rough from DANGER_RAMP before them to after them, and at each
                one a hazard hashed from its place: a deep ditch, a big kicker or a rock garden
    rocks       boulder fields beside the track where a second noise says so (none on most of the course, a few or
                many elsewhere), more on rocky ground, none on lakes or asphalt; the rock model the one BeamNG.Earth
                already uses in that place (earthpatch: the cell's own rocks), so they fit in

Deterministic: every noise is a hash of the point's position on the Earth (its latitude / longitude in metres), every
feature along the course a hash of where the course is; the per-sample facts (track width, dirt or asphalt, canyon,
turn, lake) come from the course, the map and the elevation data, as the dirt track itself. The same course file in
the same place gives the same ground on every computer, whichever order the game asks for it in.

Pure numpy; nothing here reads files.
"""
import math

import numpy as np

from . import courseroads

ALGO = 4                    # bump when a profile's contents change (2: ctr; 3: dirt roads followed from further;
                            # 4: the track's ends bend onto the road they meet: their ctr)
STEP = courseroads.STEP_M
REACH_M = 52.0              # the farthest any relief reaches from the course line (a dirt road it follows 25 m off)
FADE_M = 4.0                # past the track's edge (+ EDGE_M) the track's relief fades out over this
EDGE_M = 0.6
WASH_PAST_M = 2.5           # washes run on past the track ...
WASH_FADE_M = 9.0           # ... fading over this
CLAMP = (-1.3, 1.1)         # m: the relief never goes past these

# whoops
WHOOP_L1, WHOOP_L2 = 10.5, 23.7     # m: the two waves
WHOOP_ZONE_M = 350.0                # whoop sections: a noise at this scale ...
WHOOP_ZONE = (0.48, 0.70)           # ... between these is whoop country
WHOOP_A = (0.16, 0.50)              # m: rollers everywhere .. a whoop section's full height
SKEW_M = 450.0
# washes and kickers
BIN_M = 170.0               # one chance of a wash or a kicker per BIN_M of course
P_FEATURE = 0.45
P_KICKER = 0.35
# (terrain 4; the user, 2026-10-28: "there are some dips that are too aggressive and appear too often, it's good to have
# once in a very long while but there are dips that shouldn't be too sudden on its dip, maybe elongate the low part so
# it isn't just like a hole and then a ramp"). Terrain 3's wash was a bell 4-8 m wide and up to 0.95 m deep, one per
# ~580 m. From terrain 4 a wash is a dry streambed: an eased bank down, a flat floor 6-18 m long, an eased bank up;
# mostly shallow (0.15-0.45 m), now and then (WASH_DEEP_P) a deep one (to 0.7 m), and about one per km. The DANGER
# waypoints' ditches get the same shape, deeper.
DIPS_TV = 4
P_WASH_V4 = 0.17            # a wash's chance per BIN_M (a kicker's stays P_FEATURE x P_KICKER)
WASH_DEPTH_V4 = (0.15, 0.45)
WASH_DEEP_P, WASH_DEEP_M = 0.12, 0.7
WASH_FLOOR_M = (6.0, 18.0)  # the flat floor's length
WASH_BANK_M = (7.0, 12.0)   # each eased bank's length
DITCH_FLOOR_M = (5.0, 10.0)
DITCH_BANK_M = (7.0, 9.0)


# (terrain 5; the user, 2026-10-29, a Baja 400 photo of a bowl corner: "smooth banking on the tight corners but only on
# rough terrain, and not on all rough terrain corners, make it so there is a higher chance the tighter the corner and the
# rougher it is ... to get that baja track feel") Banked corners: in a corner the track tilts into it, its outside a
# lip of pushed-up dirt easing back into the ground, its inside dug a little; chosen per stretch of BANK_BIN_M by a hash
# of the course's place against a chance that grows with the corner's tightness and the ground's roughness (none on
# Flat or Mild; on Rough about a third of the tightest corners, on Extra most), eased in and out with the corner itself, so a corner banks smoothly and everyone gets the same.
BANKS_TV = 5
VARIETY_TV = 7              # (variety.py: sand traps, rock sections, gravel, rock crawls; its own VARIETY_TV the same)
BANK_BIN_M = 150.0
BANK_TURN = (3.0, 14.0)     # deg per sample (10 m): a gentle bend (~190 m radius) .. a tight corner (~40 m)
BANK_ROUGH = (0.7, 1.4)     # the ground's roughness (relief's power): none up to Mild (0.55) .. Extra (1.6) over the top
BANK_P_MAX = 0.9
BANK_SOFT = 0.12            # the chance's edge, eased (no bank switching on or off at a hair's difference)
BANK_SLOPE = (0.10, 0.24)   # m per m across the track at full bank: a bend .. a tight corner (6 .. 13 degrees)
BANK_INSIDE = 0.45          # the inside dug this share of the outside's rise
BANK_LIP_M, BANK_IN_M = 3.5, 2.0    # past the outside edge the lip eases down over this; past the inside, back up
# (terrain 5, the same day, photos of rutted Baja tracks: "only on mild or rougher terrain there should be some sections
# with wheel terrain deformation ... make it more probable the tighter the road is") Rutted sections: the track's floor
# worn down between windrows of dirt the tyres threw to its edges, and chopped up unevenly. The physics ground is a 2 m
# grid, so the narrow grooves themselves are drawn (ruts.py: braided rut strips over these sections); the ground takes
# what a 2 m grid holds: the worn floor, the windrows and the chop. A global noise picks the sections (RUT_ZONE_M), more
# of them on narrower tracks and rougher ground, none on Flat, few on graded roads.
RUTS_TV = 5
RUT_ZONE_M = 420.0
RUT_THR = 0.70              # the noise over this: rutted (lowered by narrowness and roughness)
RUT_NARROW_HW = (4.5, 2.0)  # m half width: wide .. narrow
RUT_SINK, RUT_BERM, RUT_CHOP = 0.12, 0.16, 0.08     # m


def bank_weight(course, s, turn, power):
    """Per point (s along the course, turn deg per sample, the ground's roughness power): 0 .. 1, how fully its corner is
    banked (0 on straights, on Flat, and where the stretch's hash said no). Pure."""
    s = np.asarray(s, np.float64)
    tight = _ramp(np.abs(turn), *BANK_TURN)
    rough = _ramp(power, *BANK_ROUGH)
    p = BANK_P_MAX * tight * rough
    lat = getattr(course, "_np_lat", None)
    if lat is None:
        course._np_lat = lat = np.asarray(course.lat, np.float64)
        course._np_lon = np.asarray(course.lon, np.float64)
    lon = course._np_lon
    u = s / BANK_BIN_M - 0.5
    b0 = np.floor(u).astype(np.int64)
    t = _smooth(u - b0)

    def h(b):
        mid = np.clip(((b + 0.5) * BANK_BIN_M / STEP).astype(np.int64), 0, len(lat) - 1)
        return _hash(np.round(lat[mid] * 1e4).astype(np.int64), np.round(lon[mid] * 1e4).astype(np.int64), 31)
    # each stretch's own yes or no (eased at the chance's edge), blended from one stretch's middle to the next: a bank
    # comes and goes over a stretch, never in a few metres
    w = _smooth((p - h(b0)) / BANK_SOFT + 0.5) * (1 - t) + _smooth((p - h(b0 + 1)) / BANK_SOFT + 0.5) * t
    return w * (p > 0) * tight


def _sections(course, s, p, bin_m, salt, soft=BANK_SOFT):
    """0 .. 1 per point: whether its stretch (bin_m long) is in, against the chance p there (0 .. 1 per point), each
    stretch's own yes or no hashed from the course's place at its middle (salt), eased at the chance's edge and blended
    from one stretch's middle to the next: bank_weight's rule for any kind of section (terrain 7: variety.py). Pure."""
    s = np.asarray(s, np.float64)
    p = np.asarray(p, np.float64)
    lat = getattr(course, "_np_lat", None)
    if lat is None:
        course._np_lat = lat = np.asarray(course.lat, np.float64)
        course._np_lon = np.asarray(course.lon, np.float64)
    lon = course._np_lon
    u = s / bin_m - 0.5
    b0 = np.floor(u).astype(np.int64)
    t = _smooth(u - b0)

    def h(b):
        mid = np.clip(((b + 0.5) * bin_m / STEP).astype(np.int64), 0, len(lat) - 1)
        return _hash(np.round(lat[mid] * 1e4).astype(np.int64), np.round(lon[mid] * 1e4).astype(np.int64), salt)
    w = _smooth((p - h(b0)) / soft + 0.5) * (1 - t) + _smooth((p - h(b0 + 1)) / soft + 0.5) * t
    return w * (p > 0)


def bank_dz(x, hw, slope):
    """The banked corner's height at x (m toward the corner's outside from the track's middle): a slope across the track,
    a lip easing down past the outside edge, the inside dug a little and easing back up. Pure."""
    x = np.asarray(x, np.float64)
    out = np.where(x >= 0, slope * np.minimum(x, hw), BANK_INSIDE * slope * np.maximum(x, -hw))
    lip = slope * hw * (1.0 - _smooth((x - hw) / BANK_LIP_M))
    dig = -BANK_INSIDE * slope * hw * (1.0 - _smooth((-x - hw) / BANK_IN_M))
    return np.where(x > hw, lip, np.where(x < -hw, dig, out))


def rut_weight(gx, gy, hw, power, road):
    """0 .. 1 per point: how rutted the track is there (the sections: rut_weight's note on RUTS_TV). Pure."""
    gate = _ramp(power, 0.45, 0.55)
    narrow = _ramp(-np.asarray(hw, np.float64), -RUT_NARROW_HW[0], -RUT_NARROW_HW[1])
    thr = RUT_THR - 0.10 * narrow - 0.05 * _ramp(power, *BANK_ROUGH) + 0.08 * np.asarray(road, np.float64)
    z = fbm(np.asarray(gx) / RUT_ZONE_M, np.asarray(gy) / RUT_ZONE_M, 41, 2)
    return gate * _ramp(z, thr, thr + 0.04)


def dip(dd, depth, floor, bank):
    """A dip's height at dd (m from its middle): 0 outside, -depth on its flat floor (floor long), eased (a half cosine)
    over each bank (bank long). Pure."""
    a = np.abs(dd) - floor / 2.0
    t = np.clip(a / bank, 0.0, 1.0)
    return -depth * 0.5 * (1.0 + np.cos(np.pi * t))
# berms
WEAR_M = 0.09
EDGE_BERM_M = 0.13
TURN_BERM_M = 0.5           # the outside of a turn of TURN_FULL_DEG per sample or more
TURN_FULL_DEG = 6.0
# broken ground and rock
BUMP_M = (0.10, 0.18)       # m: plain .. rocky
LEDGE_M = 0.42
# rocks beside the track
ROCK_FROM = 0.35            # rockiness from which boulders stand beside the track
ROCK_P = 0.5                # chance per slot (two per sample and side) at full rockiness
# the per-sample facts
SIDE_OFFS = (8.0, 16.0, 28.0, 40.0)
CANYON_RISE = (3.0, 12.0)   # m: the lower side's rise over the track: none .. a canyon
HILL_RISE = (6.0, 20.0)     # m: the higher side's rise: none .. a rocky hillside
COVER_PAD_M = 5.0
COVER_DEG = 35.0
PAVED_NEAR_M = 4.0          # a paved road this near (past its half width): no relief here
DEFAULT_HALF_M = 2.5


# -- hashing and noise (global: the point's place on the Earth) ---------------------------------------------------------
def _hash(a, b, salt):
    """Uniform [0, 1) from two integer arrays and a salt (as BeamNG.Earth's vegetation hashes its scatter)."""
    a = np.asarray(a, np.int64).astype(np.uint64)
    b = np.asarray(b, np.int64).astype(np.uint64)
    with np.errstate(over="ignore"):
        x = a * np.uint64(0x9E3779B97F4A7C15) ^ (b + np.uint64(salt)) * np.uint64(0xC2B2AE3D27D4EB4F)
        x ^= x >> np.uint64(31)
        x *= np.uint64(0xBF58476D1CE4E5B9)
        x ^= x >> np.uint64(29)
    return (x >> np.uint64(11)).astype(np.float64) / float(1 << 53)


def global_xy(lat, lon):
    """Metres east / north on the Earth for the noises (a point's own; continuous)."""
    lat = np.asarray(lat, np.float64)
    lon = np.asarray(lon, np.float64)
    return lon * 111319.49 * np.cos(np.radians(lat)), lat * 110574.0


def vnoise(x, y, salt):
    """Value noise in [0, 1): random values on the unit lattice, smoothly interpolated."""
    ix, iy = np.floor(x), np.floor(y)
    fx, fy = x - ix, y - iy
    ix, iy = ix.astype(np.int64), iy.astype(np.int64)
    ux = fx * fx * fx * (fx * (fx * 6 - 15) + 10)
    uy = fy * fy * fy * (fy * (fy * 6 - 15) + 10)
    a = _hash(ix, iy, salt)
    b = _hash(ix + 1, iy, salt)
    c = _hash(ix, iy + 1, salt)
    d = _hash(ix + 1, iy + 1, salt)
    return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy


def fbm(x, y, salt, octaves=3):
    """Sum of value noises (each half the size and weight of the last), in [0, 1)."""
    out = np.zeros(np.shape(x))
    amp, tot, f = 1.0, 0.0, 1.0
    for o in range(octaves):
        out += amp * vnoise(x * f + 17.3 * o, y * f - 9.1 * o, salt + 101 * o)
        tot += amp
        amp *= 0.5
        f *= 2.03
    return out / tot


def _smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _ramp(v, lo, hi):
    return _smooth((np.asarray(v, np.float64) - lo) / (hi - lo))


# -- the per-sample facts of a course window ----------------------------------------------------------------------------
def _mean(v, r):
    v = np.asarray(v, np.float64)
    n = len(v)
    c = np.concatenate([[0.0], np.cumsum(v)])
    i = np.arange(n)
    lo, hi = np.maximum(0, i - r), np.minimum(n, i + r + 1)
    return (c[hi] - c[lo]) / (hi - lo)


def _minf(v, r):
    v = np.asarray(v, np.float64)
    out = v.copy()
    for k in range(1, r + 1):
        out[k:] = np.minimum(out[k:], v[:-k])
        out[:-k] = np.minimum(out[:-k], v[k:])
    return out


def window_profile(course, k, pieces, road_fn, elev_fn, water_fn=None, land_fn=None, waters_fn=None):
    """The facts of window k's samples a..b (inclusive): {algo, a, b, hw (track half width, m), rough (0 asphalt .. 1
    dirt), rock (0 .. 1: canyon walls, rocky hillside), turn (deg per sample, + left), lake (0 .. 1)}; from terrain
    version surfaces.FROM_TV on, also the ground's own facts (surfaces.window_facts: canyon floor, a mapped dirt road
    followed, dry land, wetland, the water around: land_fn(lats, lons) -> land-cover classes, waters_fn(lat0, lon0,
    lat1, lon1) -> the water features).
    pieces: the window's dirt track pieces (courseroads.window_pieces); road_fn(lat0, lon0, lat1, lon1, plane) ->
    [(ax, ay, bx, by, half width, paved)] of the drawn roads near (plane metres); elev_fn(lats, lons) -> heights;
    water_fn(lats, lons) -> 0 / 1 per point (on a dry or salt lake) or None. Every fact of a sample looks only at the
    courseroads.CONTEXT samples around it, so windows agree where they meet. Pure given the functions."""
    a, b = course.inner(k)
    c0, c1 = course.context(k)
    lat = np.asarray(course.lat[c0:c1 + 1], np.float64)
    lon = np.asarray(course.lon[c0:c1 + 1], np.float64)
    n = len(lat)
    pl = courseroads.Plane(float(lat.mean()), float(lon.mean()))
    x, y = pl.xy(lat, lon)
    tx, ty = courseroads.directions(list(map(float, x)), list(map(float, y)))
    tx, ty = np.asarray(tx), np.asarray(ty)

    # the roads: on a paved one (or by one), no relief; on a dirt one, its width
    pad = (courseroads.PAD_M + 20.0) / 111320.0
    padlo = pad / max(0.05, math.cos(math.radians(pl.lat0)))
    segs = road_fn(float(lat.min()) - pad, float(lon.min()) - padlo, float(lat.max()) + pad, float(lon.max()) + padlo,
                   pl)
    segs = np.asarray(segs if segs is not None and len(segs) else np.zeros((0, 6)), np.float64).reshape(-1, 6)
    hw = np.full(n, np.nan)
    ctr = np.zeros(n)               # the road's middle, m left (+) of the course line (the course on a road it follows)
    paved = np.zeros(n, bool)
    road = np.zeros(n)              # on a mapped road it follows (not its own track)
    if len(segs):
        A, B, H, P = segs[:, 0:2], segs[:, 2:4], segs[:, 4], segs[:, 5] > 0.5
        d = B - A
        L = np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-9)
        p = np.stack([x, y], 1)
        t = np.clip(((p[:, None, :] - A[None]) * d[None]).sum(2) / (L * L)[None], 0, 1)
        q = A[None] + t[:, :, None] * d[None]
        dist = np.hypot(q[..., 0] - p[:, None, 0], q[..., 1] - p[:, None, 1])          # (n, S)
        cosang = np.abs((d[None, :, 0] * tx[:, None] + d[None, :, 1] * ty[:, None]) / L[None])
        # (the course's own rule, courseroads.follow_rule: a dirt road from further off than a paved one)
        pad = np.where(P, COVER_PAD_M, courseroads.FOLLOW_UNPAVED_M)
        cmin = np.where(P, math.cos(math.radians(COVER_DEG)), math.cos(math.radians(courseroads.FOLLOW_UNPAVED_DEG)))
        along = (dist <= H[None] + pad[None]) & (cosang >= cmin[None])
        paved = ((dist <= H[None] + PAVED_NEAR_M) & P[None]).any(axis=1)
        dd = np.where(along, dist, np.inf)
        j = dd.argmin(axis=1)
        on = np.isfinite(dd[np.arange(n), j])
        paved |= on & P[j]
        hw = np.where(on, H[j], hw)
        road = on.astype(np.float64)
        qj = q[np.arange(n), j]
        ctr = np.where(on, (qj[:, 0] - x) * -ty + (qj[:, 1] - y) * tx, 0.0)
    # the dirt track's own width where it is laid
    idx = {(round(float(lo_), 7), round(float(la_), 7)): c0 + i for i, (la_, lo_) in enumerate(zip(lat, lon))}
    for pc in pieces or ():
        pts = pc.get("ll") or ()
        off = pc.get("off") or [0.0] * len(pts)
        for m_, q_ in enumerate(pts):
            if "i0" in pc:                  # (a piece names its samples: its ends may bend off the course line)
                i = int(pc["i0"]) + m_
                i = i if c0 <= i <= c1 else None
            else:
                i = idx.get((round(float(q_[0]), 7), round(float(q_[1]), 7)))
            if i is not None:
                hw[i - c0] = float(pc["w"]) / 2.0
                ctr[i - c0] = float(off[m_]) if m_ < len(off) else 0.0      # (on the course line but where it bends)
                road[i - c0] = 0.0
    hw = np.where(np.isfinite(hw), hw, DEFAULT_HALF_M)
    rough = _mean(_minf(np.where(paved, 0.0, 1.0), 3), 2)

    # the ground beside: a canyon (both sides rise), a rocky hillside (one side rises a lot)
    offs = np.asarray(SIDE_OFFS)
    qx = [x]
    qy = [y]
    for sgn in (1.0, -1.0):
        for o in offs:
            qx.append(x - ty * sgn * o)
            qy.append(y + tx * sgn * o)
    qla, qlo = pl.ll(np.concatenate(qx), np.concatenate(qy))
    z = np.asarray(elev_fn(np.asarray(qla).tolist(), np.asarray(qlo).tolist()), np.float64).reshape(1 + 2 * len(offs), n)
    zc = z[0]
    rl = (z[1:1 + len(offs)] - zc).max(axis=0)
    rr = (z[1 + len(offs):] - zc).max(axis=0)
    canyon = _ramp(np.minimum(rl, rr), *CANYON_RISE)
    hill = _ramp(np.maximum(rl, rr), *HILL_RISE)
    rock = _mean(np.maximum(canyon, 0.6 * hill), 2)

    # the turn at each sample (degrees per sample, left positive)
    hd = np.degrees(np.arctan2(ty, tx))
    dh = np.zeros(n)
    dh[1:-1] = (((hd[2:] - hd[:-2]) + 180.0) % 360.0 - 180.0) / 2
    turn = _mean(dh, 2)

    lake = np.zeros(n)
    if water_fn is not None:
        w = water_fn(lat.tolist(), lon.tolist())
        if w is not None:
            lake = _mean(np.asarray(w, np.float64), 3)

    s0, s1 = a - c0, b - c0 + 1

    def out(v, nd=3):
        return [round(float(u), nd) for u in v[s0:s1]]
    prof = {"algo": ALGO, "a": a, "b": b, "hw": out(hw, 2), "ctr": out(ctr, 1), "rough": out(rough), "rock": out(rock),
            "turn": out(turn, 2), "lake": out(lake)}
    if getattr(course, "tv", 1) >= VARIETY_TV:     # (terrain 7: the grade along the course, for the alluvial fans)
        prof["grade"] = out(_mean(np.abs(np.gradient(zc)) / STEP if n > 1 else np.zeros(n), 3), 4)
    from . import surfaces
    if getattr(course, "tv", 1) >= surfaces.FROM_TV:
        prof.update(surfaces.window_facts(lat, lon, x, y, tx, ty, pl, canyon, road, s0, s1, land_fn, waters_fn,
                                          tv=getattr(course, "tv", 1)))
    return prof


# -- the relief at points -------------------------------------------------------------------------------------------
FACT_FIELDS = ("hw", "ctr", "rough", "rock", "turn", "lake", "canyon", "road", "arid", "wetl", "cover", "grass",
               "grade", "washn", "sean")      # (the last three: from terrain version 7, variety.py)   # (the last four: from
                                                                                                # terrain version 3)


class _Facts:
    """The profiles' facts as arrays over samples [lo, hi]; samples with no profile: rough 0."""

    def __init__(self, profiles):
        # (in window order whatever order they came in: where two windows share their end sample, the later window's
        # facts, every time; a width step there is the later window's new width)
        ps = sorted((p for p in profiles.values() if p), key=lambda p: (p["a"], p["b"]))
        self.lo = min(p["a"] for p in ps)
        self.hi = max(p["b"] for p in ps)
        n = self.hi - self.lo + 1
        self.v = {f: np.zeros(n) for f in FACT_FIELDS}
        self.v["hw"][:] = DEFAULT_HALF_M
        for p in ps:
            for f in self.v:
                if p.get(f) is not None:
                    self.v[f][p["a"] - self.lo:p["b"] - self.lo + 1] = p[f]

    def at(self, s):
        u = np.clip(s / STEP - self.lo, 0, self.hi - self.lo)
        i = np.minimum(np.floor(u).astype(np.int64), max(0, self.hi - self.lo - 1))
        f = u - i
        j = np.minimum(i + 1, self.hi - self.lo)
        return {k: v[i] + (v[j] - v[i]) * f for k, v in self.v.items()}


def nearest(course, profiles, lat, lon, reach=REACH_M):
    """Per point: (index of the points within reach of the course line, their signed offset (m, + left of the course's
    direction), their distance along it (m)). Only the windows in profiles count (their segments a..b)."""
    lat = np.asarray(lat, np.float64).ravel()
    lon = np.asarray(lon, np.float64).ravel()
    N = len(lat)
    best = np.full(N, np.inf)
    off = np.zeros(N)
    s_at = np.zeros(N)
    CH = 8
    for k, p in sorted(profiles.items()):
        if not p:
            continue
        a, b = p["a"], p["b"]
        if b <= a:
            continue
        sl = np.asarray(course.lat[a:b + 1], np.float64)
        so = np.asarray(course.lon[a:b + 1], np.float64)
        pl = courseroads.Plane(float(sl[0]), float(so[0]))           # (one plane per window: whoever asks)
        cx, cy = pl.xy(sl, so)
        x0, x1 = cx.min() - reach, cx.max() + reach
        y0, y1 = cy.min() - reach, cy.max() + reach
        px, py = pl.xy(lat, lon)
        cand = np.flatnonzero((px >= x0) & (px <= x1) & (py >= y0) & (py <= y1))
        if not len(cand):
            continue
        qx, qy = px[cand], py[cand]
        for j0 in range(0, b - a, CH):
            j1 = min(b - a, j0 + CH)
            ax, ay = cx[j0:j1], cy[j0:j1]
            bx, by = cx[j0 + 1:j1 + 1], cy[j0 + 1:j1 + 1]
            m = ((qx >= min(ax.min(), bx.min()) - reach) & (qx <= max(ax.max(), bx.max()) + reach) &
                 (qy >= min(ay.min(), by.min()) - reach) & (qy <= max(ay.max(), by.max()) + reach))
            sel = np.flatnonzero(m)
            if not len(sel):
                continue
            X, Y = qx[sel][:, None], qy[sel][:, None]
            dx, dy = (bx - ax)[None], (by - ay)[None]
            L2 = np.maximum(dx * dx + dy * dy, 1e-12)
            t = np.clip(((X - ax[None]) * dx + (Y - ay[None]) * dy) / L2, 0, 1)
            ex, ey = X - (ax[None] + t * dx), Y - (ay[None] + t * dy)
            dist = np.hypot(ex, ey)
            jj = dist.argmin(axis=1)
            r = np.arange(len(sel))
            dmin = dist[r, jj]
            gi = cand[sel]
            better = dmin < best[gi]
            if not better.any():
                continue
            gi, r, jj, dmin = gi[better], r[better], jj[better], dmin[better]
            cross = dx[0, jj] * ey[r, jj] - dy[0, jj] * ex[r, jj]
            best[gi] = dmin
            off[gi] = np.where(cross >= 0, dmin, -dmin)
            s_at[gi] = (a + j0 + jj + t[r, jj]) * STEP
    idx = np.flatnonzero(best <= reach)
    return idx, off[idx], s_at[idx]


def _bin_features(course, s, rock):
    """The washes (-) and kickers (+) at s (m, relief before the lateral fade): one chance per BIN_M, each hashed from
    where the course is at its bin's middle."""
    lat = getattr(course, "_np_lat", None)
    if lat is None:
        course._np_lat = lat = np.asarray(course.lat, np.float64)
        course._np_lon = np.asarray(course.lon, np.float64)
    lon = course._np_lon
    out = np.zeros(len(s))
    b0 = np.floor(s / BIN_M).astype(np.int64)
    v4 = getattr(course, "tv", 1) >= DIPS_TV
    for db in (-1, 0, 1):
        bb = b0 + db
        mid = np.clip(((bb + 0.5) * BIN_M / STEP).astype(np.int64), 0, len(lat) - 1)
        qa = np.round(lat[mid] * 1e4).astype(np.int64)
        qo = np.round(lon[mid] * 1e4).astype(np.int64)
        has = _hash(qa, qo, 21) < P_FEATURE
        pos = (bb + 0.2 + 0.6 * _hash(qa, qo, 22)) * BIN_M
        kick = (_hash(qa, qo, 23) < P_KICKER) & (rock < 0.5)
        size = _hash(qa, qo, 24)
        dd = s - pos
        sig = 4.0 + 4.0 * _hash(qa, qo, 25)
        wash = -(0.35 + 0.6 * size) * np.exp(-(dd / sig) ** 2)
        up = np.where(dd < 0, np.exp(-(dd / 7.0) ** 2),
                      np.exp(-(dd / (KICK_BACK_V6 if getattr(course, "tv", 1) >= SMOOTH_TV else 3.2)) ** 2))
        kicker = (0.3 + 0.5 * size) * up
        if v4:
            # (the kickers as before; the washes rarer, a floor between eased banks: dip())
            # (the kickers exactly as terrain 3's: the spectators' jumps, spots.py, find them there)
            kick4 = has & kick
            wash4 = ~kick4 & (_hash(qa, qo, 28) < P_WASH_V4)
            deep = _hash(qa, qo, 26) < WASH_DEEP_P
            depth = np.where(deep, WASH_DEEP_M, WASH_DEPTH_V4[0] + (WASH_DEPTH_V4[1] - WASH_DEPTH_V4[0]) * size)
            floor = WASH_FLOOR_M[0] + (WASH_FLOOR_M[1] - WASH_FLOOR_M[0]) * _hash(qa, qo, 25)
            bank = WASH_BANK_M[0] + (WASH_BANK_M[1] - WASH_BANK_M[0]) * _hash(qa, qo, 27)
            out += np.where(kick4, kicker, 0.0) + np.where(wash4, dip(dd, depth, floor, bank), 0.0)
            continue
        out += np.where(has, np.where(kick, kicker, wash), 0.0)
    return out


# -- auto: the setting that varies along the course ----------------------------------------------------------------------
AUTO_ZONE_M = 1500.0
# (fbm's spread: ~10 % fast, ~25 % mild, ~40 % rough, ~25 % extra over a long course)
AUTO_STEPS = ((0.26, 0.30, 0.20), (0.42, 0.46, 0.45), (0.61, 0.65, 0.60))     # (from, to, level added)
AUTO_BASE = 0.35                                # the fast sections (mild is 0.55, rough 1.0, extra 1.6)
DANGER_LEVEL = 1.8
DANGER_RAMP = (160.0, 70.0, 70.0, 140.0)        # m: rising from .. full from (before) .. full to .. gone (after)
DANGER_NEAR_M = 80.0                            # a DANGER waypoint this near the course line is on it
HAZARD_P = (0.35, 0.30)                         # a ditch, a kicker; else a rock garden
HAZARD_ROCK_M = (35.0, 55.0)                    # the rock garden: before .. after the waypoint
ROCK_ZONE_M = 900.0
ROCK_ZONE = (0.55, 0.72)                        # rock fields where the noise is between these (none below)
AUTO_ROCK_P = 0.32                              # chance per slot (four per sample and side) at full
# (terrain 9, Baja only; the user, 2026-11-06: "on the Baja setting tune the roughness of the rough and above parts a
# bit down except for where there is the danger mark and on parts that aren't changed by the new terrain from the new
# BeamNG.Earth, i.e. parts that aren't marked as dirt roads ... The new terrain added a lot of roughness and its being
# amplified by ours ... make roughness sections rarer overall, the rougher the rarer except for mild sections")
AUTO_TV = 9
AUTO_STEPS_V9 = ((0.33, 0.365, 0.20), (0.53, 0.565, 0.45), (0.69, 0.725, 0.60))  # ~20 % fast, ~40 % mild, ~28 % rough,
                                                                                  # ~12 % extra
MILD_LEVEL = 0.55
ROAD_EXCESS_V9 = 0.65       # on a mapped dirt road the course follows (BeamNG.Earth 1.8.2 wears it), away from a DANGER
                            # waypoint's stretch: the level's part over Mild kept at this share (Rough 1.0 -> 0.84,
                            # Extra 1.6 -> 1.23); the course's own track and the DANGER stretches as before
# (terrain 10: BeamNG.Earth's wear kept off the mapped dirt roads the course runs along too, earthpatch.followed_rows;
# the user, 2026-11-08: "our track on baja still is being influenced by the vanilla BeamNG.Earth new dirt roads". With
# nothing to make up for, those stretches are as rough as the course's own track again; 9's shares stay.)
UNWORN_TV = 10


def danger_s(course, points):
    """Distances along the course (m) of the waypoints [(lat, lon)] within DANGER_NEAR_M of its line (the nearest
    sample), sorted. Pure."""
    if not points:
        return []
    lat = np.asarray(course.lat, np.float64)
    lon = np.asarray(course.lon, np.float64)
    out = []
    for la, lo in points:
        k = 111320.0 * math.cos(math.radians(la))
        d = np.hypot((lat - la) * 110574.0, (lon - lo) * k)
        i = int(d.argmin())
        if d[i] <= DANGER_NEAR_M:
            out.append(i * STEP)
    return sorted(out)


def course_auto(course):
    """Per sample of the course, for "auto": (level: the relief's scale, rock: a rockiness the hazards add, rocks: the
    boulder fields' chance per slot, hazard: per DANGER waypoint (s, kind 0 ditch / 1 kicker / 2 rocks, size)).
    Computed once per course (kept on it). Pure."""
    tv = getattr(course, "tv", 1)
    got = getattr(course, "_auto", None)
    if got is not None and got.get("tv") == tv:
        return got
    lat = np.asarray(course.lat, np.float64)
    lon = np.asarray(course.lon, np.float64)
    gx, gy = global_xy(lat, lon)
    v = fbm(gx / AUTO_ZONE_M, gy / AUTO_ZONE_M, 7, 2)
    level = np.full(len(lat), AUTO_BASE)
    for lo_, hi_, add in (AUTO_STEPS_V9 if tv >= AUTO_TV else AUTO_STEPS):
        level += add * _ramp(v, lo_, hi_)
    level = _mean(level, 4)                     # (~100 m blends)
    rock = np.zeros(len(lat))
    danger = np.zeros(len(lat))                 # (a DANGER waypoint's stretch: 1, easing out; auto_level)
    hz = []
    sv = np.arange(len(lat)) * STEP
    for sd in getattr(course, "dangers", None) or ():
        b0, b1, a0, a1 = DANGER_RAMP
        up = _ramp(sv, sd - b0, sd - b1) * (1.0 - _ramp(sv, sd + a0, sd + a1))
        level = np.maximum(level, AUTO_BASE + (DANGER_LEVEL - AUTO_BASE) * up)
        danger = np.maximum(danger, up)
        i = min(len(lat) - 1, int(round(sd / STEP)))
        qa, qo = int(round(lat[i] * 1e5)), int(round(lon[i] * 1e5))
        u = float(_hash(qa, qo, 31))
        kind = 0 if u < HAZARD_P[0] else (1 if u < HAZARD_P[0] + HAZARD_P[1] else 2)
        hz.append((sd, kind, float(_hash(qa, qo, 32))))
        if kind == 2:
            rock = np.maximum(rock, 0.9 * _ramp(sv, sd - HAZARD_ROCK_M[0] - 20, sd - HAZARD_ROCK_M[0]) *
                              (1.0 - _ramp(sv, sd + HAZARD_ROCK_M[1], sd + HAZARD_ROCK_M[1] + 20)))
    rv = fbm(gx / ROCK_ZONE_M, gy / ROCK_ZONE_M, 9, 2)
    fields = AUTO_ROCK_P * _ramp(rv, *ROCK_ZONE) ** 1.5
    # (terrain 7: the DANGER waypoints that are rock crawls where they are in a canyon: variety.py)
    from . import variety
    crawl = []
    for sd in getattr(course, "dangers", None) or ():
        i = min(len(lat) - 1, int(round(sd / STEP)))
        qa, qo = int(round(lat[i] * 1e5)), int(round(lon[i] * 1e5))
        if float(_hash(qa, qo, 33)) < variety.CRAWL_P:
            crawl.append((sd, float(_hash(qa, qo, 34))))
    course._auto = got = {"level": level, "rock": rock, "rocks": np.maximum(fields, 0.6 * rock), "hazard": hz,
                          "crawl": crawl, "danger": danger, "tv": tv}
    return got


def auto_level(course, A, s, f):
    """course_auto's level at s (m along the course): in terrain 9 (AUTO_TV up to UNWORN_TV), its part over Mild
    softened on a mapped dirt road the course follows (f["road"], the profiles' facts at s), outside the DANGER
    waypoints' stretches. Pure."""
    lv = _per_sample(A["level"], s)
    if not AUTO_TV <= getattr(course, "tv", 1) < UNWORN_TV:
        return lv
    road = np.clip(np.asarray(f["road"], np.float64), 0.0, 1.0) * (1.0 - _per_sample(A["danger"], s))
    return lv - np.maximum(lv - MILD_LEVEL, 0.0) * (1.0 - ROAD_EXCESS_V9) * road


def _per_sample(v, s):
    u = np.clip(s / STEP, 0, len(v) - 1)
    i = np.minimum(np.floor(u).astype(np.int64), max(0, len(v) - 2))
    f = u - i
    j = np.minimum(i + 1, len(v) - 1)
    return v[i] + (v[j] - v[i]) * f


def _hazards(hz, s, tv=1):
    """The DANGER waypoints' ditches (-) and kickers (+) at s (m, before the lateral fade)."""
    out = np.zeros(len(s))
    for sd, kind, size in hz:
        dd = s - sd
        if kind == 0 and tv >= DIPS_TV:     # (terrain 4: a floor between eased banks)
            out += dip(dd, 0.7 + 0.35 * size, DITCH_FLOOR_M[0] + (DITCH_FLOOR_M[1] - DITCH_FLOOR_M[0]) * size,
                       DITCH_BANK_M[0] + (DITCH_BANK_M[1] - DITCH_BANK_M[0]) * size)
        elif kind == 0:
            out += -(0.75 + 0.35 * size) * np.exp(-(dd / (4.5 + 2.0 * size)) ** 2)
        elif kind == 1:
            back = KICK_BACK_V6 if tv >= SMOOTH_TV else 3.0
            up = np.where(dd < 0, np.exp(-(dd / 8.0) ** 2), np.exp(-(dd / back) ** 2))
            out += (0.65 + 0.35 * size) * up
    return out


# (terrain 6; the user, 2026-10-30, screenshots of saw-toothed berms and pyramids along the track: "Terrain now feels
# too angular, to polygony and unnatural looking and feeling ... it shouldn't be as angular or spiky. I want it to look
# and feel real ... like real baja racing terrain") The physics ground and the drawn ground are a 2 m lattice of
# triangles. Terrain 1-5's narrow shapes were narrower than that: berms 0.8-1.3 m wide, a rut chop of 3.5 m, the broken
# ground's second octave at 4.4 m, the rock ledges' steps over a quarter of a cycle, the banked corner's crease at the
# track's edge. On the lattice one point stood on such a shape and the next beside it: saw teeth along every edge and
# lone pyramids, the same in the tyres. From terrain 6 every shape is at least ~3 lattice cells wide (no feature under
# ~6 m, no edge over less than ~3 m) and has no creases, the way blown sand and worn dirt lie: whoops a little longer,
# broken ground in long swells, windrows and sand on the outside of the turns as wide soft mounds, the banked corner a
# smooth bowl with its lip past the edge. The heights are much as before; only their shapes are softer.
SMOOTH_TV = 6
WHOOP_L1_V6, WHOOP_L2_V6 = 12.5, 27.0
BUMP_V6_M = 17.0            # the broken ground's swells (two octaves: ~17 m and ~8.4 m)
LEDGE_V6_M, LEDGE_V6 = 26.0, 0.32       # rock ledges: the noise's size, their height
EDGE_V6 = (1.4, 2.2)        # the windrow: its middle past the edge, its width (Gaussian)
TURN_V6 = (2.0, 3.2, 0.42)  # sand on the outside of a turn: its middle past the edge, its width, its height
WEAR_V6_EDGE = 3.0          # the worn floor eases into the sides over this
KICK_BACK_V6 = 4.5          # a kicker's back falls off over this (terrain 1-5: 3.2; the DANGER kickers 3.0)
BANK_V6 = (2.5, 0.55, 1.2, 6.0)     # the bowl: the inside dig starts this far past the inner edge, its bottom this
# share of the half width in from it; the lip's crest this far past the outer edge, falling back over this
RUT_V6 = (1.2, 2.0, 7.0)    # ruts: the thrown dirt's middle past the edge, its width; the chop's size


def _ease(x, x0, x1, v0, v1):
    """v0 before x0, v1 after x1, a smoothstep between (no crease at either end). Pure."""
    return v0 + (v1 - v0) * _smooth((x - x0) / np.maximum(x1 - x0, 1e-6))


def bank_dz_v6(x, hw, slope):
    """Terrain 6's banked corner at x (m toward the outside from the track's middle): a smooth bowl, dug a little on the
    inside, rising across the track to a soft lip of pushed-up dirt past the outer edge that falls back into the ground
    behind it; C1 everywhere (no crease to sit on the 2 m lattice). Pure."""
    x = np.asarray(x, np.float64)
    dig_from, bottom, crest, fall = BANK_V6
    top = slope * hw                        # the lip over the middle's ground
    low = -BANK_INSIDE * slope * hw
    xa, xb = -hw - dig_from, -hw + bottom * hw
    xc, xd = hw + crest, hw + crest + fall
    return np.where(x < xb, _ease(x, xa, xb, 0.0, low),
                    np.where(x < xc, _ease(x, xb, xc, low, top), _ease(x, xc, xd, top, 0.0)))


def _shape_v6(course, s, d, ad, hw, rock, f, gx, gy, power, wash_on, var=None):
    """Terrain 6's relief before the clamp and the DANGER hazards (relief()): every shape at least ~3 lattice cells
    wide (the note on SMOOTH_TV). var (terrain 7: variety.py): the sections' weights per point {sand, rock, gravel,
    crawl}; None: terrain 6's ground exactly."""
    on = 1.0 - _smooth((ad - hw - EDGE_M) / FADE_M)
    # whoops: the same sections and heights, a little longer
    zone = _ramp(fbm(gx / WHOOP_ZONE_M, gy / WHOOP_ZONE_M, 1, 2), *WHOOP_ZONE)
    amp = (WHOOP_A[0] + (WHOOP_A[1] - WHOOP_A[0]) * zone) * (1.0 - 0.6 * rock)
    if var is not None:
        from . import variety as vy
        amp = amp * (1.0 - vy.ROCK_WHOOPS * var["rock"] - vy.GRAVEL_WHOOPS * var["gravel"])
    skew = 0.35 * (2.0 * vnoise(gx / SKEW_M, gy / SKEW_M, 2) - 1.0)
    sp = s + d * skew
    wave = 0.5 * (1.0 - np.cos(2 * np.pi * sp / WHOOP_L1_V6)) * (0.72 + 0.28 * np.sin(2 * np.pi * sp / WHOOP_L2_V6 + 0.8))
    h = amp * (wave - 0.4) * on
    # broken ground: long swells; rock ledges with soft steps
    bump = (fbm(gx / BUMP_V6_M, gy / BUMP_V6_M, 3, 2) - 0.5) * 2.0
    h += (BUMP_M[0] + (BUMP_M[1] - BUMP_M[0]) * rock) * bump * on
    v = fbm(gx / LEDGE_V6_M, gy / LEDGE_V6_M, 4, 2) * 4.0
    step = (np.floor(v) + _smooth((v - np.floor(v) - 0.3) / 0.7)) / 4.0 - 0.5
    h += LEDGE_V6 * rock * step * on
    # worn in, a windrow along the edges, sand on the outside of the turns: wide soft mounds
    inner = 1.0 - _smooth((ad - hw + WEAR_V6_EDGE) / WEAR_V6_EDGE)
    h -= WEAR_M * inner
    if var is None:
        h += EDGE_BERM_M * np.exp(-((ad - hw - EDGE_V6[0]) / EDGE_V6[1]) ** 2)
    else:                               # (gravel's windrow at the edges; a sand trap's sand in place of the dirt's)
        h += (EDGE_BERM_M * (1.0 - var["sand"]) + vy.GRAVEL_EDGE * var["gravel"]) * \
            np.exp(-((ad - hw - EDGE_V6[0]) / EDGE_V6[1]) ** 2)
    # (in a banked corner the bowl's lip is the sand pushed out: no second mound on it)
    bw = bank_weight(course, s, f["turn"], power) * (1.0 - rock) * (1.0 - f["lake"])
    if var is not None:                 # (no bowl on rock or in a crawl)
        bw = bw * (1.0 - var["rock"]) * (1.0 - var["crawl"])
    outside = np.where(f["turn"] > 0, d < 0, d > 0)
    tb = TURN_V6[2] * _ramp(np.abs(f["turn"]), 1.5, TURN_FULL_DEG) * (1.0 - 0.5 * rock) * (1.0 - bw)
    if var is not None:
        tb = tb * (1.0 - var["sand"])
    h += np.where(outside, tb * np.exp(-((ad - hw - TURN_V6[0]) / TURN_V6[1]) ** 2), 0.0)
    # washes across the course and kickers (a kicker's back softer)
    h += _bin_features(course, s, rock) * wash_on
    h = h * power
    if var is not None:
        # sand traps: the track sunk into soft sand, churned, the sand thrown beside it
        ws = var["sand"]
        if ws.any():
            churn = (fbm(gx / vy.SAND_CHURN_M, gy / vy.SAND_CHURN_M, 71, 1) - 0.5) * 2.0
            sunk = 1.0 - _smooth((ad - hw + vy.SAND_FLOOR_IN[0]) / vy.SAND_FLOOR_IN[1])   # (edge to edge, eased)
            h += ws * np.minimum(power, 1.0) * (-vy.SAND_SINK * sunk + vy.SAND_CHURN * churn * sunk
                               + vy.SAND_BERM * np.exp(-((ad - hw - vy.SAND_BERM_AT[0]) / vy.SAND_BERM_AT[1]) ** 2))
        # rock sections: stronger ledges and rocky lumps
        wr = var["rock"]
        if wr.any():
            v2 = fbm(gx / vy.ROCK_LEDGE_M, gy / vy.ROCK_LEDGE_M, 73, 2) * 4.0
            step2 = (np.floor(v2) + _smooth((v2 - np.floor(v2) - 0.3) / 0.7)) / 4.0 - 0.5
            lump = (fbm(gx / vy.ROCK_BUMP_M, gy / vy.ROCK_BUMP_M, 75, 2) - 0.5) * 2.0
            h += wr * power * (vy.ROCK_LEDGE * step2 + vy.ROCK_BUMP * lump) * on
    # banked corners: a smooth bowl
    if bw.any():
        x = np.where(f["turn"] > 0, -d, d)
        slope = (BANK_SLOPE[0] + (BANK_SLOPE[1] - BANK_SLOPE[0]) * _ramp(np.abs(f["turn"]), *BANK_TURN)) * bw
        h += bank_dz_v6(x, hw, slope)
    # rutted sections: the worn floor, the thrown dirt beside it, chopped up in swells of a few metres
    rw = rut_weight(gx, gy, hw, power, f["road"]) * (1.0 - f["lake"])
    if var is not None:                 # (rock does not rut; in a sand trap the churn in place of their chop)
        rw = rw * (1.0 - var["rock"]) * (1.0 - var["crawl"]) * (1.0 - vy.SAND_RUTS * var["sand"])
    if rw.any():
        chop = (fbm(gx / RUT_V6[2], gy / RUT_V6[2], 43, 1) - 0.5) * 2.0
        h += rw * (-RUT_SINK * inner + RUT_BERM * np.exp(-((ad - hw - RUT_V6[0]) / RUT_V6[1]) ** 2)
                   + RUT_CHOP * chop * inner)
    if var is not None and var["crawl"].any():     # (a rock crawl: shelves of rock, the track's own relief faded)
        wc = var["crawl"]
        h = h * (1.0 - vy.CRAWL_FLATTEN * wc) + wc * vy.crawl_dz(s, d, ad, hw, gx, gy) * f["rough"] * \
            (1.0 - 0.85 * f["lake"])
    h = _soft_clamp(h, *CLAMP)                      # (no flat-topped plateau with a crease round it)
    return np.where(np.abs(h) < 1e-5, 0.0, h)     # (the wide mounds' far tails: the ground away from the track as it is)


def _soft_clamp(h, lo, hi, knee=0.6):
    """h within (lo, hi), unchanged up to knee x the limit and easing into it beyond (tanh): terrain 6's in place of a
    hard clip, whose flat top had a crease all round. Pure."""
    kh, kl = knee * hi, knee * lo
    up = kh + (hi - kh) * np.tanh((h - kh) / (hi - kh))
    dn = kl + (lo - kl) * np.tanh((h - kl) / (lo - kl))
    return np.where(h > kh, up, np.where(h < kl, dn, h))


def relief(course, profiles, lat, lon, scale=1.0, auto=False, near=None):
    """Metres to add to the ground's heights at the points (any shape; the result has it). Zero away from the course,
    on asphalt and where no profile is at hand. auto: the scale varies along the course (course_auto), times scale.
    near: nearest()'s answer for these points and profiles (computed when None)."""
    shape = np.shape(lat)
    lat = np.asarray(lat, np.float64).ravel()
    lon = np.asarray(lon, np.float64).ravel()
    dz = np.zeros(len(lat))
    profiles = {k: p for k, p in profiles.items() if p}
    if not profiles or not len(lat) or scale <= 0:
        return dz.reshape(shape)
    idx, d, s = near if near is not None else nearest(course, profiles, lat, lon)
    if not len(idx):
        return dz.reshape(shape)
    f = _Facts(profiles).at(s)
    gx, gy = global_xy(lat[idx], lon[idx])
    hw, rock = f["hw"], f["rock"]
    power = f["rough"] * (1.0 - 0.85 * f["lake"]) * scale
    if auto:
        A = course_auto(course)
        power = power * auto_level(course, A, s, f)
        rock = np.maximum(rock, _per_sample(A["rock"], s))
    d = d - f["ctr"]                 # (from the middle of the track: a dirt road the course follows off its line)
    ad = np.abs(d)
    wash_on = 1.0 - _smooth((ad - hw - WASH_PAST_M) / WASH_FADE_M)
    if getattr(course, "tv", 1) >= SMOOTH_TV:
        var = None
        if getattr(course, "tv", 1) >= VARIETY_TV:
            from . import variety
            vs, vr, vg = variety.weights(course, s, f)
            vc = variety.crawl_weight(course, s, f) if auto else np.zeros(len(s))
            var = {"sand": vs * (1.0 - vc), "rock": vr * (1.0 - vc), "gravel": vg * (1.0 - vc), "crawl": vc}
        h = _shape_v6(course, s, d, ad, hw, rock, f, gx, gy, power, wash_on, var)
        if auto and A["hazard"]:
            hz = _hazards(A["hazard"], s, getattr(course, "tv", 1)) * wash_on * f["rough"] * (1.0 - 0.85 * f["lake"])
            h += hz if var is None else hz * (1.0 - var["crawl"])     # (a crawl in place of its ditch or kicker)
        dz[idx] = np.clip(h, *CLAMP)
        return dz.reshape(shape)
    on = 1.0 - _smooth((ad - hw - EDGE_M) / FADE_M)                      # the track and a little past its edges
    # whoops: two waves across the track, a little diagonal, high in whoop sections, low rollers elsewhere
    zone = _ramp(fbm(gx / WHOOP_ZONE_M, gy / WHOOP_ZONE_M, 1, 2), *WHOOP_ZONE)
    amp = (WHOOP_A[0] + (WHOOP_A[1] - WHOOP_A[0]) * zone) * (1.0 - 0.6 * rock)
    skew = 0.35 * (2.0 * vnoise(gx / SKEW_M, gy / SKEW_M, 2) - 1.0)
    sp = s + d * skew
    wave = 0.5 * (1.0 - np.cos(2 * np.pi * sp / WHOOP_L1)) * (0.72 + 0.28 * np.sin(2 * np.pi * sp / WHOOP_L2 + 0.8))
    h = amp * (wave - 0.4) * on
    # broken ground; stepped rock in rocky places
    bump = (fbm(gx / 9.0, gy / 9.0, 3, 2) - 0.5) * 2.0
    h += (BUMP_M[0] + (BUMP_M[1] - BUMP_M[0]) * rock) * bump * on
    v = fbm(gx / 16.0, gy / 16.0, 4, 2) * 5.0
    step = (np.floor(v) + _smooth((v - np.floor(v) - 0.75) / 0.25)) / 5.0 - 0.5
    h += LEDGE_M * rock * step * on
    # worn in, a windrow along the edges, sand on the outside of the turns
    inner = 1.0 - _smooth((ad - hw + 0.5) / 1.0)
    h -= WEAR_M * inner
    h += EDGE_BERM_M * np.exp(-((ad - hw - EDGE_M) / 0.9) ** 2)
    outside = np.where(f["turn"] > 0, d < 0, d > 0)                     # (left turn: the right side, d < 0)
    tb = TURN_BERM_M * _ramp(np.abs(f["turn"]), 1.5, TURN_FULL_DEG) * (1.0 - 0.5 * rock)
    h += np.where(outside, tb * np.exp(-((ad - hw - 0.8) / 1.3) ** 2), 0.0)
    # washes across the course and kickers
    h += _bin_features(course, s, rock) * wash_on
    h = h * power
    if getattr(course, "tv", 1) >= BANKS_TV:
        # banked corners (bank_weight): the corner's own height across the track, after the roughness (its size is the
        # corner's, not the setting's)
        bw = bank_weight(course, s, f["turn"], power) * (1.0 - rock) * (1.0 - f["lake"])
        if bw.any():
            x = np.where(f["turn"] > 0, -d, d)          # (toward the outside: a left turn's is its right, d < 0)
            slope = (BANK_SLOPE[0] + (BANK_SLOPE[1] - BANK_SLOPE[0]) * _ramp(np.abs(f["turn"]), *BANK_TURN)) * bw
            h += bank_dz(x, hw, slope)
    if getattr(course, "tv", 1) >= RUTS_TV:
        rw = rut_weight(gx, gy, hw, power, f["road"]) * (1.0 - f["lake"])
        if rw.any():
            chop = (fbm(gx / 3.5, gy / 3.5, 43, 2) - 0.5) * 2.0
            h += rw * (-RUT_SINK * inner + RUT_BERM * np.exp(-((ad - hw - 0.4) / 0.8) ** 2) + RUT_CHOP * chop * inner)
    if auto and A["hazard"]:                    # (full size wherever the course is on dirt)
        h += _hazards(A["hazard"], s, getattr(course, "tv", 1)) * wash_on * f["rough"] * (1.0 - 0.85 * f["lake"])
    dz[idx] = np.clip(h, *CLAMP)
    return dz.reshape(shape)


def ruts_at(course, profiles, lat, lon, scale=1.0, auto=False, near=None):
    """Per point: rut_weight on the track (0 off it, before terrain RUTS_TV, on Flat): where the drawn ruts braid
    (ruts.py, the rutted sections). Pure."""
    lat = np.asarray(lat, np.float64).ravel()
    lon = np.asarray(lon, np.float64).ravel()
    out = np.zeros(len(lat))
    profiles = {k: p for k, p in profiles.items() if p}
    if getattr(course, "tv", 1) < RUTS_TV or not profiles or not len(lat) or scale <= 0:
        return out
    idx, d, s = near if near is not None else nearest(course, profiles, lat, lon)
    if not len(idx):
        return out
    f = _Facts(profiles).at(s)
    power = f["rough"] * (1.0 - 0.85 * f["lake"]) * scale
    if auto:
        power = power * auto_level(course, course_auto(course), s, f)
    gx, gy = global_xy(lat[idx], lon[idx])
    on = np.abs(d - f["ctr"]) <= f["hw"] + 0.5
    rw = rut_weight(gx, gy, f["hw"], power, f["road"]) * (1.0 - f["lake"]) * on
    if getattr(course, "tv", 1) >= VARIETY_TV:     # (none on rock: _shape_v6's)
        from . import variety
        _vs, vr, _vg = variety.weights(course, s, f)
        vc = variety.crawl_weight(course, s, f) if auto else np.zeros(len(s))
        rw = rw * (1.0 - vr * (1.0 - vc)) * (1.0 - vc)
    out[idx] = rw
    return out


# -- boulders beside the track ----------------------------------------------------------------------------------------
def rocks(course, profiles, bounds, auto=False):
    """Boulders beside the track where it is rocky (canyons, rocky hillsides) inside bounds (lon0, lat0, lon1, lat1):
    arrays (lon, lat, size m, yaw deg, rank, scale), hashed from each sample's place. auto: also the boulder fields
    and the rock gardens of course_auto. Pure."""
    lon0, lat0, lon1, lat1 = bounds
    out = {k: [] for k in ("lon", "lat", "size", "yaw", "rank", "scale")}
    A = course_auto(course) if auto else None
    v7 = getattr(course, "tv", 1) >= VARIETY_TV
    if v7:
        from . import variety
    for k, p in sorted(profiles.items()):
        if not p:
            continue
        a, b = p["a"], p["b"]
        if v7 and b > a:            # (terrain 7: more boulders in rock sections, the crawls' own)
            sv = np.arange(a, b) * STEP
            fv = _Facts({k: p}).at(sv)
            _vs, vrock, _vg = variety.weights(course, sv, fv)
            vcrawl = variety.crawl_weight(course, sv, fv) if auto else np.zeros(len(sv))
        for i in range(a, b):
            j = i - a
            rk, ru, lk = p["rock"][j], p["rough"][j], p["lake"][j]
            pf = 0.0
            if A is not None:
                rk = max(rk, float(A["rock"][i]))
                pf = float(A["rocks"][i]) * (1.0 + 0.8 * rk)              # (more where the ground is rocky)
            wr = float(vrock[j]) if v7 else 0.0
            wc = float(vcrawl[j]) if v7 else 0.0
            if ru < 0.5 or lk > 0.5 or (rk < ROCK_FROM and pf <= 0.0 and wr < 0.3 and wc < 0.4):
                continue
            la0, lo0, la1, lo1 = course.lat[i], course.lon[i], course.lat[i + 1], course.lon[i + 1]
            if max(lo0, lo1) < lon0 - 0.001 or min(lo0, lo1) > lon1 + 0.001 or \
                    max(la0, la1) < lat0 - 0.001 or min(la0, la1) > lat1 + 0.001:
                continue
            pl = courseroads.Plane(la0, lo0)
            ex, ey = pl.xy(la1, lo1)
            L = math.hypot(ex, ey)
            if L < 1e-6:
                continue
            tx, ty = ex / L, ey / L
            hw = p["hw"][j]
            ctr = p["ctr"][j] if p.get("ctr") else 0.0
            qa, qo = int(round(la0 * 1e5)), int(round(lo0 * 1e5))
            slots = []          # (salt base: the canyons' as before, auto's its own), side, offset, size
            pr = ROCK_P * (rk - ROCK_FROM) / (1.0 - ROCK_FROM) if rk >= ROCK_FROM else 0.0
            if wr >= 0.3:
                pr = max(pr, variety.ROCK_BOULDER_P * wr)
            for slot in range(4):                       # canyons and hillsides: two each side, close in
                if _hash(qa, qo, 40 + slot) < pr:
                    o = hw + 0.9 + 3.6 * float(_hash(qa, qo, 50 + slot)) ** 1.5
                    size = 0.35 + min(1.5, 0.25 + 0.45 * (o - hw)) * float(_hash(qa, qo, 70 + slot))
                    slots.append((slot, 1.0 if slot < 2 else -1.0, o, size))
            h = lambda base, slot: float(_hash(qa, qo, 300 + 20 * base + slot))    # noqa: E731
            for slot in range(8):                       # auto's fields: four each side, small near, bigger further
                if pf > 0.0 and h(0, slot) < pf:
                    o = hw + 0.7 + 7.0 * h(1, slot) ** 1.3
                    u = h(2, slot)
                    size = 0.25 + (0.3 + 0.12 * (o - hw)) * u + (0.8 * u ** 6 if o - hw > 3.0 else 0.0)
                    slots.append((300 + slot, 1.0 if slot < 4 else -1.0, o, min(2.2, size)))   # (salts 360+ on)
            along = {}
            if wc >= 0.4:
                for slot, side, o, size, t_ in variety.crawl_rocks(course, p, i, j, la0, lo0, la1, lo1, wc):
                    slots.append((slot, side, o, size))
                    along[slot] = t_
            for slot, side, o, size in slots:
                t = (along[slot] if slot in along else float(_hash(qa, qo, 60 + slot))) * L
                lat_ = ctr + side * o                   # (beside the road's middle)
                x, y = tx * t - ty * lat_, ty * t + tx * lat_
                la, lo = pl.ll(x, y)
                if not (lon0 <= lo < lon1 and lat0 <= la < lat1):
                    continue
                out["lon"].append(lo)
                out["lat"].append(la)
                out["size"].append(size)
                out["yaw"].append(float(_hash(qa, qo, 80 + slot)) * 360.0)
                out["rank"].append(float(_hash(qa, qo, 90 + slot)) * 0.2)
                out["scale"].append(0.85 + 0.3 * float(_hash(qa, qo, 100 + slot)))
    return {k: np.asarray(v, np.float64) for k, v in out.items()}
