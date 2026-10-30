-- Turn-by-turn along a road route from the companion (OSRM steps): where the car is on the route, the next
-- maneuver and its distance, the one after it, the distance and time left, and when the car has left the route.
-- Pure apart from the anchor it is given (anchor:geodeticToEnu).
local poly = require('offroadCompanion/poly')

local M = {}

M.OFF_ROUTE_M = 60        -- farther from the route than this ...
M.OFF_ROUTE_S = 3         -- ... for this long: rerouted
M.ARRIVE_M = 30
M.THEN_M = 250            -- the maneuver after the next one is shown when it follows within this
M.PASSED_M = 8            -- a maneuver this close behind is done

local Nav = {}
Nav.__index = Nav

-- route: {points = {{lat, lon}...}, steps = {{text, icon, road, s, lat, lon, ...}}, dist, dur}
function M.new(route, dest)
  return setmetatable({ route = route, dest = dest, e = nil, s = nil, offSince = nil, arrived = false }, Nav)
end

function Nav:frame(anchor)
  if not self.e or self.e.anchor ~= anchor then
    self.e = poly.toFrame(anchor, self.route.points)
    -- maneuvers by s in this frame: the companion's s (geodesic) and ours (planar) differ by centimetres per km,
    -- so they are taken again here from the maneuver positions
    local prev = 0
    for _, st in ipairs(self.route.steps or {}) do
      local x, y = anchor:geodeticToEnu(st.lat, st.lon, 0)
      local i0 = math.max(1, poly.indexAt(self.e, prev) - 1)
      local _, _, _, s = poly.nearest(self.e, x, y, i0, self.e.n)
      st._s = math.max(prev, s)
      prev = st._s
    end
  end
  return self.e
end

-- One check: px, py (world frame), speed m/s, now (s). Returns the state table for the UI.
function Nav:update(anchor, px, py, now)
  local e = self:frame(anchor)
  local s, d = poly.follow(e, px, py, self.s)
  self.s = s
  local remaining = math.max(0, e.length - s)
  local out = { s = s, off = d, remaining = remaining + (d > M.OFF_ROUTE_M and d or 0), total = e.length }
  if self.route.dist and self.route.dist > 0 and self.route.dur then
    out.eta = self.route.dur * remaining / self.route.dist
  end
  -- off route for a while: the caller replans
  if d > M.OFF_ROUTE_M then
    self.offSince = self.offSince or now
    out.offRoute = (now - self.offSince) >= M.OFF_ROUTE_S
  else
    self.offSince = nil
  end
  -- arrived: near the end of the route, or at the destination itself
  local ex, ey = e.x[e.n], e.y[e.n]
  local toEnd = math.sqrt((ex - px) ^ 2 + (ey - py) ^ 2)
  if toEnd < M.ARRIVE_M or (remaining < M.ARRIVE_M and d < M.OFF_ROUTE_M) then
    self.arrived = true
  end
  out.arrived = self.arrived
  -- next maneuver: the first one still ahead (the departure only right at the start)
  local steps = self.route.steps or {}
  local nextI = nil
  for i, st in ipairs(steps) do
    if st.type ~= 'depart' or s < 15 then
      if st._s > s - M.PASSED_M then nextI = i; break end
    end
  end
  if nextI then
    local st = steps[nextI]
    out.next = { text = st.text, icon = st.icon, road = st.road, exit = st.exit, dist = math.max(0, st._s - s),
                 index = nextI, type = st.type }
    local th = steps[nextI + 1]
    if th and th._s - st._s <= M.THEN_M then
      out['then'] = { text = th.text, icon = th.icon, road = th.road, dist = th._s - st._s }
    end
    -- the road the car is on: the previous step's road
    local cur = steps[nextI - 1] or steps[1]
    out.road = cur and cur.road or ''
  end
  return out
end

-- The route ahead / behind for the minimap: {x, y} relative to (px, py), from s - back to s + ahead.
function Nav:mapLine(px, py, back, ahead, step)
  if not self.e or not self.s then return {} end
  local pts = poly.slice(self.e, self.s - back, self.s + ahead, step)
  local out = {}
  for i, p in ipairs(pts) do out[i] = { math.floor((p[1] - px) * 10 + 0.5) / 10, math.floor((p[2] - py) * 10 + 0.5) / 10 } end
  return out
end

return M
