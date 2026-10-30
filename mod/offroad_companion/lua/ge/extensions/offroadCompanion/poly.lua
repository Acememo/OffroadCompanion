-- Polyline maths in the world frame (x east, y north, metres): BeamNG.Earth's world is the current anchor's local
-- east/north/up frame, so a lat/lon line is turned into x/y once per anchor and everything after is planar.
-- Pure: no engine calls (runs under plain LuaJIT in the tests).
local M = {}

local sqrt, atan2, deg, rad, abs, floor, min, max = math.sqrt, math.atan2, math.deg, math.rad, math.abs, math.floor, math.min, math.max

M.MILE = 1609.344

-- The line {x = {}, y = {}, cum = {}, n} of points {{lat, lon}...} in anchor's frame (anchor:geodeticToEnu).
function M.toFrame(anchor, points)
  local xs, ys, cum = {}, {}, { 0 }
  for i, p in ipairs(points) do
    xs[i], ys[i] = anchor:geodeticToEnu(p[1], p[2], 0)
    if i > 1 then
      local dx, dy = xs[i] - xs[i - 1], ys[i] - ys[i - 1]
      cum[i] = cum[i - 1] + sqrt(dx * dx + dy * dy)
    end
  end
  return { x = xs, y = ys, cum = cum, n = #xs, anchor = anchor, length = cum[#cum] or 0 }
end

-- From plain x/y arrays (tests).
function M.fromXY(xs, ys)
  local cum = { 0 }
  for i = 2, #xs do
    local dx, dy = xs[i] - xs[i - 1], ys[i] - ys[i - 1]
    cum[i] = cum[i - 1] + sqrt(dx * dx + dy * dy)
  end
  return { x = xs, y = ys, cum = cum, n = #xs, length = cum[#cum] or 0 }
end

-- The first index i with cum[i] >= s (binary search), clamped to 1..n.
function M.indexAt(e, s)
  local lo, hi = 1, e.n
  if s <= 0 then return 1 end
  if s >= e.cum[hi] then return hi end
  while lo < hi do
    local mid = floor((lo + hi) / 2)
    if e.cum[mid] < s then lo = mid + 1 else hi = mid end
  end
  return lo
end

-- Nearest spot on segments i0 .. i1-1 (i -> i+1) to (px, py): segment i, fraction t, distance d, s along.
function M.nearest(e, px, py, i0, i1)
  local xs, ys = e.x, e.y
  if e.n == 1 then return 1, 0, sqrt((xs[1] - px) ^ 2 + (ys[1] - py) ^ 2), 0 end
  local bi, bt, bd = 1, 0, math.huge
  for i = max(1, i0 or 1), min(e.n - 1, (i1 or e.n) - 1) do
    local ax, ay = xs[i], ys[i]
    local dx, dy = xs[i + 1] - ax, ys[i + 1] - ay
    local L2 = dx * dx + dy * dy
    local t = L2 > 0 and max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L2)) or 0
    local qx, qy = ax + t * dx - px, ay + t * dy - py
    local d = qx * qx + qy * qy
    if d < bd then bi, bt, bd = i, t, d end
  end
  local s = e.cum[bi] + bt * ((e.cum[bi + 1] or e.cum[bi]) - e.cum[bi])
  return bi, bt, sqrt(bd), s
end

-- Follow a car along the line from its last spot (prevS, or nil): searched near where it was (prevS - BACK_M ..
-- prevS + AHEAD_M), so a course that crosses itself is not jumped onto its other pass; farther than REACQUIRE_M
-- from that stretch, the whole line is searched, preferring spots near prevS (d + DRIFT * |s - prevS|).
-- Returns s, d (distance from the line), i (segment).
M.BACK_M, M.AHEAD_M, M.REACQUIRE_M, M.DRIFT = 150, 1500, 150, 0.02
function M.follow(e, px, py, prevS)
  if prevS then
    local i0 = max(1, M.indexAt(e, prevS - M.BACK_M) - 1)
    local i1 = min(e.n, M.indexAt(e, prevS + M.AHEAD_M) + 1)
    local i, _, d, s = M.nearest(e, px, py, i0, i1)
    if d <= M.REACQUIRE_M then return s, d, i end
    -- reacquire: scan in chunks, keep the best score
    local best, bs, bd, bi = math.huge, s, d, i
    local CH = 200
    for c0 = 1, e.n - 1, CH do
      local ci, _, cd, cs = M.nearest(e, px, py, c0, min(e.n, c0 + CH + 1))
      local score = cd + M.DRIFT * abs(cs - prevS)
      if score < best then best, bs, bd, bi = score, cs, cd, ci end
    end
    return bs, bd, bi
  end
  local i, _, d, s = M.nearest(e, px, py, 1, e.n)
  return s, d, i
end

-- The point and direction (unit dx, dy) at s along the line.
function M.at(e, s)
  if e.n == 1 then return e.x[1], e.y[1], 0, 1, 1 end
  local k = M.indexAt(e, s)
  if k > 1 and e.cum[k] > s then k = k - 1 end
  if k >= e.n then k = e.n - 1 end
  local seg = e.cum[k + 1] - e.cum[k]
  local f = seg > 0 and max(0, min(1, (s - e.cum[k]) / seg)) or 0
  local dx, dy = e.x[k + 1] - e.x[k], e.y[k + 1] - e.y[k]
  local L = sqrt(dx * dx + dy * dy)
  if L < 1e-9 then dx, dy, L = 0, 1, 1 end
  return e.x[k] + f * dx, e.y[k] + f * dy, dx / L, dy / L, k
end

-- Compass bearing (deg, 0 north, clockwise) of a direction.
function M.bearing(dx, dy)
  return (deg(atan2(dx, dy)) + 360) % 360
end

-- Signed angle b - a in degrees, -180..180.
function M.angleDiff(a, b)
  local d = (b - a) % 360
  if d > 180 then d = d - 360 end
  return d
end

-- Which side of the line at s the point is on: 'left' | 'right' (seen driving along the line).
function M.side(e, s, px, py)
  local x, y, dx, dy = M.at(e, s)
  local cross = dx * (py - y) - dy * (px - x)
  return cross > 0 and 'left' or 'right'
end

-- Points {x, y} every step from s0 to s1 (both ends).
function M.slice(e, s0, s1, step)
  local out = {}
  s0 = max(0, s0)
  s1 = min(e.length, s1)
  local s = s0
  while true do
    local x, y = M.at(e, s)
    out[#out + 1] = { x, y, s }
    if s >= s1 then break end
    s = min(s + step, s1)
  end
  return out
end

-- Corner calls ("pace notes") along the line from s0 over `ahead` metres. Headings are taken every STEP m and
-- smoothed (GPS recordings wobble), runs of turning the same way above MIN_RATE are corners; the tightest radius
-- over any WIN m of a corner grades it the rally way: hairpin, 1 (tightest) .. 6 (fast). Returns
-- {{dir = 'left'|'right', grade = 'hairpin'|1..6, s0, s1, angle (deg), radius (m), long}} in order.
M.STEP, M.WIN, M.MIN_RATE = 10, 30, 1.6     -- m, m, degrees of turn per STEP that count as a corner
M.GRADES = { { 25, 1 }, { 40, 2 }, { 60, 3 }, { 90, 4 }, { 140, 5 }, { 250, 6 } }
function M.corners(e, s0, ahead)
  if e.n < 3 or e.length < 3 * M.STEP then return {} end
  local step = M.STEP
  local pts = M.slice(e, s0, s0 + ahead + 2 * step, step)
  local n = #pts
  if n < 4 then return {} end
  local hd = {}
  for k = 1, n - 1 do hd[k] = M.bearing(pts[k + 1][1] - pts[k][1], pts[k + 1][2] - pts[k][2]) end
  local dt = {}
  for k = 1, #hd - 1 do dt[k] = M.angleDiff(hd[k], hd[k + 1]) end
  -- smooth the turn rate (3 samples)
  local sm = {}
  for k = 1, #dt do
    local a, c = dt[k - 1] or dt[k], dt[k + 1] or dt[k]
    sm[k] = (a + 2 * dt[k] + c) / 4
  end
  local out = {}
  local k = 1
  local winN = max(1, floor(M.WIN / step + 0.5))
  while k <= #sm do
    if abs(sm[k]) >= M.MIN_RATE then
      local sign = sm[k] > 0 and 1 or -1
      local j = k
      while j + 1 <= #sm and sm[j + 1] * sign >= M.MIN_RATE * 0.5 do j = j + 1 end
      local total, tight = 0, 0
      for q = k, j do total = total + sm[q] end
      for q = k, j do
        local w = 0
        for r = q, min(j, q + winN - 1) do w = w + sm[r] end
        if abs(w) > tight then tight = abs(w) end
      end
      local spanN = min(winN, j - k + 1)
      local radius = tight > 0 and (spanN * step) / rad(tight) or math.huge
      local angle = abs(total)
      local grade = nil
      if angle >= 140 and (j - k + 1) * step <= 90 then
        grade = 'hairpin'
      else
        for _, g in ipairs(M.GRADES) do
          if radius < g[1] then grade = g[2]; break end
        end
      end
      if grade and angle >= 12 then
        out[#out + 1] = {
          -- (a compass bearing that grows turns clockwise: right)
          dir = sign > 0 and 'right' or 'left', grade = grade, angle = angle, radius = radius,
          s0 = pts[k + 1][3], s1 = pts[min(n, j + 2)][3], long = (j - k + 1) * step >= 120 and angle >= 70,
        }
      end
      k = j + 1
    else
      k = k + 1
    end
  end
  return out
end

-- Race mile at s from anchors {{s, rm}...} (piecewise linear, extended past the ends at their slope); without two
-- anchors s in miles.
function M.raceMile(anchors, s)
  local n = anchors and #anchors or 0
  if n < 2 then return s / M.MILE end
  local a, b
  if s <= anchors[1][1] then
    a, b = anchors[1], anchors[2]
  elseif s >= anchors[n][1] then
    a, b = anchors[n - 1], anchors[n]
  else
    for i = 1, n - 1 do
      if s <= anchors[i + 1][1] then a, b = anchors[i], anchors[i + 1]; break end
    end
  end
  local ds = b[1] - a[1]
  if ds <= 0 then return a[2] end
  return a[2] + (s - a[1]) * (b[2] - a[2]) / ds
end

return M
