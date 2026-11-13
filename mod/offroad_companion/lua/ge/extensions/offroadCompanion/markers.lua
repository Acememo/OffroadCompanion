-- Course markers in the world, as desert races are marked (the user, 2026-10-22: "more realistic, as they use on
-- SCORE's Baja"). SCORE's GPS file is the course and its VCPs are virtual; what crews put out is signs on stakes:
--   'checkpoints' (the default): an orange VCP board on a stake both sides of the course at each VCP, a STOP sign
--     over a CHECKPOINT plate both sides at each checkpoint, a START / FINISH banner across the course, and a
--     painted stake every STAKE_EVERY_M (far apart, as the user asked 2026-10-21);
--   'full': also the course arrows on the inside of the turns, ARROW_BEFORE_M before them (one orange arrow under
--     45 degrees, two for 45-75, two on a pink board beyond), pink DANGER AHEAD boards before the hazards, both
--     sides, and SPEED ZONE / RESUME RACE SPEED boards at the speed zones' ends;
--   'off'.
-- Every sign faces the drivers coming (a turned object: the model faces -y). Only the ones near the car exist
-- (made within SPAWN_M, removed past DESPAWN_M): a handful of objects at a time, none collides.
-- Heights: a ray down where the marker stands. Far from the car (past the collidable block, ~400-500 m in detail
-- mode) that ray can meet the far tiles' sunk ring or nothing real, so a marker made out there is provisional:
-- within SURE_M every update measures the ground again and puts the marker back on it when it is off (that was why
-- only the first VCP showed, the user 2026-10-22: the next ones stood under the ground). A marker whose object went
-- away is made again.
-- Models: art/offroadcompanion/<name>.cdae / .dae (tools/make_markers.py); their materials, and the wheel ruts' (BeamNG.Earth's
-- server lays the ruts: OffroadCompanion/gpsd/ruts.py), are made here at runtime, as BeamNG.Earth does for its own.
local poly = require('offroadCompanion/poly')

local M = {}

M.mode = 'checkpoints'      -- 'off' | 'checkpoints' | 'full'
M.enabled = true            -- (mode ~= 'off'; kept for callers that switch it)
M.SPAWN_M, M.DESPAWN_M = 2400, 2750   -- (1.7.13: 1200, was 600; 1.7.17: Settings' Props distance, DISTANCES)
M.DISTANCES = { near = { 1200, 1500 }, far = { 2400, 2750 }, farthest = { 3600, 4000 } }
function M.setDistance(v)
  local d = M.DISTANCES[v] and v or 'far'
  M.SPAWN_M, M.DESPAWN_M = M.DISTANCES[d][1], M.DISTANCES[d][2]
  return d
end
M.SURE_M = 350              -- within this the ground under the car's block is real: heights checked every update
M.FIX_DZ_M, M.FIX_XY_M = 0.25, 1.0
M.SIDE_M = 6.0              -- a sign this far beside the course line, while the track's width there is not known ...
M.EDGE_M = 1.5              -- ... else this far past the track's (or the road's) edge, from its middle (the user,
                            -- 2026-10-22: "sometimes the markers appear in the middle of the road": a wide dirt road
                            -- the course follows off its middle; the companion says where it is, course_sides)
M.MOVE_M = 0.5              -- a standing sign further than this from where it now should be is moved
M.REPLACE_M = 2000          -- the signs this near the car placed again as the track's widths come in (the rest later)
M.STAKE_EVERY_M = 8000      -- a stake about every 5 miles ...
M.STAKE_CLEAR_M = 1500      -- ... not this near a gate
M.NEAR_LINE_M = 400         -- a checkpoint farther than this from the line stands where the file puts it
M.ARROW_MIN_DEG = 20        -- turns gentler than this get no arrow
M.ARROW_BEFORE_M = 30
M.ARROW_GAP_M = 120         -- at most one arrow per this much course
M.DANGER_BEFORE_M = 45      -- ~150 ft
M.TRIES_PER_UPDATE = 24     -- places whose ground is looked for per update at most
M.PER_UPDATE = 6            -- objects made per update at most (every MARKERS_S: twice a second)
M.RAY_UP, M.RAY_LEN = 400, 1500    -- (from well above: a sign on a hillside over the car)
M.DIR = '/art/offroadcompanion/'
M.RETRY_S = 30

M.MODELS = { 'sign_vcp', 'sign_cp', 'banner_start', 'banner_finish', 'stake', 'sign_danger', 'sign_zone',
             'sign_zone_end', 'arrow1_l', 'arrow1_r', 'arrow2_l', 'arrow2_r', 'arrow3_l', 'arrow3_r' }
M.HEIGHT = { sign_cp = 2.42, banner_start = 4.75, banner_finish = 4.75, stake = 1.5 }   -- (others 1.53)
local GATE = { vcp = true, checkpoint = true, start = true, finish = true }

M.MATERIALS = {             -- name -> fields (setField(name, 0, value))
  egps_ruts = { { 'colorMap', 'ruts.png' }, { 'diffuseColor', '1 1 1 1' }, { 'translucent', '1' }, { 'translucentBlendOp', 'LerpAlpha' },
                { 'castShadows', '0' } },
}
for _, n in ipairs(M.MODELS) do M.MATERIALS['egps_' .. n] = { { 'colorMap', n .. '.png' }, { 'diffuseColor', '1 1 1 1' } } end

local made = {}             -- material name -> true
local live = {}             -- key -> { id, x, y, z, yaw, dz (last measured: object z - ground z) }
local nLive = 0
local planned = { course = nil, anchor = nil, mode = nil, list = {} }
local serial = 0
M.failed = nil
M.fixed = 0                 -- markers put back on the ground (or remade) since the course was loaded

function M.setMode(m)
  if m == true or m == nil then m = 'checkpoints' elseif m == false then m = 'off' end
  if m ~= 'off' and m ~= 'full' then m = 'checkpoints' end
  M.mode, M.enabled = m, m ~= 'off'
  return m
end

-- The materials (once; a level change keeps them: Materials are not level objects). Returns how many exist.
function M.ensureMaterials()
  local n = 0
  local fs = rawget(_G, 'FS')
  for name, fields in pairs(M.MATERIALS) do
    if made[name] then
      n = n + 1
    else
      local ok = pcall(function()
        local m = scenetree.findObject(name)
        if not m then
          m = createObject('Material')
          m:setField('mapTo', 0, name)
          for _, f in ipairs(fields) do
            local v = f[2]
            if f[1] == 'colorMap' then
              v = M.DIR .. v
              if fs and fs.fileExists and not fs:fileExists(v) then error('missing ' .. v) end
            end
            m:setField(f[1], 0, v)
          end
          m.canSave = false
          m:registerObject(name)
        end
      end)
      if ok then made[name] = true; n = n + 1 end
    end
  end
  return n
end

-- The yaw (radians, counter-clockwise from the model's own frame) that turns a model facing -y to face drivers
-- travelling (dx, dy).
function M.faceYaw(dx, dy) return math.atan2(-dx, dy) end

-- Pure: where the markers of a course go, in the anchor's frame: { {key, model, x, y, yaw, gate (the waypoint kind
-- for checkpoint markers)} }. e: the course line framed (x, y, cum, n, length); waypoints with s / off / _x / _y;
-- opts: { mode = 'checkpoints' | 'full', zones = {{s0, s1}...} }.
function M.plan(e, waypoints, length, closed, opts)
  opts = opts or {}
  local full = opts.mode == 'full'
  local out = {}
  local line = e and e.n and e.n >= 2
  length = length or (e and e.length) or 0
  -- s: where along the course, side: +1 right / -1 left / 0 across it (a banner): the place is found again from these
  -- when the track's width there becomes known (M.place)
  local function put(key, model, x, y, yaw, gate, s, side)
    out[#out + 1] = { key = key, model = model, x = x, y = y, yaw = yaw or 0, gate = gate, s = s, side = side }
  end
  -- the course at s: point, direction, and a spot `side` metres to the right (negative: left)
  local function at(s, side)
    local x, y, dx, dy = poly.at(e, math.max(0, math.min(length, s)))
    return x + dy * side, y - dx * side, M.faceYaw(dx, dy)
  end
  -- beside the course (side +1 right, -1 left): past the track's edge and any other pass of the course there
  local function beside(s, side)
    local _, _, yaw = at(s, 0)
    local x, y = M.besideAt(e, length, s, side, opts.sides)
    return x, y, yaw
  end
  local function pair(key, model, s, gate)
    local x, y, yaw = beside(s, 1)
    put(key .. 'R', model, x, y, yaw, gate, s, 1)
    x, y, yaw = beside(s, -1)
    put(key .. 'L', model, x, y, yaw, gate, s, -1)
  end
  local gates = {}
  for i, w in ipairs(waypoints or {}) do
    local k = w.kind
    if GATE[k] and not (closed and k == 'finish') then
      local model = (k == 'vcp' and 'sign_vcp') or (k == 'checkpoint' and 'sign_cp')
        or (k == 'start' and 'banner_start') or 'banner_finish'
      if line and w.s and (w.off or 0) <= M.NEAR_LINE_M then
        if model:find('^banner') then
          local x, y, yaw = at(w.s, 0)
          put(i .. 'B', model, x, y, yaw, k, w.s, 0)
        else
          pair(tostring(i), model, w.s, k)
        end
        gates[#gates + 1] = w.s
      elseif w._x then
        put(i .. 'P', model, w._x, w._y, 0, k)
      end
    end
  end
  local function nearGate(s, r)
    for _, g in ipairs(gates) do if math.abs(g - s) < r then return true end end
    return false
  end
  if line and length > M.STAKE_EVERY_M then
    local s = M.STAKE_EVERY_M
    while s < length - M.STAKE_CLEAR_M do
      if not nearGate(s, M.STAKE_CLEAR_M) then
        local x, y, yaw = beside(s, 1)
        put('S' .. math.floor(s), 'stake', x, y, yaw, nil, s, 1)
      end
      s = s + M.STAKE_EVERY_M
    end
  end
  if full and line then
    for i, w in ipairs(waypoints or {}) do
      if w.kind == 'danger' and w.s and (w.off or 0) <= M.NEAR_LINE_M then
        pair('D' .. i, 'sign_danger', math.max(0, w.s - M.DANGER_BEFORE_M))
      end
    end
    for i, z in ipairs(opts.zones or {}) do
      if z.s0 then pair('Z' .. i .. 'a', 'sign_zone', z.s0) end
      if z.s1 and z.s1 < length then pair('Z' .. i .. 'b', 'sign_zone_end', z.s1) end
    end
    local lastS = -math.huge
    local ok, corners = pcall(poly.corners, e, 0, length)
    for _, c in ipairs(ok and corners or {}) do
      if c.angle >= M.ARROW_MIN_DEG then
        local s = math.max(0, c.s0 - M.ARROW_BEFORE_M)
        if s - lastS >= M.ARROW_GAP_M and not nearGate(s, 60) then
          local n = c.angle < 45 and 1 or (c.angle <= 75 and 2 or 3)
          local right = c.dir == 'right'
          local x, y, yaw = beside(s, right and 1 or -1)   -- (on the inside of the turn)
          put('A' .. math.floor(s), 'arrow' .. n .. (right and '_r' or '_l'), x, y, yaw, nil, s, right and 1 or -1)
          lastS = s
        end
      end
    end
  end
  return out
end

-- The ground under (x, y): rays down at three spots 0.8 m apart, their middle height (a tree or a post under one of
-- them does not lift the marker), or the lower of two; nil when nothing is there yet.
local OFFS = { { 0, 0 }, { 0.8, 0 }, { 0, 0.8 } }
local function rayZ(x, y, zHint)
  local ray = rawget(_G, 'castRayStatic')
  if not ray then return nil end
  local hits = {}
  local top = zHint + M.RAY_UP
  for _, o in ipairs(OFFS) do
    local ok, d = pcall(ray, vec3(x + o[1], y + o[2], top), vec3(0, 0, -1), M.RAY_LEN)
    if ok and type(d) == 'number' and d < M.RAY_LEN then hits[#hits + 1] = top - d end
  end
  if #hits == 0 then return nil end
  table.sort(hits)
  if #hits == 3 then return hits[2] end
  return hits[1]
end
M.rayZ = rayZ

-- The terrain's own height at (x, y) (the TerrainBlock the cars drive on: core_terrain), or nil.
local function terrainAt(x, y)
  local ct = rawget(_G, 'core_terrain')
  if not (ct and ct.getTerrainHeight) then return nil end
  local ok, h = pcall(ct.getTerrainHeight, vec3(x, y, 0))
  if ok and type(h) == 'number' and h == h and math.abs(h) < 1e5 then return h end
  return nil
end
M.terrainAt = terrainAt

-- The ground under (x, y): the terrain the cars drive on where it is there (its height, checked by a short ray down
-- onto it: TERRAIN_CHECK_M above it to as far below), else rayZ's rays from high above. (1.7.12, the user 2026-11-12:
-- spectators and signs standing right, then jumping into the air, and every one after them up there too: a ray from
-- RAY_UP above meets the first static collision on its way down, and after one of BeamNG.Earth's moves of the world
-- (a rebase) the old place's collision stays a while where it was, over the new ground.)
M.TERRAIN_CHECK_M = 2.0
M.TERRAIN_TOL_M = 0.35
local function groundZ(x, y, zHint)
  local t = terrainAt(x, y)
  local ray = rawget(_G, 'castRayStatic')
  if t and ray then
    local ok, d = pcall(ray, vec3(x, y, t + M.TERRAIN_CHECK_M), vec3(0, 0, -1), 2 * M.TERRAIN_CHECK_M)
    if ok and type(d) == 'number' and math.abs(d - M.TERRAIN_CHECK_M) <= M.TERRAIN_TOL_M then return t end
  end
  return rayZ(x, y, zHint)
end
M.groundZ = groundZ

-- Puts object o at (x, y, z) turned by yaw (CCW): BeamNG.Earth's own recipe for its props (trees.lua: setFromEuler
-- takes the angle clockwise). Returns whether it was turned.
local function place(o, x, y, z, yaw)
  if yaw and yaw ~= 0 and rawget(_G, 'MatrixF') and o.setTransform then
    local ok = pcall(function()
      local m = MatrixF(true)
      m:setFromEuler(vec3(0, 0, -yaw))
      m:setPosition(vec3(x, y, z))
      o:setTransform(m)
    end)
    if ok then return true end
  end
  o:setPosition(vec3(x, y, z))
  return false
end
M.place = place

local function remove(key)
  local l = live[key]
  live[key] = nil
  nLive = nLive - 1
  local o = l and scenetree.findObjectById(l.id)
  if o then pcall(function() o:delete() end) end
end

function M.clear()
  for key in pairs(live) do remove(key) end
  live, nLive = {}, 0
end

-- The shape files to try, in order: the .cdae (BeamNG's own binary shape, tools/make_cdae.py), then the .dae. The
-- first that loads is kept per model.
local shapeOf = {}          -- model -> the shape that loaded
local shapeBad = {}         -- shape path -> why it did not
function M.candidates(model)
  local base = M.DIR .. model
  local fs = rawget(_G, 'FS')
  local out = {}
  for _, ext in ipairs({ '.cdae', '.dae' }) do
    local p = base .. ext
    if not shapeBad[p] and (not (fs and fs.fileExists) or fs:fileExists(p)) then out[#out + 1] = p end
  end
  return out
end
function M.shape(model) return shapeOf[model] or M.candidates(model)[1] end

-- The made object's height (its world box), or nil when the engine does not say.
function M.objectHeight(o)
  local ok, h = pcall(function() local e = o:getWorldBox():getExtents(); return e.z end)
  if ok and type(h) == 'number' then return h end
  ok, h = pcall(function() local b = o:getObjBox(); return b.maxExtents.z - b.minExtents.z end)
  if ok and type(h) == 'number' then return h end
  return nil
end

-- One TSStatic of shape at (x, y, z) turned by yaw: its id, height (nil: unknown), the object, whether it was turned;
-- or nil and why it failed.
function M.make(shape, x, y, z, yaw, name)
  local o = createObject('TSStatic')
  o:setField('shapeName', 0, shape)
  o:setField('collisionType', 0, 'None')
  o:setField('decalType', 0, 'None')
  o.canSave = false
  local turned = place(o, x, y, z, yaw)
  if o:registerObject(name) == false then return nil, 'the engine refused the object' end
  scenetree.MissionGroup:addObject(o)
  return o:getID(), M.objectHeight(o), o, turned
end

local function spawn(m, z)
  serial = serial + 1
  local want = M.HEIGHT[m.model] or 1.53
  local last
  for _, shape in ipairs(shapeOf[m.model] and { shapeOf[m.model] } or M.candidates(m.model)) do
    local id, h, _, turned = M.make(shape, m.x, m.y, z, m.yaw, 'egpsMarker_' .. serial)
    if id then
      -- (the height is only reported: far from the camera the engine may not have measured the object yet)
      shapeOf[m.model] = shape
      M.placed = (M.placed or 0) + 1
      M.turned = turned
      if type(h) == 'number' and h < want * 0.6 then
        M.lowHeight = string.format('%s measured %.2f m tall when placed', shape, h)
      end
      if M.placed == 1 and log then
        log('I', 'offroadCompanion', string.format('course markers: first %s at %.0f %.0f %.0f (%s, height %s, turned %s)',
          m.model, m.x, m.y, z, shape, tostring(h), tostring(turned)))
      end
      return id
    end
    last = shape .. ': ' .. tostring(h)
    shapeBad[shape] = last
    if log then log('W', 'offroadCompanion', 'course markers: ' .. last) end
  end
  error('the marker could not be made (' .. tostring(last or 'no model file in the mod') .. ')')
end

-- (Settings' "Test markers") a VCP sign of each model file 12 m ahead of the car, 3 m either side, facing it, for a
-- minute: which ones the game shows, and what it says about each.
local testIds = {}
function M.test(car, headingDeg)
  for _, id in ipairs(testIds) do local o = scenetree.findObjectById(id); if o then pcall(function() o:delete() end) end end
  testIds = {}
  local fs = rawget(_G, 'FS')
  local hd = math.rad(headingDeg or 0)
  local fx, fy = math.sin(hd), math.cos(hd)
  local out = { materials = M.ensureMaterials(), items = {} }
  local list = { M.DIR .. 'sign_vcp.cdae', M.DIR .. 'sign_vcp.dae' }
  for i, shape in ipairs(list) do
    local side = (i - 1.5) * 6
    local x, y = car.x + fx * 12 + fy * side, car.y + fy * 12 - fx * side
    local z = groundZ(x, y, car.z or 0)
    local item = { shape = shape, exists = fs and fs.fileExists and fs:fileExists(shape) or nil, ground = z ~= nil }
    local ok, id, h, _, turned = pcall(M.make, shape, x, y, z or car.z or 0, M.faceYaw(fx, fy), 'egpsMarkerTest_' .. i)
    item.made = ok and id ~= nil
    item.height = ok and h or nil
    item.turned = ok and turned or nil
    item.error = (not ok) and tostring(id) or ((ok and id == nil) and tostring(h)) or nil
    if ok and id then testIds[#testIds + 1] = id end
    out.items[#out.items + 1] = item
  end
  out.at = os.clock()
  M.lastTest = out
  return out
end
function M.testCleanup()
  if M.lastTest and os.clock() - M.lastTest.at > 60 and #testIds > 0 then
    for _, id in ipairs(testIds) do local o = scenetree.findObjectById(id); if o then pcall(function() o:delete() end) end end
    testIds = {}
  end
end

-- A live marker near the car: its object still there, on the ground at its spot? Put back when not.
local function recheck(key, l, car, force)
  local o = scenetree.findObjectById(l.id)
  if not o then
    live[key], nLive = nil, nLive - 1          -- (gone: made again by the caller's loop)
    M.fixed = M.fixed + 1
    return
  end
  local gz = groundZ(l.x, l.y, car.z or l.z)
  local moveTo = nil
  if gz then
    l.dz = l.z - gz
    if math.abs(l.dz) > M.FIX_DZ_M then moveTo = gz end
  end
  -- (where the object really is: the engine's word, when it gives it)
  local okP, px, py, pz = pcall(function() local p = o:getPosition(); return p.x, p.y, p.z end)
  if okP and type(px) == 'number' and type(py) == 'number' then
    if math.abs(px - l.x) > M.FIX_XY_M or math.abs(py - l.y) > M.FIX_XY_M then moveTo = moveTo or gz or l.z end
    if gz and type(pz) == 'number' and math.abs(pz - gz) > M.FIX_DZ_M then moveTo = gz; l.dz = pz - gz end
  end
  if force then moveTo = moveTo or gz or l.z end
  if moveTo then
    pcall(place, o, l.x, l.y, moveTo, l.yaw)
    l.z, l.dz = moveTo, 0
    M.fixed = M.fixed + 1
  end
end

-- -- clear of every pass of the course ----------------------------------------------------------------------------
-- A course out and back along the same road has two lines a few metres apart; a sign (or a spectator: crowds.lua)
-- beside one of them, on the other's side, stood on the other one, in the middle of the road (the user, 2026-10-25:
-- "the incoming markers ... appear close to the center of the track, specially on two way roads"). So a place is
-- checked against every pass of the course near it, and moved out past them all.
M.GRID_M = 64
M.UNKNOWN_HALF_M = M.SIDE_M - M.EDGE_M      -- the track's half width while the companion has not said
M.PUSH_STEP_M, M.PUSH_MAX_M = 1.0, 30.0
M.SELF_M = 25.0             -- a sign's own pass this near it along the course: not checked (placed beside it already)

local function halfAt(sides, s, default)
  if sides and sides.step then
    local i = math.floor(s / sides.step + 0.5)
    if type(sides.hw[i]) == 'number' and type(sides.ctr[i]) == 'number' then return sides.hw[i], sides.ctr[i] end
  end
  return default or M.UNKNOWN_HALF_M, 0
end
M.halfAt = halfAt

-- The course's segments by grid cell (made once a course frame): every segment listed in the cells it passes.
local function grid(e)
  if e._grid and e._gridN == e.n then return e._grid end
  local G, cells = M.GRID_M, {}
  local function add(cx, cy, i)
    local k = cx * 1000003 + cy
    local c = cells[k]
    if not c then c = {}; cells[k] = c end
    if c[#c] ~= i then c[#c + 1] = i end
  end
  for i = 1, e.n - 1 do
    local ax, ay, bx, by = e.x[i], e.y[i], e.x[i + 1], e.y[i + 1]
    local L = math.sqrt((bx - ax) ^ 2 + (by - ay) ^ 2)
    local k = math.max(1, math.ceil(L / (G / 2)))
    for j = 0, k do
      local t = j / k
      add(math.floor((ax + t * (bx - ax)) / G), math.floor((ay + t * (by - ay)) / G), i)
    end
  end
  e._grid, e._gridN = cells, e.n
  return cells
end

-- Pure: how far (x, y) is past the track's edge, of the nearest pass of the course within r m (math.huge: none). The
-- track there: its half width and its middle (sides: hw, ctr m left of the line; default half width while unknown).
-- selfS, selfR: the course within selfR m of selfS left out (a sign's own pass: placed beside it already).
function M.clearance(e, x, y, sides, default, r, selfS, selfR)
  r = r or 60
  if not e or (e.n or 0) < 2 then return math.huge end
  local cells, G = grid(e), M.GRID_M
  local ring = math.ceil((r + G) / G)
  local gx, gy = math.floor(x / G), math.floor(y / G)
  local best, seen = math.huge, {}
  for cx = gx - ring, gx + ring do
    for cy = gy - ring, gy + ring do
      local c = cells[cx * 1000003 + cy]
      if c then
        for _, i in ipairs(c) do
          if not seen[i] then
            seen[i] = true
            local ax, ay = e.x[i], e.y[i]
            local dx, dy = e.x[i + 1] - ax, e.y[i + 1] - ay
            local L2 = dx * dx + dy * dy
            if L2 > 0 then
              local t = math.max(0, math.min(1, ((x - ax) * dx + (y - ay) * dy) / L2))
              local L = math.sqrt(L2)
              local ss = e.cum[i] + t * (e.cum[i + 1] - e.cum[i])
              if not (selfS and math.abs(ss - selfS) < selfR) then
                local hw, ctr = halfAt(sides, ss, default)
                -- the track's middle there: ctr m left of the line (the right normal is (dy, -dx))
                local mx, my = ax + t * dx - dy / L * ctr, ay + t * dy + dx / L * ctr
                local cl = math.sqrt((mx - x) ^ 2 + (my - y) ^ 2) - hw
                if cl < best then best = cl end
              end
            end
          end
        end
      end
    end
  end
  return best
end

-- Pure: the other stretches of the course (outside sA .. sB) that pass within r m of (x, y): { {s0, s1} } each padded
-- by pad, merged, in order. (A course out and back along one road: its other pass is right here on the ground but far
-- along the course; its track's width is asked for too, so the signs stand clear of it.)
function M.passesNear(e, x, y, r, sA, sB, pad)
  if not e or (e.n or 0) < 2 then return {} end
  local cells, G = grid(e), M.GRID_M
  local ring = math.ceil(r / G) + 1
  local gx, gy = math.floor(x / G), math.floor(y / G)
  local ss, seen = {}, {}
  for cx = gx - ring, gx + ring do
    for cy = gy - ring, gy + ring do
      local c = cells[cx * 1000003 + cy]
      if c then
        for _, i in ipairs(c) do
          if not seen[i] then
            seen[i] = true
            local ax, ay = e.x[i], e.y[i]
            local dx, dy = e.x[i + 1] - ax, e.y[i + 1] - ay
            local L2 = dx * dx + dy * dy
            local t = L2 > 0 and math.max(0, math.min(1, ((x - ax) * dx + (y - ay) * dy) / L2)) or 0
            if (ax + t * dx - x) ^ 2 + (ay + t * dy - y) ^ 2 <= r * r then
              local s = e.cum[i] + t * (e.cum[i + 1] - e.cum[i])
              if s < sA or s > sB then ss[#ss + 1] = s end
            end
          end
        end
      end
    end
  end
  table.sort(ss)
  local out = {}
  for _, s in ipairs(ss) do
    local last = out[#out]
    if last and s - pad <= last[2] then
      last[2] = math.max(last[2], s + pad)
    else
      out[#out + 1] = { math.max(0, s - pad), s + pad }
    end
  end
  return out
end

-- Pure: (x, y) moved out along (nx, ny) (a unit vector, away from the course) until it is need m clear of every pass
-- of the course; nil when it is not within PUSH_MAX_M.
function M.clearOf(e, x, y, nx, ny, need, sides, default, selfS, selfR)
  local step, max = M.PUSH_STEP_M, M.PUSH_MAX_M
  local p = 0
  while p <= max + 1e-9 do
    local px, py = x + nx * p, y + ny * p
    if M.clearance(e, px, py, sides, default, nil, selfS, selfR) >= need then return px, py end
    p = p + step
  end
  return nil
end

-- Pure: a sign's place at s, `side` (+1 right, -1 left) of the course: past the track's edge (its middle shifted to
-- the road's), clear of every other pass of it too. sides nil: the width not known yet (UNKNOWN_HALF_M).
local function besideAt(e, length, s, side, sides)
  local x, y, dx, dy = poly.at(e, math.max(0, math.min(length or e.length or 0, s)))
  local hw, ctr = halfAt(sides, s)
  local lat = -ctr + side * (hw + M.EDGE_M)
  local px, py = x + dy * lat, y - dx * lat
  local qx, qy = M.clearOf(e, px, py, dy * side, -dx * side, M.EDGE_M - 0.05, sides, nil, s, M.SELF_M)
  if qx then return qx, qy end
  return px, py                                    -- (nowhere clear near: where it was)
end
M.besideAt = besideAt

-- Pure: where marker m (planned with s and side) stands given sides = {step, hw = {[i] = m}, ctr = {[i] = m}} (the
-- track's half width and its middle, m left of the course line, every step m: the companion's course_sides): its middle
-- shifted to the road's, then past its edge, and past any other pass of the course there (their widths as known: a
-- sign whose own stretch's width is not known yet still steps clear of another pass's road; the user, 2026-10-25: a
-- sign on a two-lane highway the course comes back along). A banner across the road: nil until its width is known.
function M.placeFor(e, length, m, sides)
  if not (e and e.n and e.n >= 2 and m.s and sides and sides.step) then return nil end
  if m.side ~= 0 then return besideAt(e, length, m.s, m.side, sides) end
  local i = math.floor(m.s / sides.step + 0.5)
  local hw, ctr = sides.hw[i], sides.ctr[i]
  if type(hw) ~= 'number' or type(ctr) ~= 'number' then return nil end
  local x, y, dx, dy = poly.at(e, math.max(0, math.min(length or e.length or 0, m.s)))
  local lat = -ctr                                 -- (to the right: + ; ctr is to the left)
  return x + dy * lat, y - dx * lat
end

-- Every second or so: the markers near the car (crs: course.lua's instance, framed for this anchor).
function M.update(crs, anchor, car)
  if M.failed and M.failedAt and os.clock() - M.failedAt > M.RETRY_S then M.failed = nil end   -- (tried again)
  if not M.enabled or M.mode == 'off' or not crs or not anchor or not car or M.failed then
    if nLive > 0 then M.clear() end
    planned.course = nil
    return
  end
  if planned.course ~= crs or planned.anchor ~= anchor or planned.mode ~= M.mode then
    M.clear()
    M.fixed = 0
    local e = crs.e and crs.e.anchor == anchor and crs.e or nil
    planned = { course = crs, anchor = anchor, mode = M.mode,
                list = M.plan(e, crs.track.waypoints, crs.length, crs.closed,
                              { mode = M.mode, zones = crs.track.zones }) }
  end
  -- the track's width along the course known (more of it): the signs placed beside it, standing ones moved
  local sides = crs.sides
  if sides and planned.sidesV ~= sides.version then
    planned.sidesV = sides.version
    local e = crs.e and crs.e.anchor == anchor and crs.e or nil
    local r2 = M.REPLACE_M * M.REPLACE_M
    for _, m in ipairs(planned.list) do
      local nx, ny
      if (m.x - car.x) ^ 2 + (m.y - car.y) ^ 2 < r2 then nx, ny = M.placeFor(e, crs.length, m, sides) end
      if nx and (math.abs(nx - m.x) > M.MOVE_M or math.abs(ny - m.y) > M.MOVE_M) then
        m.x, m.y = nx, ny
        local l = live[m.key]
        if l then l.x, l.y, l.dz = nx, ny, nil; l.moveNow = true end
      end
    end
  end
  if not scenetree or not scenetree.MissionGroup then return end
  M.ensureMaterials()
  local made_, tries = 0, 0
  local sure2 = M.SURE_M * M.SURE_M
  for _, m in ipairs(planned.list) do
    local dx, dy = m.x - car.x, m.y - car.y
    local d2 = dx * dx + dy * dy
    m.dist = math.sqrt(d2)
    local l = live[m.key]
    if l then
      if d2 > M.DESPAWN_M * M.DESPAWN_M then
        remove(m.key)
      elseif d2 < sure2 or l.moveNow then
        local force = l.moveNow
        l.moveNow = nil
        recheck(m.key, l, car, force)
      end
    end
    if not live[m.key] and d2 < M.SPAWN_M * M.SPAWN_M and made_ < M.PER_UPDATE and tries < M.TRIES_PER_UPDATE then
      tries = tries + 1                 -- (far out, ground not there yet: a few looked for each update, not them all)
      local z = groundZ(m.x, m.y, car.z or 0)
      if z then                         -- (the ground there not loaded yet: tried again next time)
        local ok, id = pcall(spawn, m, z)
        if ok then
          live[m.key] = { id = id, x = m.x, y = m.y, z = z, yaw = m.yaw }
          nLive, made_ = nLive + 1, made_ + 1
        else
          M.failed, M.failedAt = tostring(id), os.clock()
          if log then log('E', 'offroadCompanion', 'markers: ' .. M.failed) end
          M.clear()
          return
        end
      end
    end
  end
end

function M.status()
  local near, d = nil, math.huge
  local nGates = 0
  for _, m in ipairs(planned.list or {}) do
    if m.gate then
      nGates = nGates + 1
      if m.dist and m.dist < d then near, d = m, m.dist end
    end
  end
  local bad = {}
  for _, why in pairs(shapeBad) do bad[#bad + 1] = why end
  local t = M.lastTest
  local l = near and live[near.key]
  return { live = nLive, planned = #(planned.list or {}), gates = nGates, mode = M.mode, failed = M.failed,
           placed = M.placed or 0, fixed = M.fixed, turned = M.turned,
           shape = shapeOf.sign_vcp or shapeOf.stake, bad = bad, lowHeight = M.lowHeight,
           test = t and { items = t.items, materials = t.materials } or nil,
           nearest = near and { kind = near.gate, dist = math.floor(d + 0.5), live = l ~= nil,
                                dz = l and l.dz and math.floor(l.dz * 10 + 0.5) / 10 or nil } or nil }
end

return M
