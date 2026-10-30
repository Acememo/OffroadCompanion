"""Natural cut banks beside the course's dirt track (the user, 2026-10-25, a photo of a smooth bare cliff beside the
track on a hillside: "can we avoid this kind of wall/road that appeared too unnatural? but without modifying the rest
of road gen because it's really good and fun right now").

BeamNG.Earth cuts a road into a hillside with a retaining wall's step (grading.WALL_CUT_M): a strip at the road's
level behind the core's edge, the ground jumping up 1.5 - 2 m within half a metre, then its transition back to the
natural ground (over T_MAX, 12 m from the core: on a steep hillside steeper than the hillside itself). Beside a built
road a stone wall stands on the step (roads.retaining_walls); beside a dirt road none does (BUILT roads only), so a
dirt track along a hillside ran beside a bare, smooth face of ground.

Here, only there (beside the course's dirt track or a dirt road it follows, on the side where BeamNG.Earth's grading
made that step), the ground from where the grading leaves the road's level back up to the hillside is a straight cut
bank instead, as a grader leaves one: rising at BANK_GRADE (about 39 degrees), or steeper where the hillside is so steep
that it would not meet it within REACH_M otherwise, never over the natural ground. The track itself, the other side,
every other road and every gentle 1:2 transition stay exactly as BeamNG.Earth graded them.

The step is read from BeamNG.Earth's own grading (grade_fn) at probes across the edge every BIN_M of course and side
(the road's level, where the grading leaves it, the largest jump between two probes). The probes depend only on the
course, never on which points were asked for, so the physics block, the road tiles and the ground tiles all get the
same bank.

Terrain version 2 (terrain.py): a course of version 1 keeps BeamNG.Earth's step. Pure numpy given the functions.
"""
import numpy as np

from . import courseroads, relief

FROM_TV = 2                 # the terrain version these banks came in with
SHOULDER_M = 1.0            # (grading.SHOULDER_M: the core is the road's half width plus this)
PROBE_FROM_M = -1.5         # the probes across the edge: from this far inside the core's edge ...
PROBE_TO_M = 5.0            # ... to this far out (the step: 2 - 2.8 m out from BeamNG.Earth's own edge)
PROBE_STEP_M = 0.5
LEVEL_TOL_M = 0.05          # the grading at the road's level: within this of it
JUMP_M = (0.45, 0.7)        # m the ground rises between two probes: a slope .. a step (a 1:2 slope: 0.25 - 0.4)
BANK_GRADE = 0.8            # rise per metre out, at least
REACH_M = 15.0              # m out from the road's level the bank meets the natural ground at the latest
BIN_M = 1.0                 # m of course between probes
OVER_TOL_M = 0.05           # only ground the grading left between the road's level and the natural ground is banked


def _ramp(v, lo, hi):
    return np.clip((v - lo) / (hi - lo), 0.0, 1.0)


def probes(course, facts, s, side, grade_fn, elev_fn):
    """At distances s along the course on side (+1 left, -1 right): the road's level beside the track, the offset
    (m from the track's middle, unsigned) where the grading leaves it, how much a step stands there (0 .. 1) and the
    bank's grade (rise per metre). Each probe in a plane of its own sample's: the same whichever others are asked with
    it. Pure given the functions."""
    lat_all = np.asarray(course.lat, np.float64)
    lon_all = np.asarray(course.lon, np.float64)
    n = len(lat_all)
    step = relief.STEP
    s = np.clip(np.asarray(s, np.float64), 0.0, (n - 1) * step)
    side = np.asarray(side, np.float64)
    k = len(s)
    i = np.minimum((s / step).astype(np.int64), max(0, n - 2))
    t = s / step - i
    j = np.minimum(i + 1, n - 1)
    lat0, lon0 = lat_all[i], lon_all[i]
    kx = np.radians(1.0) * courseroads.R_EARTH * np.cos(np.radians(lat0))
    ky = np.radians(1.0) * courseroads.R_EARTH
    dx, dy = (lon_all[j] - lon0) * kx, (lat_all[j] - lat0) * ky
    L = np.maximum(np.hypot(dx, dy), 1e-9)
    nx, ny = -dy / L, dx / L                                # (left of the course's direction)
    px, py = dx * t, dy * t
    f = facts.at(s)
    ctr, edge = f["ctr"], f["hw"] + SHOULDER_M

    def at(a):
        """lat, lon of the points a m (k, m) out from the track's middle on each probe's side."""
        o = ctr[:, None] + side[:, None] * a
        return (lat0[:, None] + (py[:, None] + ny[:, None] * o) / ky,
                lon0[:, None] + (px[:, None] + nx[:, None] * o) / kx[:, None])
    offs = np.arange(PROBE_FROM_M, PROBE_TO_M + 1e-9, PROBE_STEP_M)
    a = edge[:, None] + offs[None, :]                       # (k, m)
    la, lo = at(a)
    nat = np.asarray(elev_fn(la.ravel(), lo.ravel()), np.float64).reshape(a.shape)
    g = np.asarray(grade_fn(la.ravel(), lo.ravel(), nat.ravel()), np.float64).reshape(a.shape)
    z_road = g[:, 0]
    level = np.abs(g - z_road[:, None]) <= LEVEL_TOL_M
    m = a.shape[1]
    first_off = np.where(~level.all(axis=1), np.argmax(~level, axis=1), m)     # (the first probe off the road's level)
    last = np.maximum(first_off - 1, 0)
    a_flat = a[np.arange(k), last]
    jump = np.diff(g, axis=1)                               # (k, m - 1): the rise to each next probe
    past = np.arange(m - 1)[None, :] >= last[:, None]
    wall = _ramp(np.where(past, jump, 0.0).max(axis=1), *JUMP_M)
    rla, rlo = at((a_flat + REACH_M)[:, None])
    n_reach = np.asarray(elev_fn(rla.ravel(), rlo.ravel()), np.float64)
    grade = np.maximum(BANK_GRADE, (n_reach - z_road) / REACH_M)
    return z_road, a_flat, wall, grade


def bank(x, z_road, natural, grade):
    """The cut bank's height x m out from where the grading leaves the road's level: a straight slope up from it at
    grade, the natural ground where it meets it (never over it). Pure."""
    return np.minimum(natural, z_road + grade * np.maximum(x, 0.0))


def banks(course, profiles, lat, lon, base, graded, grade_fn, elev_fn, near=None):
    """graded (BeamNG.Earth's heights at the points, any shape; base: the natural ones) with the course's cut banks
    in place of a wall's step. grade_fn(lat, lon, natural) -> BeamNG.Earth's graded heights there; elev_fn(lat, lon) ->
    natural heights; near: relief.nearest's answer for these points (computed when None). Pure given the functions."""
    shape = np.shape(graded)
    out = np.asarray(graded, np.float64).ravel().copy()
    profiles = {k: p for k, p in profiles.items() if p}
    if not profiles or not len(out) or getattr(course, "tv", FROM_TV) < FROM_TV:
        return out.reshape(shape)
    lat = np.asarray(lat, np.float64).ravel()
    lon = np.asarray(lon, np.float64).ravel()
    base = np.asarray(base, np.float64).ravel()
    idx, d, s = near if near is not None else relief.nearest(course, profiles, lat, lon)
    if not len(idx):
        return out.reshape(shape)
    facts = relief._Facts(profiles)
    f = facts.at(s)
    dd = d - f["ctr"]
    ad = np.abs(dd)
    x0 = ad - (f["hw"] + SHOULDER_M)
    m = (x0 > PROBE_FROM_M) & (x0 < PROBE_TO_M + REACH_M) & (f["rough"] > 0.5) & (f["lake"] < 0.5) & (dd != 0)
    if not m.any():
        return out.reshape(shape)
    idx, dd, ad, s = idx[m], dd[m], ad[m], s[m]
    left = dd > 0
    u = np.maximum(s, 0.0) / BIN_M
    b0 = np.floor(u).astype(np.int64)
    t = u - b0
    k0, k1 = b0 * 2 + left, (b0 + 1) * 2 + left
    keys = np.unique(np.concatenate([k0, k1]))
    z_road, a_flat, wall, grade = probes(course, facts, (keys // 2) * BIN_M, np.where(keys % 2 == 1, 1.0, -1.0),
                                         grade_fn, elev_fn)
    p0, p1 = np.searchsorted(keys, k0), np.searchsorted(keys, k1)

    def lerp(v):
        return v[p0] + (v[p1] - v[p0]) * t
    zr, af, w, k = lerp(z_road), lerp(a_flat), lerp(wall), lerp(grade)
    x = ad - af
    g, nat = out[idx], base[idx]
    ok = ((w > 0) & (x > 0) & (x < REACH_M) & (nat > zr) &
          (g >= zr - OVER_TOL_M) & (g <= nat + OVER_TOL_M))
    if ok.any():
        new = bank(x[ok], zr[ok], nat[ok], k[ok])
        out[idx[ok]] = g[ok] + w[ok] * (new - g[ok])
    return out.reshape(shape)
