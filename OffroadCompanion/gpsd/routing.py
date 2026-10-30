"""Turn-by-turn road routes: OSRM (FOSSGIS instance, OpenStreetMap data) with its maneuver steps.

BeamNG.Earth's own server already plans the route that the in-game arrows follow, but without the steps; this asks
OSRM the same question with steps=true so the app can say "In 300 m turn left onto Avenida Revolución". Same
instance, same bearing hint, so both routes are the same road.
"""
import math

from . import geo

OSRM_HOSTS = [
    "https://routing.openstreetmap.de/routed-car/route/v1/driving/",
    "https://router.project-osrm.org/route/v1/driving/",
]
BEARING_RANGE = 60
SIMPLIFY_M = 3.0
MAX_POINTS = 12000
ATTRIBUTION = "Routing: OSRM, data (c) OpenStreetMap contributors (ODbL)"


def url(base, lat0, lon0, lat1, lon1, bearing=None):
    u = (f"{base}{lon0:.6f},{lat0:.6f};{lon1:.6f},{lat1:.6f}"
         "?overview=full&geometries=geojson&steps=true&continue_straight=default")
    if bearing is not None:
        u += f"&bearings={int(bearing) % 360},{BEARING_RANGE};"
    return u


# -- instruction text ---------------------------------------------------------------------------------------------
_MOD = {
    "en": {"uturn": "Make a U-turn", "sharp right": "Sharp right", "right": "Turn right", "slight right": "Bear right",
           "straight": "Continue straight", "slight left": "Bear left", "left": "Turn left", "sharp left": "Sharp left"},
    "es": {"uturn": "Da vuelta en U", "sharp right": "Gira cerrado a la derecha", "right": "Gira a la derecha",
           "slight right": "Mantente a la derecha", "straight": "Sigue derecho", "slight left": "Mantente a la izquierda",
           "left": "Gira a la izquierda", "sharp left": "Gira cerrado a la izquierda"},
}
_WORDS = {
    "en": {"onto": "onto", "on": "on", "depart": "Head {dir}", "arrive": "Arrive at your destination",
           "arrive_side": "Your destination is on the {side}", "left": "left", "right": "right",
           "roundabout": "At the roundabout take exit {n}", "roundabout_any": "Enter the roundabout",
           "exit_round": "Exit the roundabout", "merge": "Merge", "on ramp": "Take the ramp",
           "off ramp": "Take the exit", "fork": "Keep {side} at the fork", "end of road": "At the end of the road {turn}",
           "continue": "Continue", "toward": "toward", "dirs": ["north", "northeast", "east", "southeast", "south",
                                                                 "southwest", "west", "northwest"]},
    "es": {"onto": "hacia", "on": "por", "depart": "Dirígete al {dir}", "arrive": "Llegaste a tu destino",
           "arrive_side": "Tu destino está a la {side}", "left": "izquierda", "right": "derecha",
           "roundabout": "En la glorieta toma la salida {n}", "roundabout_any": "Entra a la glorieta",
           "exit_round": "Sal de la glorieta", "merge": "Incorpórate", "on ramp": "Toma la rampa",
           "off ramp": "Toma la salida", "fork": "Mantente a la {side} en la bifurcación",
           "end of road": "Al final del camino {turn}", "continue": "Continúa", "toward": "hacia",
           "dirs": ["norte", "noreste", "este", "sureste", "sur", "suroeste", "oeste", "noroeste"]},
}


def road_label(step):
    name, ref = (step.get("name") or "").strip(), (step.get("ref") or "").strip()
    if name and ref and ref not in name:
        return f"{name} ({ref})"
    return name or ref


def icon_for(mtype, modifier):
    """A short icon key the UI draws (arrow shapes)."""
    if mtype in ("arrive",):
        return "arrive"
    if mtype in ("roundabout", "rotary", "roundabout turn", "exit roundabout", "exit rotary"):
        return "roundabout"
    if mtype == "depart":
        return "straight"
    return (modifier or "straight").replace(" ", "-")


def instruction(step, lang="en"):
    """One human sentence for an OSRM step. Pure."""
    lang = lang if lang in _WORDS else "en"
    W, MOD = _WORDS[lang], _MOD[lang]
    m = step.get("maneuver") or {}
    t, mod = m.get("type", "turn"), m.get("modifier")
    road = road_label(step)
    turn = MOD.get(mod or "straight", MOD["straight"])
    if t == "depart":
        b = m.get("bearing_after")
        d = W["dirs"][int(((b or 0) + 22.5) % 360 // 45)]
        s = W["depart"].format(dir=d)
        return f"{s} {W['on']} {road}" if road else s
    if t == "arrive":
        if mod in ("left", "right", "slight left", "slight right", "sharp left", "sharp right"):
            return W["arrive_side"].format(side=W["left"] if "left" in mod else W["right"])
        return W["arrive"]
    if t in ("roundabout", "rotary"):
        n = m.get("exit")
        s = W["roundabout"].format(n=n) if n else W["roundabout_any"]
        return f"{s} {W['onto']} {road}" if road else s
    if t in ("exit roundabout", "exit rotary"):
        return f"{W['exit_round']} {W['onto']} {road}" if road else W["exit_round"]
    if t == "fork":
        side = W["left"] if mod and "left" in mod else W["right"]
        s = W["fork"].format(side=side)
    elif t in ("on ramp", "off ramp", "merge"):
        s = W[t]
        dest = (step.get("destinations") or "").strip()
        if dest and not road:
            return f"{s} {W['toward']} {dest}"
    elif t == "end of road":
        s = W["end of road"].format(turn=turn[0].lower() + turn[1:])
    elif t in ("new name", "continue", "notification") and (mod in (None, "straight")):
        s = W["continue"]
    else:
        s = turn
    return f"{s} {W['onto']} {road}" if road else s


# -- parsing -------------------------------------------------------------------------------------------------------
def parse(data, lang="en"):
    """{points [[lat, lon]], dist, dur, steps [{text, icon, type, modifier, road, exit, lat, lon, i, s, dist}]}.
    i: index of the maneuver in points, s: metres along points. Raises ValueError."""
    if not isinstance(data, dict) or data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError(f"no route ({data.get('code') if isinstance(data, dict) else 'bad answer'})")
    r = data["routes"][0]
    raw = [(float(c[1]), float(c[0])) for c in r["geometry"]["coordinates"]]
    steps_raw = [st for leg in r.get("legs", []) for st in leg.get("steps", [])]
    # keep each maneuver's vertex through simplification
    pin = set()
    for st in steps_raw:
        loc = (st.get("maneuver") or {}).get("location")
        if loc:
            pin.add((round(float(loc[1]), 6), round(float(loc[0]), 6)))
    pts = _simplify_pinned(raw, pin, SIMPLIFY_M)
    tol = SIMPLIFY_M
    while len(pts) > MAX_POINTS:
        tol *= 2
        pts = _simplify_pinned(raw, pin, tol)
    cum = geo.cumulative(pts)
    steps, i_hint = [], 0
    for st in steps_raw:
        m = st.get("maneuver") or {}
        loc = m.get("location") or [pts[0][1], pts[0][0]]
        lat, lon = float(loc[1]), float(loc[0])
        s, _, i = geo.project(pts, cum, lat, lon, i_hint, min(len(pts) - 1, i_hint + 4000))
        i_hint = i
        steps.append({
            "text": instruction(st, lang), "icon": icon_for(m.get("type"), m.get("modifier")),
            "type": m.get("type"), "modifier": m.get("modifier"), "road": road_label(st), "exit": m.get("exit"),
            "lat": round(lat, 6), "lon": round(lon, 6), "i": i, "s": round(s, 1),
            "dist": float(st.get("distance") or 0), "dur": float(st.get("duration") or 0),
        })
    return {"points": [[round(a, 6), round(b, 6)] for a, b in pts], "dist": float(r.get("distance") or 0),
            "dur": float(r.get("duration") or 0), "steps": steps, "attribution": ATTRIBUTION}


def _simplify_pinned(points, pin, tol):
    """RDP that never drops a maneuver point: simplify each stretch between pinned vertices on its own."""
    if len(points) < 3:
        return list(points)
    cuts = [0] + [i for i in range(1, len(points) - 1)
                  if (round(points[i][0], 6), round(points[i][1], 6)) in pin] + [len(points) - 1]
    out = []
    for a, b in zip(cuts, cuts[1:]):
        part = geo.simplify(points[a:b + 1], tol)
        out.extend(part if not out else part[1:])
    return out


def plan(fetcher, lat0, lon0, lat1, lon1, bearing=None, lang="en"):
    """The route (blocking). Tries the bearing first (start on the carriageway the car is on), then without it,
    then the next host. Raises ValueError / fetch.FetchError (the last error)."""
    from .fetch import FetchError
    last = None
    for base in OSRM_HOSTS:
        for b in ([bearing, None] if bearing is not None else [None]):
            try:
                resp = fetcher.get(url(base, lat0, lon0, lat1, lon1, b), ttl=600)
                return parse(resp.json(), lang)
            except FetchError as e:
                last = e
                if e.status == 400 and b is not None:
                    continue          # no road that way near the start: try any direction
                break                 # host trouble: next host
            except ValueError as e:
                last = e
                if b is not None:
                    continue
                break
    raise last or ValueError("no route")


def bearing_deg(dx, dy):
    if dx * dx + dy * dy < 1e-6:
        return None
    return (math.degrees(math.atan2(dx, dy)) + 360) % 360
