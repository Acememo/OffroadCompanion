-- Wet ground after rain (the user, 2026-10-28: "could you make realistically more slippery on places that it's raining
-- or rained recently? And mud/water puddles if it rained and the water could accumulate, like in between woops and
-- natural creeks or rivers. Realism is my most wanted feature so don't over do it").
--
-- The ground's wetness w (0 dry .. 1 soaked) comes from the companion (gpsd/wetness.py: the rain of the last days where
-- the car is, the same for everyone near at the same hour), and is at least RAIN_W while the game's own rain falls
-- (BeamNG.Earth's weather, the level's rain object: in BeamMP the server's weather).
--
--   grip     BeamNG's ground models lose some grip with w (FACTORS: full-wet multipliers of their static and sliding
--            friction, near the measured drops of wet against dry surfaces; wet asphalt as BeamNG's own ASPHALT_WET).
--            Sand and mud are left as they are (wet sand holds better, mud is mud). be:setGroundModel changes a
--            model live for everything on it; the models' own values come back when the ground dries, the setting is
--            turned off or the mod unloads.
--   puddles  from PUDDLE_W, water in the closed dips of the track near the car (the troughs between whoops, a dip
--            through a wash): found from the ground itself along the track's middle every SCAN_S (a dip whose
--            rims along the track and both sides stand above its floor), filled part way (more the wetter), each a
--            small WaterBlock whose surface the ground around it hides (BeamNG.Earth's sea uses them: water physics
--            too). The same ground gives the same puddles on every computer.
local M = {}

M.enabled = true
-- full-wet multipliers (static, sliding friction) per ground model (BeamNG's art/groundmodels.json names)
M.FACTORS = {
  ASPHALT = { 0.94, 0.79 }, ASPHALT_OLD = { 0.94, 0.80 }, COBBLESTONE = { 0.88, 0.80 },
  DIRT = { 0.86, 0.84 }, DIRT_DUSTY = { 0.86, 0.84 }, DIRT_DUSTY_LOOSE = { 0.90, 0.88 }, GRAVEL = { 0.92, 0.90 },
  GRASS = { 0.76, 0.72 }, ROCK = { 0.88, 0.84 },
}
M.STEP = 0.05               -- grip rewritten when w moved this much
M.RAIN_W = 0.5              -- while the game's rain falls, the ground at least this wet
M.PUDDLE_W = 0.55           -- puddles from here (wetness.py PUDDLE_W)
M.PUDDLE_OFF_W = 0.45       -- ... and gone below this
M.SCAN_S = 2.0
-- (1.6.2, the user 2026-10-28: "the puddles render too close to the camera; they should be visible from further away so
-- the pilots can account for it": made out to AHEAD_M along the course, a few each scan, nearest first)
M.AHEAD_M, M.BEHIND_M = 450, 60
M.SAMPLE_M = 0.5            -- along the track's middle
M.RIM_M = 6.0               -- a dip's rims looked for this far along either way
M.MIN_DEPTH = 0.06          -- m: shallower dips hold no water worth showing
M.FILL = { 0.3, 0.7 }       -- share of a dip's depth filled at PUDDLE_W .. soaked
M.HALF_WIDTHS = { 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0 }   -- m across: the narrowest whose outline the ground closes
M.MAX = 40                  -- puddles at once
M.DESPAWN_M = 650
M.PER_SCAN = 6
M.RAIN_OBJECT = 'bngEarthRain'

local origin = {}           -- ground model name -> { static, sliding } as the game had it (false: left alone)
M.applied = 0               -- the w the grip is set for
M.w, M.real, M.rainNow = 0, nil, false
M.puddles = {}              -- key -> { id, x, y, z }
M.none = {}                 -- key -> the wetness bucket a dip there was found to hold no water at
M.nPuddles = 0
M.failed = nil
local scanAt = -math.huge

-- Pure: the multipliers of model name at wetness w.
function M.factor(name, w)
  local f = M.FACTORS[name]
  if not f then return 1, 1 end
  w = math.max(0, math.min(1, w or 0))
  return 1 - w * (1 - f[1]), 1 - w * (1 - f[2])
end

local function engine() return rawget(_G, 'be') end

local function setGrip(w)
  local be = engine()
  if not (be and be.getGroundModel and be.setGroundModel) then return false end
  for name in pairs(M.FACTORS) do
    local ok = pcall(function()
      local g = be:getGroundModel(name)
      local d = g and g.data
      if not d then return end
      if origin[name] == nil then
        -- (a model whose shearStrength reads back non-zero is left alone: written back, it changed how the model
        -- behaved, BeamNG forum 2020)
        local sh = tonumber(d.shearStrength) or 0
        origin[name] = sh == 0 and { tonumber(d.staticFrictionCoefficient), tonumber(d.slidingFrictionCoefficient) } or false
      end
      local o = origin[name]
      if not o or not o[1] or not o[2] then return end
      local ks, kd = M.factor(name, w)
      d.staticFrictionCoefficient = o[1] * ks
      d.slidingFrictionCoefficient = o[2] * kd
      be:setGroundModel(name, d)
    end)
    if not ok then M.failed = 'grip: ' .. name end
  end
  M.applied = w
  return true
end

-- The game's ground models back as they were.
function M.restore()
  if M.applied ~= 0 then setGrip(0) end
  M.applied = 0
end

-- The companion's answer (wetness_result): the rain of the last days.
function M.onWetness(msg)
  if type(msg) ~= 'table' or type(msg.w) ~= 'number' then return end
  M.real = { w = msg.w, level = msg.level, rainMmH = msg.rainMmH, last24 = msg.last24, hour = msg.hour }
end

local function raining()
  local so = rawget(_G, 'scenetree')
  local o = so and so.findObject and so.findObject(M.RAIN_OBJECT)
  if not o then return false end
  local ok, v = pcall(function() return tonumber(o:getField('numDrops', 0)) end)
  return ok and v ~= nil and v > 0
end

-- Pure: the wetness to use from the companion's and the game's rain.
function M.wetness(real, rainNow)
  local w = real and tonumber(real.w) or 0
  if rainNow then w = math.max(w, M.RAIN_W) end
  return math.max(0, math.min(1, w))
end

-- -- puddles ------------------------------------------------------------------------------------------------------
-- Pure: the dips of heights h (every step m along the track): { { i, floor, rim } } where h[i] is the lowest within
-- RIM_M / 4 either way and the ground rises at least MIN_DEPTH above it within RIM_M on both sides (rim: the lower of
-- the two highest points), the deepest first, none closer than RIM_M to a deeper one.
function M.dips(h, step)
  local n = #h
  local near = math.max(1, math.floor(M.RIM_M / 4 / step + 0.5))
  local far = math.max(near + 1, math.floor(M.RIM_M / step + 0.5))
  local out = {}
  for i = 1, n do
    local v = h[i]
    if v then
      local lowest = true
      for j = math.max(1, i - near), math.min(n, i + near) do
        if h[j] and (h[j] < v or (h[j] == v and j < i)) then lowest = false; break end
      end
      if lowest then
        local left, right = nil, nil
        for j = math.max(1, i - far), i - 1 do if h[j] and (not left or h[j] > left) then left = h[j] end end
        for j = i + 1, math.min(n, i + far) do if h[j] and (not right or h[j] > right) then right = h[j] end end
        if left and right then
          local rim = math.min(left, right)
          if rim - v >= M.MIN_DEPTH then out[#out + 1] = { i = i, floor = v, rim = rim } end
        end
      end
    end
  end
  table.sort(out, function(a, b) return (a.rim - a.floor) > (b.rim - b.floor) end)
  local keep = {}
  for _, d in ipairs(out) do
    local ok = true
    for _, k in ipairs(keep) do if math.abs(k.i - d.i) * step < M.RIM_M then ok = false; break end end
    if ok then keep[#keep + 1] = d end
  end
  return keep
end

-- Pure: the water's level in a dip at wetness w.
function M.level(d, w)
  local t = math.max(0, math.min(1, (w - M.PUDDLE_W) / (1 - M.PUDDLE_W)))
  local fill = M.FILL[1] + (M.FILL[2] - M.FILL[1]) * t
  return d.floor + fill * (d.rim - d.floor)
end

-- Pure: the puddle's box in a dip at index i of heights h (step m apart along the track): along the track the run of
-- samples under the level (stretched up to EXTEND samples either way where the sides of the trough lie lower than
-- its middle); across it the narrowest of HALF_WIDTHS whose whole outline stands above the level (side(s, off) ->
-- the ground's height there), so the ground closes the water all round and hides the surface's edges. nil when the
-- ground does not hold it (the water would run off: a dip open to the side, a wash across the track).
M.EXTEND = 3
function M.box(h, step, i, level, side)
  local a, b = i, i
  while a > 1 and h[a - 1] and h[a - 1] < level do a = a - 1 end
  while b < #h and h[b + 1] and h[b + 1] < level do b = b + 1 end
  if a == 1 or b == #h then return nil end            -- (it runs off the scanned stretch: not a closed dip)
  local function dry(s, off)
    local z = side(s, off)
    return z ~= nil and z >= level + 0.005
  end
  for _, hw in ipairs(M.HALF_WIDTHS) do
    local offs = { -hw, -hw / 2, 0, hw / 2, hw }
    for ext = 0, M.EXTEND do
      local s0, s1 = (a - 1.5 - ext) * step, (b - 0.5 + ext) * step   -- (half a sample past the last wet one)
      local ok = s0 >= 0 and s1 <= (#h - 1) * step
      for k = 0, 6 do                                 -- the sides
        if not ok then break end
        local s = s0 + (s1 - s0) * k / 6
        ok = dry(s, -hw) and dry(s, hw)
      end
      for _, off in ipairs(offs) do                   -- the ends
        if not ok then break end
        ok = dry(s0, off) and dry(s1, off)
      end
      if ok then return { s0 = s0, s1 = s1, hw = hw } end
    end
  end
  return nil
end

local function groundZ(x, y, zHint)
  local ray = rawget(_G, 'castRayStatic')
  if not ray then return nil end
  local top = (zHint or 0) + 30
  local ok, d = pcall(ray, vec3(x, y, top), vec3(0, 0, -1), 200)
  if ok and type(d) == 'number' and d < 200 then return top - d end
  return nil
end

local FIELDS = {
  { 'fresnelPower', 0, '0.3' }, { 'overallWaveMagnitude', 0, '0' }, { 'overallFoamOpacity', 0, '0' },
  { 'depthGradientMax', 0, '0.4' }, { 'wetDarkening', 0, '0.45' }, { 'wetDepth', 0, '0.15' },
  { 'fullReflect', 0, '0' }, { 'reflectDetailAdjust', 0, '0' },
  { 'rippleSpeed', 0, '0.01' }, { 'rippleSpeed', 1, '0.02' }, { 'rippleSpeed', 2, '0.005' },
  { 'rippleTexScale', 0, '3 3' }, { 'rippleTexScale', 1, '1 1' }, { 'rippleTexScale', 2, '30 30' },
}
-- (the user, 2026-10-28: "they should be kind of muddy or full muddy depending on the rain intensity and how long has it
-- been since it rained") The water's look by how fresh the rain is (M.mud): raining or just rained, brown water with the
-- sky in it and rain rings; as it settles, thicker; a day or two on, a mud hole: opaque, dull, still.
M.LOOKS = {
  fresh = { base = '92 78 58 255', under = '96 82 60 250', clarity = '0.05', bias = '-0.3', spec = '700', ripple = '0.35' },
  settled = { base = '78 64 46 255', under = '80 66 48 252', clarity = '0.02', bias = '-0.6', spec = '300', ripple = '0.06' },
  mud = { base = '62 49 35 255', under = '62 49 35 255', clarity = '0.0', bias = '-0.95', spec = '40', ripple = '0' },
}

-- Pure: the puddles' look (a M.LOOKS key) for the companion's rain (real: rainMmH the last hour, last24 the last day,
-- mm) and the game's rain falling now.
function M.look(real, rainNow)
  local hr = real and tonumber(real.rainMmH) or 0
  local day = real and tonumber(real.last24) or 0
  if rainNow or hr >= 0.2 then return 'fresh' end
  if day >= 3 then return 'settled' end
  return 'mud'
end
-- the stock water textures BeamNG.Earth's sea uses (core ones)
local TEXTURES = {
  { 'rippleTex', '/art/water/ripple.dds' }, { 'foamTex', '/art/water/foam.dds' },
  { 'depthGradientTex', '/art/water/depthcolor_ramp.png' },
}

local function removePuddle(key)
  local p = M.puddles[key]
  M.puddles[key] = nil
  M.nPuddles = M.nPuddles - 1
  local so = rawget(_G, 'scenetree')
  local o = p and so and so.findObjectById and so.findObjectById(p.id)
  if o then pcall(function() o:delete() end) end
end

function M.clear()
  for k in pairs(M.puddles) do removePuddle(k) end
  M.nPuddles = 0
  M.none = {}
end

local function makePuddle(key, x, y, level, len, width, dx, dy, depth)
  local markers = require('offroadCompanion/markers')
  local o = createObject('WaterBlock')
  o:setField('gridSize', 0, tostring(math.max(1, math.floor(math.min(len, width)))))
  for _, f in ipairs(FIELDS) do o:setField(f[1], f[2], f[3]) end
  local L = M.LOOKS[M.lookNow or 'settled'] or M.LOOKS.settled
  o:setField('baseColor', 0, L.base)
  o:setField('underwaterColor', 0, L.under)
  o:setField('clarity', 0, L.clarity)
  o:setField('fresnelBias', 0, L.bias)
  o:setField('specularPower', 0, L.spec)
  o:setField('overallRippleMagnitude', 0, L.ripple)
  local fs = rawget(_G, 'FS')
  for _, t in ipairs(TEXTURES) do
    if not fs or not fs.fileExists or fs:fileExists(t[2]) then o:setField(t[1], 0, t[2]) end
  end
  -- (a WaterBlock's surface is at its position, its volume half its height below: BeamNG.Earth's sea.lua); its length
  -- along the track (the box is the same turned half round)
  o:setScale(vec3(width, len, 2 * (depth + 0.1)))
  markers.place(o, x, y, level, markers.faceYaw(dx, dy))
  o:setField('gridElementSize', 0, '0.5')
  o.canSave = false
  o:registerObject('ocPuddle_' .. key)
  if scenetree.MissionGroup then scenetree.MissionGroup:addObject(o) end
  return o:getId()
end

-- The puddles near the car along the course (crs: course.lua's, its frame for this anchor; sides: the track's middle
-- off the course line, markers.halfAt).
local function scan(crs, anchor, car, w, halfAt)
  local e = crs.e and crs.e.anchor == anchor and crs.e or nil
  if not e or not e.n or e.n < 2 or not crs.s then return end
  local poly = require('offroadCompanion/poly')
  local s0 = math.max(0, crs.s - M.BEHIND_M)
  local s1 = math.min(e.length, crs.s + M.AHEAD_M)
  local step = M.SAMPLE_M
  local pts, h = {}, {}
  local n = math.floor((s1 - s0) / step)
  for k = 0, n do
    local s = s0 + k * step
    local x, y, dx, dy = poly.at(e, s)
    local _, ctr = halfAt(crs.sides, s, 2.5)
    ctr = ctr or 0
    x, y = x - dy * ctr, y + dx * ctr                -- (left normal: (-dy, dx))
    pts[k + 1] = { x = x, y = y, dx = dx, dy = dy, s = s }
    h[k + 1] = groundZ(x, y, car.z)
  end
  local made = 0
  -- (box positions are metres from the stretch's first sample)
  local function at(srel)
    return pts[math.max(1, math.min(#pts, math.floor(srel / step + 0.5) + 1))]
  end
  local function side(srel, off)
    local q = at(srel)
    return groundZ(q.x - q.dy * off, q.y + q.dx * off, car.z)
  end
  -- the nearest first, ahead of the car before behind it
  local dips = M.dips(h, step)
  for _, d in ipairs(dips) do
    local ds = pts[d.i].s - crs.s
    d.rank = ds >= 0 and ds or (-ds * 3)
  end
  table.sort(dips, function(a, b) return a.rank < b.rank end)
  local bucket = math.floor(w * 20 + 0.5)
  for _, d in ipairs(dips) do
    if M.nPuddles >= M.MAX or made >= M.PER_SCAN then break end
    local p = pts[d.i]
    local key = string.format('%d', math.floor(p.s / M.RIM_M + 0.5))
    if not M.puddles[key] and M.none[key] ~= bucket then
      local level = M.level(d, w)
      local b = M.box(h, step, d.i, level, side)
      if not b then M.none[key] = bucket end          -- (the ground there holds none at this wetness: not again)
      if b then
        local q = at((b.s0 + b.s1) / 2)
        local ok, id = pcall(makePuddle, key, q.x, q.y, level, b.s1 - b.s0, 2 * b.hw, q.dx, q.dy, level - d.floor)
        if ok then
          M.puddles[key] = { id = id, x = q.x, y = q.y, z = level }
          M.nPuddles, made = M.nPuddles + 1, made + 1
        else
          M.failed = 'puddle: ' .. tostring(id)
          return
        end
      end
    end
  end
end

-- -- the wet look --------------------------------------------------------------------------------------------------
-- (the user, 2026-10-28: "the puddles appear on visually dry dirt ... also the roads look dry when wet") The ground the
-- player sees is BeamNG.Earth's tiles with the aerial photo (their Materials, bngEarthFar_..., satmat.lua; the roads
-- painted into the photo, asphalt as a second layer): wet, the photo goes darker and glossier, asphalt more so; dry,
-- back as BeamNG.Earth made them. A few materials a tick (a change reloads each), every one looked at again every
-- SWEEP_S (new tiles' materials, one BeamNG.Earth set back).
M.LOOK_PREFIX = 'bngEarthFar_'
M.DARK, M.GLOSS = 0.32, 0.55                -- soaked: the photo this much darker, roughness 1 -> 1 - GLOSS
M.ASPHALT_DARK, M.ASPHALT_GLOSS = 0.4, 0.6  -- ... its asphalt layer (0.35 grey, roughness 0.9)
M.LOOK_STEP = 0.1
M.SWEEP_S = 15
M.PER_TICK = 6
M.FALLBACK_COLOR = '0.39 0.35 0.27 1'       -- (satmat's colour for a missing photo: left alone)
local lookQ, lookHead, lookAt, lookW = {}, 1, -math.huge, nil
M.looked = 0

local function f3(v) return string.format('%.3f', v) end

-- Pure: the fields of the wet look at wetness w (quantised): photo colour factor, roughness, asphalt colour, roughness.
function M.groundLook(w)
  w = math.max(0, math.min(1, math.floor((w or 0) / M.LOOK_STEP + 0.5) * M.LOOK_STEP))
  local k = 1 - M.DARK * w
  local ka = 0.35 * (1 - M.ASPHALT_DARK * w)
  return { w = w, color = f3(k) .. ' ' .. f3(k) .. ' ' .. f3(k) .. ' 1', rough = f3(1 - M.GLOSS * w),
           acolor = f3(ka) .. ' ' .. f3(ka) .. ' ' .. f3(ka) .. ' 1', arough = f3(0.9 - M.ASPHALT_GLOSS * w) }
end

local function lookOne(name, L)
  local so = rawget(_G, 'scenetree')
  local m = so and so.findObject and so.findObject(name)
  if not m then return false end
  local v15 = tostring(m:getField('version', 0)) == '1.5'
  if not v15 and tostring(m:getField('diffuseColor', 0)) == M.FALLBACK_COLOR then return false end
  local colorField = v15 and 'baseColorFactor' or 'diffuseColor'
  local two = v15 and tostring(m:getField('activeLayers', 0)) == '2'
  if tostring(m:getField('roughnessFactor', 0)) == L.rough and tostring(m:getField(colorField, 0)) == L.color
      and (not two or tostring(m:getField('roughnessFactor', 1)) == L.arough) then
    return false
  end
  m:setField(colorField, 0, L.color)
  m:setField('roughnessFactor', 0, L.rough)
  if two then
    m:setField('baseColorFactor', 1, L.acolor)
    m:setField('roughnessFactor', 1, L.arough)
  end
  pcall(function() m:flush() end)
  pcall(function() m:reload() end)
  return true
end

-- The wet look for wetness w: the materials queued again when it changed or SWEEP_S went by, a few done per call.
function M.lookTick(w, now)
  local L = M.groundLook(w)
  local so = rawget(_G, 'scenetree')
  if not (so and so.findClassObjects) then return end
  if L.w ~= lookW or now - lookAt >= M.SWEEP_S then
    if L.w == 0 and lookW == nil then lookAt = now; return end    -- (dry from the start: nothing to put back)
    lookW, lookAt = L.w, now
    lookQ, lookHead = {}, 1
    local ok, names = pcall(so.findClassObjects, 'Material')
    if ok and type(names) == 'table' then
      for _, nm in ipairs(names) do
        if type(nm) == 'string' and nm:sub(1, #M.LOOK_PREFIX) == M.LOOK_PREFIX then lookQ[#lookQ + 1] = nm end
      end
    end
  end
  local done = 0
  while lookHead <= #lookQ and done < M.PER_TICK do
    local nm = lookQ[lookHead]
    lookHead = lookHead + 1
    local ok, changed = pcall(lookOne, nm, L)
    if ok and changed then done = done + 1; M.looked = M.looked + 1 end
  end
end

-- Every frame or so: the grip for the wetness now, the puddles near the car. crs / anchor / car may be nil (no course:
-- the grip still follows the rain; no puddles).
function M.update(dt, crs, anchor, car, halfAt, now)
  now = now or os.clock()
  M.rainNow = raining()
  local w = M.enabled and M.wetness(M.real, M.rainNow) or 0
  M.w = w
  if math.abs(w - M.applied) >= M.STEP or (w == 0 and M.applied ~= 0) then setGrip(w) end
  pcall(M.lookTick, w, now)
  local want = M.enabled and car and crs and (w >= M.PUDDLE_W or (M.nPuddles > 0 and w >= M.PUDDLE_OFF_W))
  if not want then
    if M.nPuddles > 0 then M.clear() end
    return
  end
  if M.anchor ~= anchor then M.clear(); M.anchor = anchor end   -- (the world moved: they stand elsewhere now)
  local lk = M.look(M.real, M.rainNow)
  if lk ~= M.lookNow then                     -- (the rain stopped, or came: the water looks different now)
    if M.lookNow then M.clear() end
    M.lookNow = lk
  end
  for k, p in pairs(M.puddles) do
    if (p.x - car.x) ^ 2 + (p.y - car.y) ^ 2 > M.DESPAWN_M * M.DESPAWN_M then removePuddle(k) end
  end
  if now - scanAt >= M.SCAN_S and not M.failed then
    scanAt = now
    local ok, err = pcall(scan, crs, anchor, car, w, halfAt)
    if not ok then M.failed = tostring(err) end
  end
end

-- The dry look back on every material at once (the mod unloading, the setting turned off).
function M.restoreLook()
  if lookW == nil or lookW == 0 then return end
  local L = M.groundLook(0)
  local so = rawget(_G, 'scenetree')
  local ok, names = pcall(function() return so.findClassObjects('Material') end)
  if ok and type(names) == 'table' then
    for _, nm in ipairs(names) do
      if type(nm) == 'string' and nm:sub(1, #M.LOOK_PREFIX) == M.LOOK_PREFIX then pcall(lookOne, nm, L) end
    end
  end
  lookW, lookQ, lookHead = 0, {}, 1
end

function M.setEnabled(on)
  M.enabled = on and true or false
  if not M.enabled then M.clear(); M.restore(); M.restoreLook() end
  return M.enabled
end

function M.status()
  return { w = M.w, level = M.real and M.real.level or nil, rainNow = M.rainNow, last24 = M.real and M.real.last24 or nil,
           puddles = M.nPuddles, grip = M.applied, failed = M.failed, enabled = M.enabled, look = M.lookNow,
           wetLook = lookW }
end

return M
