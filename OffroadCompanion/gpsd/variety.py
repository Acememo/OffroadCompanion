"""The track's sections (terrain 7; the user, 2026-11-01: "can we add gravel and rock sections where they would be irl?
and some sandy parts should be like those sand traps that you see on baja. Basically, add more track variety but it
should always make sense like on irl baja. Also in some "danger" parts there should be on some of them rock crawling
parts when the tracks goes through canyons").

Along a course the track changes with the ground it crosses, the way a Baja course does. Each kind of section comes
only where the place has it (the course's relief facts: relief.window_profile, surfaces.window_facts), and where it
may come, a hash of the course's place decides, stretch by stretch, whether it does (relief._sections: the same for
everyone, eased in and out over a stretch):

    sand traps      deep soft sand where a dry wash crosses or runs along the course, on a desert canyon's floor and
                    by the sea, now and then on open sandy desert: the track sunk into it, churned, the sand thrown up
                    beside it, all sand (no drawn dirt track: the sand itself)
    rock sections   rocky ground in canyons and on rocky hillsides: the track over rock, its ledges and lumps
                    stronger, more boulders beside it; never in a wash or on a lake
    gravel          the alluvial fans at the foot of the mountains (a desert track climbing or falling a steady 2.5-12 %
                    grade), the creek beds of green country, broken ground on the way into the rocks, dirt roads in the
                    hills: gravel underfoot, the track a little smoother, a low windrow of gravel at its edges
    rock crawls     (Auto only, where the course's DANGER waypoints count) some DANGER waypoints in a canyon: the
                    track a staircase of tilted rock shelves for 70-160 m, boulders in it with a weaving line between
                    them, all rock. The waypoint's own ditch or kicker gives way to it.

Nothing on asphalt (the relief's own rule), and the sections keep to their order: a sand trap wins over rock, rock
over gravel. The heights are the relief's (scaled by the track terrain setting, none on Flat), the surfaces the
ground's (surfaces.course_surfaces: whatever the setting). Pure numpy.
"""
import math

import numpy as np

from . import relief as rf

VARIETY_TV = 7
# sand traps
SAND_BIN_M, SAND_SALT = 130.0, 61
SAND_P = (0.65, 0.45, 0.3)  # the chance of a stretch where a dry wash crosses or runs along it, by the sea, on a
#                             desert canyon's floor (its walls may be rock instead)
SAND_OPEN_P = 0.08          # ... on open, flat, bare desert
SAND_SINK, SAND_BERM, SAND_CHURN = 0.24, 0.24, 0.13     # m (at most: not past Rough): the track sunk, the sand
#                                                         thrown beside it, its churn
SAND_BERM_AT = (2.6, 2.6)   # the thrown sand's middle past the edge, its width (Gaussian)
SAND_FLOOR_IN = (2.0, 4.5)  # the sunk floor full to this far inside the edge, easing up over this
SAND_RUTS = 0.7             # the rutted sections' heights this much lower in a sand trap (the drawn ruts stay)
SAND_CHURN_M = 9.0          # the churned floor's swells (one octave: ~3 cells of the 2 m lattice and more)
SAND_REACH_M = 2.5          # the sand reaches this far past the track's edge
# rock sections
ROCK_BIN_M, ROCK_SALT = 150.0, 63
ROCK_P = 0.7
ROCK_FROM = (0.45, 0.8)     # the rock fact (canyon walls, rocky hillside): none .. full chance
ROCK_LEDGE, ROCK_LEDGE_M = 0.28, 20.0       # m: the extra ledges' height, the noise's size
ROCK_BUMP, ROCK_BUMP_M = 0.10, 12.0         # m: the rocky lumps
ROCK_WHOOPS = 0.7           # the whoops this much lower on rock
ROCK_EDGE_M = 1.5           # loose gravel this far past the edge of a rock section
ROCK_BOULDER_P = 0.35       # boulders beside the track: at least this chance per slot in a rock section
# gravel
GRAVEL_BIN_M, GRAVEL_SALT = 180.0, 65
GRAVEL_P = 0.6
FAN_GRADE = (0.025, 0.05, 0.12, 0.18)      # the fan's grade: from .. full .. full to .. none (steeper: a mountain)
GRAVEL_WHOOPS = 0.35
GRAVEL_EDGE = 0.07          # m: the windrow of gravel at the edges
GRAVEL_REACH_M = 1.0
# rock crawls
CRAWL_P = 0.7               # a DANGER waypoint's chance of being a crawl (where it is in a canyon)
CRAWL_BEFORE = (35.0, 30.0)  # m before the waypoint: base + size x this
CRAWL_AFTER = (45.0, 40.0)
CRAWL_EASE_M = 15.0
CRAWL_CANYON = (0.35, 0.6)  # the canyon fact from which it is a crawl (or the rock fact's, a little later)
CRAWL_CELL_M, CRAWL_RAMP = 6.5, 0.5     # a shelf every CRAWL_CELL_M, the step between two over this share of it
CRAWL_STEP = 0.42           # m: a shelf's height, up or down from the ground's mean
CRAWL_TILT = 0.09           # m per m: a shelf's tilt across the track
CRAWL_SKEW = 0.3
CRAWL_PAST_M, CRAWL_FADE_M = 1.0, 3.0   # the shelves this far past the edge, fading over this
CRAWL_FLATTEN = 0.8         # the track's own relief this much lower in a crawl
CRAWL_REACH_M = 3.0         # rock this far past the edge
CRAWL_LANE = (0.45, 55.0, 1.6)      # the line between the boulders: weaving this share of the half width, once per
#                                   this many m, this wide each side of its middle
CRAWL_ROCK_SLOTS, CRAWL_SIDE_SLOTS = 4, 4
BARE_W = 0.5                # sections from this weight on are drawn as the ground itself (no dirt track decal)


def _desert(f):
    return rf._ramp(f["arid"], 0.35, 0.6)


def weights(course, s, f):
    """(sand, rock, gravel): 0 .. 1 per point (s along the course, f the facts there: relief._Facts.at), each
    section's weight after the order (sand over rock over gravel); zeros before VARIETY_TV. Pure."""
    s = np.asarray(s, np.float64)
    z = np.zeros(len(s))
    if getattr(course, "tv", 1) < VARIETY_TV or not len(s):
        return z, z.copy(), z.copy()
    desert = _desert(f)
    rock = f["rock"]
    nolake = 1.0 - rf._ramp(f["lake"], 0.2, 0.5)
    wash, sea = f["washn"], f["sean"]
    flat = 1.0 - rf._ramp(f["grade"], 0.03, 0.07)
    floor = desert * rf._ramp(f["canyon"], 0.5, 0.8)
    plain = np.maximum(np.maximum(SAND_P[0] * wash * desert, SAND_P[1] * sea), SAND_P[2] * floor)
    p_sand = plain + SAND_OPEN_P * desert * (1.0 - f["cover"]) * flat * (1.0 - rock)
    p_sand = p_sand * nolake * (1.0 - 0.85 * f["road"]) * (1.0 - rf._ramp(rock, 0.35, 0.6) * (1.0 - floor))
    p_rock = ROCK_P * rf._ramp(rock, *ROCK_FROM) * (1.0 - np.maximum(wash, sea)) * nolake * (1.0 - 0.4 * f["road"])
    g = f["grade"]
    fan = desert * rf._ramp(g, FAN_GRADE[0], FAN_GRADE[1]) * (1.0 - rf._ramp(g, FAN_GRADE[2], FAN_GRADE[3]))
    creek = (1.0 - desert) * wash
    broken = rf._ramp(rock, 0.2, 0.4) * (1.0 - rf._ramp(rock, 0.55, 0.75))
    hills = f["road"] * rf._ramp(rock, 0.15, 0.45)
    p_gravel = GRAVEL_P * np.maximum(np.maximum(fan, creek), np.maximum(broken, hills)) * nolake * (1.0 - sea)
    w_sand = rf._sections(course, s, p_sand, SAND_BIN_M, SAND_SALT)
    r = rf._sections(course, s, p_rock, ROCK_BIN_M, ROCK_SALT)
    g = rf._sections(course, s, p_gravel, GRAVEL_BIN_M, GRAVEL_SALT)
    return w_sand, r * (1.0 - w_sand), g * (1.0 - w_sand) * (1.0 - r)


def crawls(course):
    """The DANGER waypoints that are rock crawls where they are in a canyon: [(s, size)] (course_auto's)."""
    if getattr(course, "tv", 1) < VARIETY_TV:
        return []
    return rf.course_auto(course).get("crawl") or []


def crawl_weight(course, s, f):
    """0 .. 1 per point: how fully it is in a rock crawl (Auto: the course's crawls, crawls(); in a canyon). Pure."""
    s = np.asarray(s, np.float64)
    out = np.zeros(len(s))
    cs = crawls(course)
    if not cs or not len(s):
        return out
    for sd, size in cs:
        b = CRAWL_BEFORE[0] + CRAWL_BEFORE[1] * size
        a = CRAWL_AFTER[0] + CRAWL_AFTER[1] * size
        w = rf._ramp(s, sd - b - CRAWL_EASE_M, sd - b) * (1.0 - rf._ramp(s, sd + a, sd + a + CRAWL_EASE_M))
        out = np.maximum(out, w)
    if not out.any():
        return out
    canyon = np.maximum(rf._ramp(f["canyon"], *CRAWL_CANYON), rf._ramp(f["rock"], 0.5, 0.75))
    return out * canyon


def crawl_dz(s, d, ad, hw, gx, gy):
    """A rock crawl's ground (before its weight): a staircase of shelves along the track, each tilted across it, the
    steps a little diagonal; easing out past the edges. Every step over at least ~3 m (the 2 m lattice). Pure."""
    skew = CRAWL_SKEW * (2.0 * rf.vnoise(gx / rf.SKEW_M, gy / rf.SKEW_M, 85) - 1.0)
    u = (np.asarray(s, np.float64) + d * skew) / CRAWL_CELL_M
    k = np.floor(u).astype(np.int64)
    t = rf._smooth((u - k - (1.0 - CRAWL_RAMP)) / CRAWL_RAMP)

    def lv(kk, salt, amp):
        return (2.0 * rf._hash(kk, np.zeros_like(kk), salt) - 1.0) * amp
    lev = lv(k, 81, CRAWL_STEP) + (lv(k + 1, 81, CRAWL_STEP) - lv(k, 81, CRAWL_STEP)) * t
    tilt = lv(k, 82, CRAWL_TILT) + (lv(k + 1, 82, CRAWL_TILT) - lv(k, 82, CRAWL_TILT)) * t
    on = 1.0 - rf._smooth((ad - hw - CRAWL_PAST_M) / CRAWL_FADE_M)
    return (lev + tilt * np.clip(d, -hw, hw)) * on


def crawl_lane(s, hw):
    """The middle of the line kept clear between a crawl's boulders, m left of the track's middle. Pure."""
    return CRAWL_LANE[0] * hw * np.sin(2.0 * np.pi * np.asarray(s, np.float64) / CRAWL_LANE[1] + 0.7)


def bare(course, profiles, s):
    """Per s (m along the course, on the track's middle): True where the track is drawn as the ground itself (a sand
    trap, a rock section, a crawl: no dirt track decal); None when a window there is not planned (decide later). Pure
    given the profiles."""
    s = np.asarray(s, np.float64)
    if getattr(course, "tv", 1) < VARIETY_TV:
        return np.zeros(len(s), bool)
    have = rf._Facts(profiles) if profiles else None
    if have is None:
        return None
    k = np.floor(s / rf.STEP).astype(np.int64)
    if (k < have.lo).any() or (k > have.hi).any():
        return None
    f = have.at(s)
    ws, wr, _ = weights(course, s, f)
    auto = getattr(course, "rough", "on") == "auto"
    wc = crawl_weight(course, s, f) if auto else np.zeros(len(s))
    return np.maximum(np.maximum(ws, wr), wc) >= BARE_W


def split_bare(course, profiles, ps):
    """The pieces ps (courseroads.window_pieces) cut where a stretch is drawn as the ground itself (bare()): each run a
    piece of its own, its "surface" "rock" (BeamNG.Earth then draws no decal there: its terrain_surface) or "dirt";
    (pieces, complete): complete False when a window was missing (all dirt, decided again later). Pure."""
    if getattr(course, "tv", 1) < VARIETY_TV or not ps:
        return ps, True
    out, complete = [], True
    for p in ps:
        n = len(p.get("ll") or ())
        if "i0" not in p or n < 2:
            out.append(p)
            continue
        s = (int(p["i0"]) + np.arange(n)) * rf.STEP
        b = bare(course, profiles, s)
        if b is None:
            complete = False
            out.append(p)
            continue
        if not b.any():
            out.append(p)
            continue
        if b.all():
            out.append({**p, "surface": "rock"})
            continue
        r, i = 0, 0
        while i < n - 1:
            j = i
            while j + 1 < n - 1 and b[j + 1] == b[i]:
                j += 1
            e = j + 1                           # (runs share their end point)
            q = {"id": f"{p['id']}{r:02d}", "w": p["w"], "i0": int(p["i0"]) + i,
                 "ll": p["ll"][i:e + 1], "surface": "rock" if b[i] else "dirt"}
            for key in ("z", "off"):
                if p.get(key) is not None:
                    q[key] = p[key][i:e + 1]
            out.append(q)
            r += 1
            i = e
    return out, complete


def crawl_rocks(course, p, i, j, la0, lo0, la1, lo1, w_crawl):
    """The boulders of a crawl along sample i (profile p's j): in the track off the weaving line, and a wall of bigger
    ones beside it: [(salt, side, offset from the middle, size, along 0..1)]. Pure."""
    out = []
    if w_crawl < 0.4:
        return out
    hw = p["hw"][j]
    qa, qo = int(round(la0 * 1e5)), int(round(lo0 * 1e5))
    h = lambda salt: float(rf._hash(qa, qo, salt))     # noqa: E731
    for slot in range(CRAWL_ROCK_SLOTS):
        if h(500 + slot) >= 0.75 * w_crawl:
            continue
        t = h(520 + slot)
        o = (2.0 * h(540 + slot) - 1.0) * (hw + 0.8)
        lane = float(crawl_lane((i + t) * rf.STEP, hw))
        if abs(o - lane) < CRAWL_LANE[2]:
            continue
        out.append((500 + slot, 1.0 if o >= 0 else -1.0, abs(o), 0.3 + 0.4 * h(560 + slot), t))
    for slot in range(CRAWL_SIDE_SLOTS):
        if h(600 + slot) >= 0.6 * w_crawl:
            continue
        o = hw + 1.0 + 4.0 * h(620 + slot)
        out.append((600 + slot, 1.0 if slot % 2 == 0 else -1.0, o, 0.6 + 1.0 * h(640 + slot), h(660 + slot)))
    return out
