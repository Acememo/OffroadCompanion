-- The course drawn on the ground ahead of the car: a ribbon of chevrons along the line (colour by what the stretch
-- is: course, speed zone, danger near), and posts at checkpoints / VCPs. Heights come from a ray cast down at each
-- sample (cached per anchor: the ground under a sample only changes when the world rebases or the terrain loads in).
-- debugDrawer is the game's immediate-mode 3D drawing; every call is guarded, and a failure turns the ribbon off
-- with one log line instead of spamming errors every frame.
local poly = require('offroadCompanion/poly')

local M = {}

M.enabled = true
M.BACK_M, M.AHEAD_M, M.STEP_M = 15, 320, 6
M.LIFT = 0.35               -- metres above the ground
M.WIDTH, M.THICK = 1.4, 0.08
M.RAY_UP, M.RAY_LEN = 80, 400
M.RETRY_S = 1.5             -- a sample whose ray missed (ground not loaded yet) is cast again after this
M.POST_H, M.POST_R = 6, 0.35

local cache = { anchor = nil, z = {}, miss = {} }
M.failed = nil

local function groundZ(x, y, zHint, now)
  local ray = rawget(_G, 'castRayStatic')
  if not ray then return nil end
  local ok, d = pcall(ray, vec3(x, y, zHint + M.RAY_UP), vec3(0, 0, -1), M.RAY_LEN)
  if ok and d and d < M.RAY_LEN then return zHint + M.RAY_UP - d end
  return nil
end

local function sampleZ(key, x, y, zHint, now)
  local z = cache.z[key]
  if z then return z end
  local m = cache.miss[key]
  if m and now - m < M.RETRY_S then return nil end
  z = groundZ(x, y, zHint, now)
  if z then cache.z[key] = z; cache.miss[key] = nil else cache.miss[key] = now end
  return z
end

-- Pure: the colour {r, g, b} of the ribbon at s (speed zone yellow, near a danger red, else the course colour).
function M.colorAt(s, zones, dangers)
  for _, d in ipairs(dangers or {}) do
    if s >= d - 150 and s <= d + 30 then return { 1.0, 0.25, 0.2 } end
  end
  for _, z in ipairs(zones or {}) do
    if s >= z.s0 and s <= z.s1 then return { 1.0, 0.82, 0.15 } end
  end
  return { 0.15, 0.85, 1.0 }
end

local function drawOrFail(fn)
  local ok, err = pcall(fn)
  if not ok then
    M.enabled, M.failed = false, tostring(err)
    if log then log('W', 'offroadCompanion', 'course ribbon turned off: ' .. M.failed) end
  end
end

-- Every frame (onPreRender): course (course.lua instance, framed), car position, now.
function M.draw(course, carPos, now)
  if not M.enabled or not course or not course.hasLine or not course.e or not course.s or not carPos then return end
  local dd = rawget(_G, 'debugDrawer')
  if not dd then return end
  local e = course.ahead or course.e
  if cache.anchor ~= e.anchor then cache = { anchor = e.anchor, z = {}, miss = {} } end
  local tr = course.track
  local dangers = course._dangerS
  if not dangers then
    dangers = {}
    for _, w in ipairs(tr.waypoints or {}) do
      if w.kind == 'danger' and (w.off or 0) < 400 then dangers[#dangers + 1] = w.s end
    end
    course._dangerS = dangers
  end
  local s0 = course.s - M.BACK_M
  local s1 = course.s + M.AHEAD_M
  local step = M.STEP_M
  local zHint = carPos.z
  local first = math.floor(math.max(0, s0) / step)
  local last = math.floor(math.min(e.length, s1) / step)
  drawOrFail(function()
    local prev = nil
    for k = first, last do
      local s = k * step
      local x, y = poly.at(e, s)
      local z = sampleZ(k, x, y, zHint, now)
      if z then
        zHint = z
        local p = vec3(x, y, z + M.LIFT)
        if prev then
          local dist = math.abs(s - course.s)
          local a = math.max(0.15, 0.85 - dist / M.AHEAD_M * 0.7)
          local c = M.colorAt(s, tr.zones, dangers)
          if k % 2 == 0 then
            dd:drawSquarePrism(prev, p, Point2F(M.THICK, M.WIDTH), Point2F(M.THICK, M.WIDTH * 0.35),
              ColorF(c[1], c[2], c[3], a))
          end
        end
        prev = p
      else
        prev = nil
      end
    end
    -- posts at checkpoints / VCPs within reach (green once hit, red when missed)
    for i, w in ipairs(tr.waypoints or {}) do
      if (w.kind == 'vcp' or w.kind == 'checkpoint' or w.kind == 'finish' or w.kind == 'start') and w._x then
        local ds = w.s - course.s
        if ds > -40 and ds < 700 then
          local z = sampleZ('w' .. i, w._x, w._y, carPos.z, now)
          if z then
            local j = course.judged[i]
            local c = j == 'hit' and { 0.2, 1, 0.3 } or j == 'miss' and { 1, 0.2, 0.2 } or { 1, 0.55, 0.1 }
            dd:drawCylinder(vec3(w._x, w._y, z), vec3(w._x, w._y, z + M.POST_H), M.POST_R, ColorF(c[1], c[2], c[3], 0.8))
            if ds < 250 and dd.drawTextAdvanced then
              dd:drawTextAdvanced(vec3(w._x, w._y, z + M.POST_H + 0.8), String(w.name), ColorF(1, 1, 1, 1), true,
                false, ColorI(0, 0, 0, 160))
            end
          end
        end
      end
    end
  end)
  -- forget samples far behind (a long course would grow the cache forever)
  if (now - (cache.pruned or 0)) > 5 then
    cache.pruned = now
    for key in pairs(cache.z) do
      if type(key) == 'number' and (key < first - 50 or key > last + 200) then cache.z[key] = nil end
    end
  end
end

function M.reset() cache = { anchor = nil, z = {}, miss = {} } end

return M
