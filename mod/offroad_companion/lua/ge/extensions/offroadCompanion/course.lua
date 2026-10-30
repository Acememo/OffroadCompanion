-- Guidance through a race course (a track from the companion: a course line and/or waypoints).
--
-- With a line: where the car is along it (metres and race mile), how far off it and which way back, wrong way, the
-- next corner as a rally-style call ("Right 3 in 120 m", from the line's curvature), the next checkpoints, VCPs,
-- hazards and speed zones, the speed limit inside a zone, VCPs / checkpoints judged as hit or missed, and timing:
-- laps on a closed circuit, start to finish on an open course.
-- Waypoints only (a course given as places in race order): the next waypoint's distance and bearing, reached
-- within REACH_M, then the one after.
-- Pure apart from the anchor it is given (anchor:geodeticToEnu).
local poly = require('offroadCompanion/poly')
local fmt = require('offroadCompanion/fmt')

local M = {}

M.NEAR_LINE_M = 400        -- waypoints farther than this from the line are map markers only
M.OFF_M = 40               -- off course beyond this
M.VCP_RADIUS_M = 75        -- a VCP counts when the car passes this close
M.CP_RADIUS_M = 120
M.JUDGE_M = 120            -- a VCP is judged once the car is this far past it along the course
M.REACH_M = 60             -- waypoint courses: reached this close
M.AHEAD_M = 5000           -- the "coming up" list looks this far
M.CORNER_AHEAD_M = 400
M.CORNER_EVERY_S = 0.4
M.ZONE_AHEAD_M = 600
M.DANGER_AHEAD_M = 500
M.TIMING_OFF_M = 60
M.WRONG_WAY_DEG = 115
M.EVENT_S = 4.5

local CALLOUT = { checkpoint = true, vcp = true, danger = true, speed_start = true, speed_end = true, start = true,
                  finish = true, pit = true }

local C = {}
C.__index = C

local function hypot(x, y) return math.sqrt(x * x + y * y) end

-- Haversine metres (the course's s is measured on the Earth, like the companion's, so race-mile anchors and
-- waypoint positions along it agree over a 1000-mile course).
local function geod(lat1, lon1, lat2, lon2)
  local r = math.rad
  local p1, p2 = r(lat1), r(lat2)
  local a = math.sin((p2 - p1) / 2) ^ 2 + math.cos(p1) * math.cos(p2) * math.sin(r(lon2 - lon1) / 2) ^ 2
  return 2 * 6371008.8 * math.asin(math.min(1, math.sqrt(a)))
end

function M.new(track, opts)
  local self = setmetatable({ track = track, opts = opts or {}, e = nil, s = nil, off = nil, events = {},
                              judged = {}, minDist = {}, target = 1, laps = {}, lap = 0 }, C)
  self.hasLine = track.points and #track.points >= 2
  self.closed = track.closed and self.hasLine
  -- geodesic cumulative distance of the line, once
  if self.hasLine then
    local cum = { 0 }
    local p = track.points
    for i = 2, #p do cum[i] = cum[i - 1] + geod(p[i - 1][1], p[i - 1][2], p[i][1], p[i][2]) end
    self.gcum = cum
    self.length = cum[#cum]
  else
    self.length = track.length or 0
  end
  return self
end

function C:frame(anchor)
  if self.e and self.e.anchor == anchor then return self.e end
  if self.hasLine then
    local e = poly.toFrame(anchor, self.track.points)
    e.cum, e.length = self.gcum, self.length
    self.e = e
    -- a closed circuit: two laps end to end for everything that looks ahead (corner calls, the ribbon, the
    -- minimap) so they carry on over the start / finish line
    if self.closed then
      local p, n = self.track.points, #self.track.points
      local x2, y2, c2 = {}, {}, {}
      for i = 1, n do x2[i], y2[i], c2[i] = e.x[i], e.y[i], e.cum[i] end
      for i = 2, n do
        x2[n + i - 1], y2[n + i - 1], c2[n + i - 1] = e.x[i], e.y[i], self.length + e.cum[i]
      end
      self.ahead = { x = x2, y = y2, cum = c2, n = #x2, length = c2[#c2], anchor = anchor }
    else
      self.ahead = e
    end
  else
    self.e = { anchor = anchor, n = 0 }
  end
  for _, w in ipairs(self.track.waypoints or {}) do
    w._x, w._y = anchor:geodeticToEnu(w.lat, w.lon, 0)
  end
  return self.e
end

function C:event(text, level, now)
  table.insert(self.events, 1, { text = text, level = level or 'info', t = now })
  while #self.events > 4 do table.remove(self.events) end
end

function C:recentEvents(now)
  local out = {}
  for _, ev in ipairs(self.events) do
    if now - ev.t <= M.EVENT_S then out[#out + 1] = { text = ev.text, level = ev.level } end
  end
  return out
end

-- Where along the line (follow + the wrap past the line's end on a closed circuit).
function C:locate(e, px, py)
  local s, d = poly.follow(e, px, py, self.s)
  if self.closed and self.s and self.s > self.length - 300 then
    local s2, d2 = poly.follow(e, px, py, 0)
    if s2 < 300 and d2 < d then return s2, d2, true end
  end
  return s, d, false
end

-- The relative way to (tx, ty) from the car heading `heading` (deg): 'ahead' | 'left' | 'right' | 'behind'.
local function relative(px, py, heading, tx, ty)
  if not heading then return nil end
  local b = poly.bearing(tx - px, ty - py)
  local a = poly.angleDiff(heading, b)
  if math.abs(a) <= 30 then return 'ahead' end
  if math.abs(a) >= 150 then return 'behind' end
  return a > 0 and 'right' or 'left'
end

function C:updateLine(e, px, py, heading, speed, now, lang, imperial)
  local prevS = self.s
  local s, d, wrapped = self:locate(e, px, py)
  self.s, self.off = s, d
  local tr = self.track
  local out = { s = s, off = d, length = self.length, progress = self.length > 0 and s / self.length or 0 }
  out.rm = poly.raceMile(tr.rm, s)
  local _, _, tdx, tdy = poly.at(e, s)
  out.courseBearing = poly.bearing(tdx, tdy)
  if heading and speed and speed > 2 and d < 80 then
    out.wrongWay = math.abs(poly.angleDiff(heading, out.courseBearing)) > M.WRONG_WAY_DEG
  end
  -- off course: which way back
  if d > M.OFF_M then
    local cx, cy = poly.at(e, s)
    local rel = relative(px, py, heading, cx, cy) or poly.side(e, s, px, py)
    out.offCourse = { dist = d, dir = rel, bearing = poly.bearing(cx - px, cy - py) }
    out.offText = fmt.t(lang, 'offCourse', fmt.dist(d, imperial),
      rel == 'left' and fmt.t(lang, 'yourLeft') or rel == 'right' and fmt.t(lang, 'yourRight') or rel)
    self.wasOff = true
  elseif self.wasOff then
    self.wasOff = false
    self:event(fmt.t(lang, 'backOn'), 'good', now)
  end
  -- the stretch the car covered since the last check (a jump > 500 m is a teleport or a reacquire: not a pass)
  local moved = prevS and (wrapped and (self.length - prevS + s) or (s - prevS)) or 0
  local continuous = prevS and math.abs(moved) < 500 and d < M.TIMING_OFF_M

  -- waypoints: callouts ahead, VCP / checkpoint judging
  local ahead, nextRm = {}, nil
  for i, w in ipairs(tr.waypoints or {}) do
    if (w.off or 0) <= M.NEAR_LINE_M then
      local ds = w.s - s
      if wrapped or (self.closed and ds < -self.length / 2) then ds = ds + self.length end
      if (w.kind == 'vcp' or w.kind == 'checkpoint') and not self.judged[i] and w._x then
        if math.abs(ds) <= M.JUDGE_M then
          local dd = hypot(w._x - px, w._y - py)
          if not self.minDist[i] or dd < self.minDist[i] then self.minDist[i] = dd end
        elseif ds < -M.JUDGE_M and self.minDist[i] then
          local r = w.kind == 'vcp' and M.VCP_RADIUS_M or M.CP_RADIUS_M
          local hit = self.minDist[i] <= r
          self.judged[i] = hit and 'hit' or 'miss'
          if hit then
            self:event(fmt.t(lang, w.kind == 'vcp' and 'vcpHit' or 'cpHit', w.name), 'good', now)
          else
            self:event(fmt.t(lang, 'vcpMiss', w.name), 'bad', now)
          end
        end
      end
      if ds > 0 and ds <= M.AHEAD_M then
        if CALLOUT[w.kind] and #ahead < 4 then
          ahead[#ahead + 1] = { name = w.name, kind = w.kind, dist = ds, limit = w.limit }
        elseif w.kind == 'racemile' and not nextRm then
          nextRm = { name = w.name, dist = ds }
        end
      end
    end
  end
  out.ahead, out.nextRm = ahead, nextRm
  local danger = nil
  for _, a in ipairs(ahead) do
    if a.kind == 'danger' and a.dist <= M.DANGER_AHEAD_M then danger = a; break end
  end
  out.danger = danger
  -- speed zones
  for _, z in ipairs(tr.zones or {}) do
    if s >= z.s0 and s <= z.s1 then
      out.zone = { name = z.name, limit = z.limit, toEnd = z.s1 - s }
      if z.limit and speed and speed * 3.6 > z.limit + 3 then
        out.zone.speeding = true
        if not self.lastSpeeding or now - self.lastSpeeding > 6 then
          self.lastSpeeding = now
          self:event(fmt.t(lang, 'slowDown') .. ' (' .. fmt.limit(z.limit, imperial) .. ')', 'bad', now)
        end
      end
    elseif z.s0 > s and z.s0 - s <= M.ZONE_AHEAD_M and not out.zoneAhead then
      out.zoneAhead = { name = z.name, limit = z.limit, dist = z.s0 - s }
    end
  end
  -- corner calls (not on a rough line made of race-mile markers)
  if not tr.approximate then
    if not self.cornersAt or now - self.cornersAt >= M.CORNER_EVERY_S or math.abs(s - (self.cornersS or s)) > 60 then
      self.cornersAt, self.cornersS = now, s
      self.cornerList = poly.corners(self.ahead or e, s, M.CORNER_AHEAD_M)
    end
    local list = self.cornerList or {}
    local c1 = nil
    for k, c in ipairs(list) do
      if c.s1 > s + 2 then c1 = k; break end
    end
    if c1 then
      local c = list[c1]
      local call = { text = fmt.corner(lang, c), dir = c.dir, grade = c.grade, dist = math.max(0, c.s0 - s),
                     angle = c.angle }
      local c2 = list[c1 + 1]
      if c2 and c2.s0 - c.s1 <= 40 then call.into = fmt.corner(lang, c2) end
      out.corner = call
    end
  end
  -- timing
  if self.closed then
    if continuous and wrapped then
      if self.lapStart then
        self.lap = self.lap + 1
        local t = now - self.lapStart
        self.laps[#self.laps + 1] = t
        local best = self.best == nil or t < self.best
        if best then self.best = t end
        self:event(fmt.t(lang, 'lap', self.lap, fmt.laptime(t)) .. (best and (' · ' .. fmt.t(lang, 'bestLap')) or ''),
          'good', now)
      else
        self:event(fmt.t(lang, 'startTimer'), 'info', now)
      end
      self.lapStart = now
    end
    out.timing = { mode = 'laps', lap = self.lap + 1, current = self.lapStart and (now - self.lapStart) or nil,
                   last = self.laps[#self.laps], best = self.best }
  else
    if not self.startTime and continuous and prevS and prevS <= 40 and s > 40 then
      self.startTime = now
      self:event(fmt.t(lang, 'startTimer'), 'info', now)
    end
    if self.startTime and not self.finishTime and s >= self.length - 25 and d < M.TIMING_OFF_M then
      self.finishTime = now
      self:event(fmt.t(lang, 'finished', fmt.laptime(now - self.startTime)), 'good', now)
    end
    out.timing = { mode = 'stage', elapsed = self.startTime and ((self.finishTime or now) - self.startTime) or nil,
                   finished = self.finishTime ~= nil }
  end
  local hits, misses = 0, 0
  for _, v in pairs(self.judged) do if v == 'hit' then hits = hits + 1 else misses = misses + 1 end end
  out.vcp = { hit = hits, miss = misses }
  return out
end

function C:updateWaypoints(px, py, heading, now, lang, imperial)
  local wps = self.track.waypoints or {}
  local out = { waypoints = true, total = #wps }
  while self.target <= #wps do
    local w = wps[self.target]
    local d = hypot(w._x - px, w._y - py)
    if d > M.REACH_M then break end
    self:event(fmt.t(lang, 'reached', w.name), 'good', now)
    self.target = self.target + 1
  end
  if self.target > #wps then
    out.finished = true
    return out
  end
  local w = wps[self.target]
  local d = hypot(w._x - px, w._y - py)
  local rest = 0
  for k = self.target + 1, #wps do rest = rest + geod(wps[k - 1].lat, wps[k - 1].lon, wps[k].lat, wps[k].lon) end
  out.target = { index = self.target, name = w.name, kind = w.kind, dist = d, lat = w.lat, lon = w.lon,
                 bearing = poly.bearing(w._x - px, w._y - py), dir = relative(px, py, heading, w._x, w._y) }
  out.remaining = d + rest
  local nx = wps[self.target + 1]
  if nx then out.after = { name = nx.name } end
  return out
end

-- One check. Returns the state for the UI.
function C:update(anchor, px, py, heading, speed, now, lang, imperial)
  local e = self:frame(anchor)
  local out
  if self.hasLine then
    out = self:updateLine(e, px, py, heading, speed, now, lang, imperial)
  else
    out = self:updateWaypoints(px, py, heading, now, lang, imperial)
  end
  out.events = self:recentEvents(now)
  return out
end

-- Skip to the next waypoint (waypoint courses) / restart timing and judging.
function C:skip() if not self.hasLine then self.target = self.target + 1 end end
function C:restart()
  self.judged, self.minDist, self.target, self.laps, self.lap = {}, {}, 1, {}, 0
  self.lapStart, self.best, self.startTime, self.finishTime, self.s = nil, nil, nil, nil, nil
end

-- The start (first point / first waypoint) and the current target as lat / lon.
function C:startLatLon()
  local t = self.track
  if self.hasLine then return t.points[1][1], t.points[1][2] end
  local w = t.waypoints and t.waypoints[1]
  if w then return w.lat, w.lon end
end
function C:targetLatLon()
  if self.hasLine then
    -- the nearest course point ahead of the car (or the start before it is on the course)
    if not self.s or not self.e or not self.e.x then return self:startLatLon() end
    local i = poly.indexAt(self.e, self.s + 50)
    local p = self.track.points[i]
    return p[1], p[2]
  end
  local w = self.track.waypoints[self.target]
  if w then return w.lat, w.lon, w.name end
end

-- The whole course for the map's overview (sent once per course and anchor): the line every length / maxPts m as
-- x, y pairs relative to its first point (ox, oy in the anchor's frame), and its checkpoints {x, y, kind}.
function C:overview(maxPts)
  local e = self.e
  if not e or not e.n or e.n < 1 then return nil end
  local ox, oy = e.x[1], e.y[1]
  local function r(v) return math.floor(v + 0.5) end
  local pts, step = {}, 0
  if self.hasLine and e.n >= 2 then
    step = math.max(10, e.length / (maxPts or 1500))
    for _, p in ipairs(poly.slice(e, 0, e.length, step)) do
      pts[#pts + 1] = r(p[1] - ox)
      pts[#pts + 1] = r(p[2] - oy)
    end
  else
    for _, w in ipairs(self.track.waypoints or {}) do
      if w._x then pts[#pts + 1] = r(w._x - ox); pts[#pts + 1] = r(w._y - oy) end
    end
  end
  local wps = {}
  for _, w in ipairs(self.track.waypoints or {}) do
    if w._x and w.kind ~= 'racemile' and w.kind ~= 'place' then
      -- x, y, kind, name, distance along the course (-1: off it) for the overview's labels and passed ones
      wps[#wps + 1] = { r(w._x - ox), r(w._y - oy), w.kind, tostring(w.name or ''), w.s and r(w.s) or -1 }
    end
  end
  return { pts = pts, wps = wps, step = step, ox = ox, oy = oy, closed = self.track.closed and true or false }
end

-- For the minimap: the line from s - back to s + ahead and the waypoints near, relative to (px, py).
function C:mapData(px, py, radius)
  local out = { line = {}, wps = {} }
  local e = self.e
  if not e then return out end
  local r1 = function(v) return math.floor(v * 10 + 0.5) / 10 end
  if self.hasLine and self.s then
    local pts = poly.slice(self.ahead or e, self.s - radius, self.s + radius * 1.5, math.max(8, radius / 60))
    for i, p in ipairs(pts) do out.line[i] = { r1(p[1] - px), r1(p[2] - py), p[3] < self.s and 1 or 0 } end
  elseif not self.hasLine then
    for i, w in ipairs(self.track.waypoints or {}) do
      if w._x then out.line[#out.line + 1] = { r1(w._x - px), r1(w._y - py), i < self.target and 1 or 0 } end
    end
  end
  for i, w in ipairs(self.track.waypoints or {}) do
    if w._x and w.kind ~= 'racemile' and w.kind ~= 'place' then
      local dx, dy = w._x - px, w._y - py
      if dx * dx + dy * dy <= radius * radius * 2.5 then
        out.wps[#out.wps + 1] = { r1(dx), r1(dy), w.kind, self.judged[i] }
      end
    end
  end
  return out
end

return M
