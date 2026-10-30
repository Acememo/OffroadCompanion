"""Where along a course spectators gather (the user, 2026-10-25: "spectator models around the sections of the track
where it would make sense"), from the course's own ground: its jumps (the track terrain's kickers, relief.py) and where
it crosses a paved road (people park there and walk over). The game adds the start, the finish, the checkpoints, the
danger spots and the hairpins from the course file and its line (crowds.lua).

Pure Python (no numpy: the companion runs on any Python). hash01 is relief._hash bit for bit, and kicks() finds the
kickers relief._bin_features makes (tests/test_spots.py checks both), so the crowds stand at the jumps the ground has,
the same for everyone.
"""
import math

from . import courseroads

MASK = (1 << 64) - 1
C1, C2, C3 = 0x9E3779B97F4A7C15, 0xC2B2AE3D27D4EB4F, 0xBF58476D1CE4E5B9
# (relief.py's: kept equal there by tests/test_spots.py)
BIN_M = 170.0
P_FEATURE = 0.45
P_KICKER = 0.35
STEP = courseroads.STEP_M
CROSS_ROUGH = 0.2           # a paved crossing: the relief's dirt share dips under this ...
CROSS_MAX_N = 8             # ... for at most this many samples (a road across, not one along) ...
CROSS_DIRT = 0.6            # ... with dirt (this share) on both sides within CROSS_SIDE_N samples
CROSS_SIDE_N = 10


def hash01(a, b, salt):
    """Uniform [0, 1) from two integers and a salt: relief._hash exactly (uint64 arithmetic)."""
    a &= MASK
    b &= MASK
    x = ((a * C1) & MASK) ^ ((((b + salt) & MASK) * C2) & MASK)
    x ^= x >> 31
    x = (x * C3) & MASK
    x ^= x >> 29
    return (x >> 11) / float(1 << 53)


def _round(v):
    """numpy.round's integer (half to even), as relief quantizes a place."""
    return int(round(v))


def kicks(lat, lon, s0, s1, rock_at=None):
    """The kickers (jumps) of the course between s0 and s1 (m along it): [(s, size 0..1)]. lat / lon: the course's
    samples (courseroads.Course); rock_at(s) -> the rockiness there (none on rocky ground), None: 0."""
    n = len(lat)
    out = []
    if n == 0:
        return out
    for bb in range(int(math.floor(s0 / BIN_M)) - 1, int(math.floor(s1 / BIN_M)) + 2):
        mid = int((bb + 0.5) * BIN_M / STEP)
        mid = min(max(mid, 0), n - 1)
        qa, qo = _round(lat[mid] * 1e4), _round(lon[mid] * 1e4)
        if hash01(qa, qo, 21) >= P_FEATURE:
            continue
        pos = (bb + 0.2 + 0.6 * hash01(qa, qo, 22)) * BIN_M
        if not (s0 <= pos <= s1):
            continue
        if hash01(qa, qo, 23) >= P_KICKER:
            continue                                    # (a wash: a dip, nothing to watch)
        if rock_at is not None and rock_at(pos) >= 0.5:
            continue
        out.append((round(pos, 1), round(hash01(qa, qo, 24), 3)))
    return out


def crossings(rough, i0=0):
    """Where the course crosses a paved road: the samples' relief dirt share rough (from sample i0) dipping briefly
    between dirt on both sides. [s (m)]."""
    out = []
    n = len(rough)
    i = 0
    while i < n:
        v = rough[i]
        if v is None or v >= CROSS_ROUGH:
            i += 1
            continue
        j = i
        while j + 1 < n and rough[j + 1] is not None and rough[j + 1] < CROSS_ROUGH:
            j += 1
        if j - i + 1 <= CROSS_MAX_N:
            before = [r for r in rough[max(0, i - CROSS_SIDE_N):i] if r is not None]
            after = [r for r in rough[j + 1:j + 1 + CROSS_SIDE_N] if r is not None]
            if before and after and max(before) >= CROSS_DIRT and max(after) >= CROSS_DIRT:
                out.append(round((i0 + (i + j) / 2.0) * STEP, 1))
        i = j + 1
    return out
