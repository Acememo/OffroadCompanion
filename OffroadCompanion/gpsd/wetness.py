"""How wet the ground is from the rain that fell (the user, 2026-10-28: "could you make realistically more slippery on
places that it's raining or rained recently? And mud/water puddles if it rained and the water could accumulate").

The rain of the last days at the place (Open-Meteo's hourly precipitation, the same weather service BeamNG.Earth's
real weather uses, keyless) is added up with the older rain counting less, as the ground dries: an antecedent
precipitation index with a drying time that follows the air (TAU_*: hot dry air dries the ground in hours, cool damp
air takes days). The ground's wetness w = 1 - exp(-index / SOAK_MM): 0 dry .. 1 soaked. The game makes the ground
slipperier with w and, from PUDDLE_W, fills the closed dips of the track with water (wet.lua).

Everyone near the same place at the same hour gets the same w: the place is taken on a GRID_DEG grid, the hour is the
UTC hour, and w is rounded to STEP. Pure apart from fetch().
"""
import math
import time

API = "https://api.open-meteo.com/v1/forecast"
GRID_DEG = 0.1              # the place, rounded to this (everyone within a few km asks the same)
PAST_DAYS = 3
TTL_S = 1800
SOAK_MM = 6.0               # index (mm) at which the ground is 63 % of the way to soaked
TAU_BASE_H = 30.0           # drying time (h) at 15 C and 60 % relative humidity
TAU_PER_C = 0.8             # ... shorter per degree warmer
TAU_PER_RH = 0.3            # ... longer per % more humid
TAU_H = (6.0, 60.0)
STEP = 0.05
PUDDLE_W = 0.55             # from here the track's dips hold water (the game's)
LEVELS = ((0.15, "dry"), (0.4, "damp"), (0.7, "wet"), (2.0, "soaked"))


def grid(lat, lon):
    return round(round(float(lat) / GRID_DEG) * GRID_DEG, 4), round(round(float(lon) / GRID_DEG) * GRID_DEG, 4)


def url(lat, lon):
    la, lo = grid(lat, lon)
    return (f"{API}?latitude={la}&longitude={lo}&hourly=precipitation,temperature_2m,relative_humidity_2m"
            f"&past_days={PAST_DAYS}&forecast_days=1&timezone=GMT&timeformat=unixtime")


def level(w):
    for top, name in LEVELS:
        if w < top:
            return name
    return LEVELS[-1][1]


def model(times, precip, temp, rh, now):
    """{w, level, index (mm), tau (h), rainMmH (the last hour's), last24 (mm)} from Open-Meteo's hourly series (each
    value: the hour ending at its time) up to the UTC hour of now. Pure."""
    now_h = math.floor(float(now) / 3600.0) * 3600.0
    rows = [(float(t), float(p or 0.0), t_, h_) for t, p, t_, h_ in zip(times, precip, temp, rh)
            if t is not None and float(t) <= now_h]
    if not rows:
        return {"w": 0.0, "level": "dry", "index": 0.0, "tau": TAU_BASE_H, "rainMmH": 0.0, "last24": 0.0}
    day = [r for r in rows if now_h - r[0] < 24 * 3600]
    ts = [float(r[2]) for r in day if r[2] is not None]
    hs = [float(r[3]) for r in day if r[3] is not None]
    t_avg = sum(ts) / len(ts) if ts else 15.0
    h_avg = sum(hs) / len(hs) if hs else 60.0
    tau = TAU_BASE_H - TAU_PER_C * (t_avg - 15.0) + TAU_PER_RH * (h_avg - 60.0)
    tau = min(TAU_H[1], max(TAU_H[0], tau))
    index = sum(max(0.0, p) * math.exp(-(now_h - t) / 3600.0 / tau) for t, p, _, _ in rows)
    w = 1.0 - math.exp(-index / SOAK_MM)
    w = round(round(w / STEP) * STEP, 2)
    last = max(rows, key=lambda r: r[0])
    return {"w": w, "level": level(w), "index": round(index, 2), "tau": round(tau, 1),
            "rainMmH": round(last[1] if now_h - last[0] < 3600 * 1.5 else 0.0, 2),
            "last24": round(sum(r[1] for r in day), 1)}


def fetch(fetcher, lat, lon, now=None):
    """The ground's wetness at (lat, lon) now (model's dict, with the place it was read for). Raises FetchError."""
    now = time.time() if now is None else now
    data = fetcher.get(url(lat, lon), ttl=TTL_S, accept="application/json").json()
    h = data.get("hourly") or {}
    out = model(h.get("time") or [], h.get("precipitation") or [], h.get("temperature_2m") or [],
                h.get("relative_humidity_2m") or [], now)
    out["lat"], out["lon"] = grid(lat, lon)
    out["hour"] = int(math.floor(now / 3600.0))
    return out
