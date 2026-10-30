"""The spectators' crowd sound (mod/offroad_companion/art/offroadcompanion/sound/crowd_<1..3>.ogg) from a seamless loop
of a crowd cheering and clapping: mglennsound's "AF Crowd Cheer Clapping LOOP.wav" on Freesound (CC0,
https://freesound.org/people/mglennsound/sounds/678542/; the user, 2026-10-30, in place of 1.4's Mixkit recording,
whose licence does not allow passing the sound files on by themselves: the project's repository is public).

Three loops from it (the user, 2026-10-25: "the spectator sound should loop"), so neighbouring crowds don't sound the
same: the whole loop, each started at another point of it (STARTS), so two played at once (a gate's) or side by side
are never in step. The recording's end runs into its start without a seam, and a turned loop keeps that. Mono (the
game places a mono sound in the world: 3D, louder near the crowd), the same loudness each.
Run: python3 tools/make_crowd_sounds.py <the loop .wav>      (needs ffmpeg with libvorbis, numpy)
(crowdsound.lua's LOOP_S is the loop's length: the printed one.)
"""
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "mod", "offroad_companion", "art", "offroadcompanion", "sound")
SR = 44100
STARTS = [0.0, 7.3, 14.6]             # s into the loop each of the three starts at
GAIN = 1.2                            # (the user, 2026-10-25: "spectator sound should be x1.2 louder")
TARGET_RMS_DB = -20.0 + 20 * np.log10(GAIN)
PEAK = 0.98                           # (a peak over this is limited)


def read_mono(src):
    raw = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", src, "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def level(x):
    rms = np.sqrt(np.mean(x ** 2))
    x = x * (10 ** (TARGET_RMS_DB / 20) / max(rms, 1e-9))
    pk = np.abs(x).max()
    if pk > PEAK:
        x = x * (PEAK / pk)
    return x


def main(src):
    os.makedirs(OUT, exist_ok=True)
    x = read_mono(src)
    x = level(x)                          # (one gain for all three: the same loudness)
    for k, t0 in enumerate(STARTS, 1):
        y = np.roll(x, -int(t0 * SR)).astype(np.float32)
        out = os.path.join(OUT, f"crowd_{k}.ogg")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1",
                        "-i", "-", "-c:a", "libvorbis", "-q:a", "4", out], input=y.tobytes(), check=True)
        print(out, os.path.getsize(out) // 1024, "KB")
    print(f"loop length {len(x) / SR:.3f} s (crowdsound.lua LOOP_S)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
