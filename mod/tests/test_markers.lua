-- luajit test_markers.lua (from mod/tests): course signs placed, turned to face the drivers, streamed around the car,
-- put back on the ground when they were placed wrong far away, materials made once.
package.path = '../offroad_companion/lua/ge/extensions/?.lua;' .. package.path
local pass, fail = 0, 0
local function check(cond, name) if cond then pass = pass + 1 else fail = fail + 1; print('FAIL: ' .. name) end end
local function near(a, b, eps) return math.abs(a - b) < (eps or 1e-6) end

function vec3(x, y, z) return { x = x, y = y, z = z } end
function log() end
local objects, nextId, deleted = {}, 0, 0
local function newObj(class)
  nextId = nextId + 1
  local o = { class = class, fields = {}, id = nextId }
  function o:setField(k, _, v) self.fields[k] = v end
  function o:setPosition(p) self.pos = p end
  function o:setTransform(m) self.pos = m.pos; self.yaw = m.euler and m.euler.z end
  function o:getPosition() return self.pos end
  function o:registerObject(name) self.name = name; objects[name] = self end
  function o:getID() return self.id end
  function o:delete() objects[self.name] = nil; deleted = deleted + 1 end
  return o
end
function createObject(class) return newObj(class) end
function MatrixF()
  local m = {}
  function m:setFromEuler(e) self.euler = e end
  function m:setPosition(p) self.pos = p end
  return m
end
scenetree = { MissionGroup = { addObject = function() end },
  findObject = function(name) return objects[name] end,
  findObjectById = function(id) for _, o in pairs(objects) do if o.id == id then return o end end end }
-- the ground: 2 m under the ray's start unless set otherwise; far from the car (past `real`) a sunk far tile 30 m lower
local groundLoaded, groundAt, carX, real = true, 0, 0, math.huge
function castRayStatic(from, dir, len)
  if not groundLoaded then return nil end
  local z = groundAt
  if math.abs(from.x - carX) > real then z = groundAt - 30 end
  return from.z - z
end

local poly = require('offroadCompanion/poly')
local markers = require('offroadCompanion/markers')

local function byModel(plan)
  local by = {}
  for _, m in ipairs(plan) do by[m.model] = (by[m.model] or 0) + 1 end
  return by
end

-- a 30 km straight course east, VCPs at 5 km and 20 km, a checkpoint at 12 km, a danger at 21 km, a finish
local xs, ys = {}, {}
for i = 0, 300 do xs[#xs + 1], ys[#ys + 1] = i * 100, 0 end
local e = poly.fromXY(xs, ys)
e.length = e.cum[#e.cum]
local wps = { { kind = 'start', s = 0, off = 0 }, { kind = 'vcp', s = 5000, off = 10 }, { kind = 'racemile', s = 8000 },
              { kind = 'checkpoint', s = 12000, off = 0 }, { kind = 'vcp', s = 20000, off = 2 },
              { kind = 'danger', s = 21000 }, { kind = 'finish', s = 30000 } }
local plan = markers.plan(e, wps, 30000, false, { mode = 'checkpoints' })
local by = byModel(plan)
check(by.sign_vcp == 4 and by.sign_cp == 2, 'a VCP board both sides at each VCP, a STOP sign both sides at the checkpoint')
check(by.banner_start == 1 and by.banner_finish == 1, 'a banner across the course at the start and the finish')
check(by.sign_danger == nil and not by.arrow1_l, 'checkpoints mode: no danger signs, no arrows')
local v
for _, m in ipairs(plan) do if m.model == 'sign_vcp' then v = m; break end end
check(near(v.x, 5000) and near(math.abs(v.y), markers.SIDE_M), 'VCP boards either side of the line')
-- driving east (+x) the board must face west (-x): the model faces -y (south), so it is turned 90 degrees clockwise
check(near(v.yaw, -math.pi / 2), 'turned to face the drivers coming: ' .. v.yaw)
check(near(markers.faceYaw(0, 1), 0) and near(markers.faceYaw(0, -1), math.pi) or near(markers.faceYaw(0, -1), -math.pi),
      'north: not turned; south: turned around')
local sx = {}
for _, m in ipairs(plan) do
  if m.model == 'stake' then sx[#sx + 1] = math.floor(m.x + 0.5); check(m.y < 0, 'stake right of the line') end
end
check(table.concat(sx, ',') == '8000,16000,24000', 'stakes every 8 km, none within 1.5 km of a gate: ' .. table.concat(sx, ','))
local nGate = 0
for _, m in ipairs(markers.plan(e, { { kind = 'start', s = 0 }, { kind = 'finish', s = 30000 } }, 30000, true)) do
  if m.gate then nGate = nGate + 1 end
end
check(nGate == 1, 'a circuit: the start banner only')
local off = markers.plan(e, { { kind = 'vcp', s = 100, off = 2000, _x = 7, _y = 9 } }, 30000, false)
check(#off >= 1 and off[1].model == 'sign_vcp' and off[1].x == 7 and off[1].y == 9, 'a VCP far off the line: where the file puts it')

-- full: arrows at the turns (on the inside, before them), danger boards, speed zone signs
do
  -- east 1 km, a right-angle turn right (south) 1 km, then a gentle 30 degree left
  local X, Y = {}, {}
  for i = 0, 100 do X[#X + 1], Y[#Y + 1] = i * 10, 0 end
  for i = 1, 100 do X[#X + 1], Y[#Y + 1] = 1000, -i * 10 end
  local a = math.rad(-90 + 30)
  for i = 1, 100 do X[#X + 1], Y[#Y + 1] = 1000 + math.cos(a) * i * 10, -1000 + math.sin(a) * i * 10 end
  local f = poly.fromXY(X, Y)
  f.length = f.cum[#f.cum]
  local p = markers.plan(f, { { kind = 'danger', s = 500, off = 0 } }, f.length, false,
                         { mode = 'full', zones = { { s0 = 1200, s1 = 1600 } } })
  local b = byModel(p)
  check(b.sign_danger == 2, 'DANGER AHEAD both sides')
  check(b.sign_zone == 2 and b.sign_zone_end == 2, 'SPEED ZONE and RESUME RACE SPEED both sides')
  local arrows = {}
  for _, m in ipairs(p) do if m.model:find('^arrow') then arrows[#arrows + 1] = m end end
  check(#arrows == 2, 'an arrow at each turn: ' .. #arrows)
  local r = arrows[1]
  check(r and r.model == 'arrow3_r', 'the right angle: two arrows on a pink board, right: ' .. tostring(r and r.model))
  check(r and r.x < 1000 and r.x > 900 and r.y < 0, 'before the turn, on its inside (right)')
  local l = arrows[2]
  check(l and l.model == 'arrow1_l', 'the gentle left: one arrow: ' .. tostring(l and l.model))
  for _, m in ipairs(p) do if m.key == 'D1R' then check(near(m.x, 500 - markers.DANGER_BEFORE_M), 'danger board ~150 ft before') end end
end

-- streaming around the car
local anchor = {}
local crs = { e = { anchor = anchor, x = e.x, y = e.y, cum = e.cum, n = e.n, length = 30000 }, track = { waypoints = wps },
              length = 30000 }
local function update(x) carX = x; markers.update(crs, anchor, { x = x, y = 0, z = 10 }) end
update(4700)
local st = markers.status()
check(st.live == 2 and st.planned == #plan and st.mode == 'checkpoints', 'the VCP boards near the car made: ' .. st.live)
check(objects.egps_sign_vcp and objects.egps_sign_vcp.fields.colorMap == '/art/offroadcompanion/sign_vcp.png',
      'its material made, pointing at the texture')
check(objects.egps_ruts and objects.egps_ruts.fields.translucent == '1', 'the wheel ruts material made')
local function posts(prefix)
  local out = {}
  for _, o in pairs(objects) do if o.class == 'TSStatic' and o.name:find('^' .. (prefix or 'egpsMarker_')) then out[#out + 1] = o end end
  return out
end
local post = posts()[1]
check(post.fields.shapeName == '/art/offroadcompanion/sign_vcp.cdae' and post.fields.collisionType == 'None', 'a non-colliding sign')
check(near(post.pos.z, 0), 'on the ground')
check(post.yaw and near(post.yaw, math.pi / 2), 'turned (the engine takes the angle clockwise): ' .. tostring(post.yaw))
check(st.turned == true, 'turned reported')
update(4700)
check(markers.status().live == 2, 'nothing more near')
-- the track's width known (the companion's course_sides): a road 8 m wide whose middle is 2 m left of the course line
-- (a dirt road the course follows off its middle: the user's arrow stood on it, 2026-10-22)
crs.sides = { step = 10, hw = { [500] = 4.0 }, ctr = { [500] = 2.0 }, version = 1 }
update(4700)
local ys = {}
for _, o in ipairs(posts()) do ys[#ys + 1] = math.floor(o.pos.y * 10 + 0.5) / 10 end
table.sort(ys)
check(#ys == 2 and near(ys[1], -3.5) and near(ys[2], 7.5),
      'standing boards moved beside the road, 1.5 m past each edge: ' .. table.concat(ys, ', '))
check(markers.placeFor(e, 30000, { s = 5000, side = 0 }, crs.sides) == 5000, 'a banner across the road\'s middle')
local bx, by = markers.placeFor(e, 30000, { s = 5000, side = 0 }, crs.sides)
check(near(by, 2.0), 'the banner over the road\'s middle: ' .. tostring(by))
local ux, uy = markers.placeFor(e, 30000, { s = 6000, side = 1 }, crs.sides)
local px6, py6 = poly.at(e, 6000)
check(ux and math.abs(math.sqrt((ux - px6) ^ 2 + (uy - py6) ^ 2) - markers.SIDE_M) < 0.01,
  'width not known there: as planned, SIDE_M beside the line')
check(markers.placeFor(e, 30000, { s = 6000, side = 0 }, crs.sides) == nil, 'a banner there: its planned place')
-- out and back on a two-way road (the user, 2026-10-25: "the incoming markers ... appear close to the center of the
-- track, specially on two way roads"): east along y = 0, back west along y = 5; every sign past both passes' edges
do
  local X, Y = {}, {}
  for i = 0, 40 do X[#X + 1], Y[#Y + 1] = i * 100, 0 end
  for i = 0, 40 do X[#X + 1], Y[#Y + 1] = 4000 - i * 100, 5 end
  local f = poly.fromXY(X, Y)
  f.length = f.cum[#f.cum]
  local wps = { { kind = 'start', s = 0, off = 0 }, { kind = 'vcp', s = 1500, off = 0 },
                { kind = 'vcp', s = f.length - 1500, off = 0 }, { kind = 'danger', s = 2500, off = 0 },
                { kind = 'danger', s = f.length - 2500, off = 0 }, { kind = 'finish', s = f.length, off = 0 } }
  -- the road: 4 m each side of y = 2.5 (both passes' companion widths: half 4, its middle 2.5 m left of each line)
  local sd = { step = 10, hw = {}, ctr = {} }
  for i = 0, 900 do sd.hw[i], sd.ctr[i] = 4.0, 2.5 end
  local function offRoad(name, list, half)
    local bad, n = 0, 0
    for _, m in ipairs(list) do
      if m.side ~= 0 and m.s and m.x > 200 and m.x < 3800 then
        n = n + 1
        -- both passes' tracks: |y - middle| past the half width
        local outY = half and math.min(math.abs(m.y - 2.5) - half, math.huge)
          or math.min(math.abs(m.y - 0) - 4.5, math.abs(m.y - 5) - 4.5)
        if outY < markers.EDGE_M - 0.1 then
          bad = bad + 1
          if bad <= 3 then print(string.format('  %s %s at y %.1f', name, m.model, m.y)) end
        end
      end
    end
    check(n >= 8 and bad == 0, name .. ': every sign off the road (' .. bad .. ' of ' .. n .. ')')
  end
  local list = markers.plan(f, wps, f.length, false, { mode = 'full' })
  offRoad('a two-way road, widths not known', list)
  for _, m in ipairs(list) do
    local nx, ny = markers.placeFor(f, f.length, m, sd)
    if nx then m.x, m.y = nx, ny end
  end
  offRoad('a two-way road, its width known', list, 4.0)
  -- each pass its own track, 4 m each side of its line (the course's track laid twice, overlapping)
  local sd2 = { step = 10, hw = {}, ctr = {} }
  for i = 0, 900 do sd2.hw[i], sd2.ctr[i] = 4.0, 0.0 end
  local list2 = markers.plan(f, wps, f.length, false, { mode = 'full' })
  for _, m in ipairs(list2) do
    local nx, ny = markers.placeFor(f, f.length, m, sd2)
    if nx then m.x, m.y = nx, ny end
  end
  local bad2, n2 = 0, 0
  for _, m in ipairs(list2) do
    if m.side ~= 0 and m.x > 200 and m.x < 3800 then
      n2 = n2 + 1
      if math.min(math.abs(m.y) - 4.0, math.abs(m.y - 5) - 4.0) < markers.EDGE_M - 0.1 then bad2 = bad2 + 1 end
    end
  end
  check(n2 >= 8 and bad2 == 0, 'each pass its own track: every sign off both (' .. bad2 .. ' of ' .. n2 .. ')')
  -- a wide road (a highway, both lanes and wide shoulders: 8 m each side of its middle) known only for the outward
  -- pass (the car is there; the other pass's own width not asked yet): the return's signs still clear of it
  local sd3 = { step = 10, hw = {}, ctr = {} }
  for i = 0, 400 do sd3.hw[i], sd3.ctr[i] = 8.0, 2.5 end           -- (the outward pass: s 0 .. 4000)
  local list3 = markers.plan(f, wps, f.length, false, { mode = 'full' })
  local bad3, n3 = 0, 0
  for _, m in ipairs(list3) do
    local nx, ny = markers.placeFor(f, f.length, m, sd3)
    if nx then m.x, m.y = nx, ny end
    if m.side ~= 0 and m.s > f.length / 2 + 200 and m.x > 200 and m.x < 3800 then
      n3 = n3 + 1
      if math.abs(m.y - 2.5) < 8.0 + markers.EDGE_M - 0.1 then bad3 = bad3 + 1 end
    end
  end
  check(n3 >= 4 and bad3 == 0, 'the return\'s signs (their own width unknown) clear of the known road: ' .. bad3 .. ' of ' .. n3)
  -- the other pass found near the car: far along the course, right here on the ground
  local near = markers.passesNear(f, 1500, 0, 400, 1000, 2000, 300)
  check(#near == 1 and near[1][1] < f.length - 1500 and near[1][2] > f.length - 1500
    and near[1][2] - near[1][1] < 2000, 'the return pass near the car: ' .. (near[1] and (near[1][1] .. '-' .. near[1][2]) or 'none'))
  check(#markers.passesNear(f, 1500, 200, 100, 1000, 2000, 300) == 0, 'none within 100 m off to the side')
  check(#markers.passesNear(e, 5000, 0, 400, 4000, 6000, 300) == 0, 'a course that passes once: none')
  -- and the signs stay near the road: just past its far edge, not pushed off into the desert
  local far = 0
  for _, m in ipairs(list) do if m.side ~= 0 and math.abs(m.y - 2.5) > 4.0 + markers.EDGE_M + 1.5 then far = far + 1 end end
  check(far == 0, 'just past the road\'s edge: ' .. far .. ' farther')
end
crs.sides = nil
update(19600)
check(markers.status().live == 2 and deleted == 2, 'the old boards removed far behind, the next ones made')
groundLoaded = false
update(29600)
check(markers.status().live == 0, 'no ground loaded yet: waits')
groundLoaded = true
update(29600)
check(markers.status().live == 1, 'then the finish banner made')

-- made far away on a sunk far tile (30 m too low): put back on the ground once the car is near (the user,
-- 2026-10-22: only the first VCP showed)
markers.update(nil)
real = 400
update(4450)                                   -- 550 m from the VCP: made, but on the far tile
local p0 = posts()
check(#p0 == 2 and near(p0[1].pos.z, -30), 'made far away: 30 m under the ground')
check(markers.status().nearest.live, 'the nearest VCP is up')
update(4700)                                   -- 300 m: the real ground
local p1 = posts()
check(#p1 == 2 and near(p1[1].pos.z, 0) and near(p1[2].pos.z, 0), 'put back on the ground near the car')
check(markers.status().fixed == 2, 'reported as put back: ' .. markers.status().fixed)
check(p1[1].yaw and near(p1[1].yaw, math.pi / 2), 'still facing the drivers')
real = math.huge
groundAt = 3                                   -- (the ground there changes: a regrade)
update(4800)
check(near(posts()[1].pos.z, 3), 'follows the ground')
groundAt = 0
-- an object that went away is made again
local gone = posts()[1]
gone:delete()
update(4800)
check(#posts() == 2, 'a sign that went away made again')

markers.update(nil)
check(markers.status().live == 0, 'no course: all removed')
markers.setMode('full')
update(4700)
check(markers.status().mode == 'full' and markers.status().planned > #plan, 'full: more signs planned')
markers.setMode(false)
update(4700)
check(markers.status().live == 0 and markers.mode == 'off', 'turned off (the old false): removed')
check(markers.setMode(true) == 'checkpoints' and markers.setMode('nonsense') == 'checkpoints', 'old true / unknown: checkpoints')
local n = 0
for name in pairs(objects) do if name:find('^egps_') then n = n + 1 end end
check(n == #markers.MODELS + 1, 'materials made once each: ' .. n)

-- the .cdae when the mod has it; a model that did not load is reported, and the other file used
markers.clear()
local exists = {}
FS = { fileExists = function(_, p) return exists[p] or p:match('%.png$') ~= nil end }
package.loaded['offroadCompanion/markers'] = nil
local mk = require('offroadCompanion/markers')
exists['/art/offroadcompanion/sign_vcp.cdae'] = true
exists['/art/offroadcompanion/sign_vcp.dae'] = true
exists['/art/offroadcompanion/stake.dae'] = true
check(mk.shape('sign_vcp') == '/art/offroadcompanion/sign_vcp.cdae', 'the .cdae preferred')
check(mk.shape('stake') == '/art/offroadcompanion/stake.dae', 'else the .dae')
local heights = { ['/art/offroadcompanion/sign_vcp.cdae'] = 0.0, ['/art/offroadcompanion/sign_vcp.dae'] = 1.53 }
local refuse = {}
local origNew = createObject
createObject = function(class)
  local o = origNew(class)
  function o:getWorldBox()
    local h = heights[self.fields.shapeName] or 0
    return { getExtents = function() return { x = 0.9, y = 0.1, z = h } end }
  end
  local reg = o.registerObject
  function o:registerObject(name)
    if refuse[self.fields.shapeName] then return false end
    return reg(self, name)
  end
  return o
end
carX = 4700
mk.update(crs, anchor, { x = 4700, y = 0, z = 10 })
local q1 = posts()
check(#q1 == 2 and q1[1].fields.shapeName == '/art/offroadcompanion/sign_vcp.cdae', 'kept though measured 0 m: ' .. #q1)
check(mk.status().lowHeight ~= nil, 'the reading reported')
carX = 19600
mk.update(crs, anchor, { x = 19600, y = 0, z = 10 })
local q2 = posts()
check(#q2 == 2 and math.abs(q2[1].pos.x - 20000) < 1, 'the next VCP placed too: ' .. #q2)
mk.clear()
refuse['/art/offroadcompanion/sign_vcp.cdae'] = true
package.loaded['offroadCompanion/markers'] = nil
mk = require('offroadCompanion/markers')
carX = 4700
mk.update(crs, anchor, { x = 4700, y = 0, z = 10 })
local q3 = posts()
check(#q3 == 2 and q3[1].fields.shapeName == '/art/offroadcompanion/sign_vcp.dae', 'refused .cdae: the .dae used')
check(#mk.status().bad == 1, 'the refusal reported')
refuse = {}
-- the test button: a VCP board of each file ahead of the car, facing it
local t = mk.test({ x = 0, y = 0, z = 10 }, 90)
check(#t.items == 2 and t.items[1].made and t.items[1].height == 0 and t.items[2].height == 1.53, 'test boards made')
local tp = objects.egpsMarkerTest_2
check(tp and near(tp.pos.x, 12) and near(tp.pos.y, -3), '12 m ahead (east), 3 m right')
check(tp and near(tp.yaw, math.pi / 2) and t.items[2].turned, 'facing the car')
check(mk.status().test and #mk.status().test.items == 2, 'test result in the status')
createObject = origNew
FS = nil
-- (1.7.12, the user 2026-11-12: signs and spectators jumping into the air) the ground is the terrain the cars drive on
-- where it is there, not the first static collision a ray from high above meets (after a rebase the old place's
-- collision stays a while over the new ground): a layer 20 m up is passed by
do
  local oldRay, oldCt = castRayStatic, core_terrain
  castRayStatic = function(from, dir, len)
    if from.z > 20 then return from.z - 20 end           -- (a ghost layer 20 m up)
    return from.z - 0                                     -- (the terrain at 0)
  end
  check(math.abs(mk.groundZ(10, 10, 0) - 20) < 1e-9, 'no terrain known: the first collision, as before')
  core_terrain = { getTerrainHeight = function() return 0 end }
  check(math.abs(mk.groundZ(10, 10, 0)) < 1e-9, 'the terrain known and there: its height, under the layer')
  castRayStatic = function(from, dir, len) return len + 1 end      -- (no collision there yet)
  check(mk.groundZ(10, 10, 0) == nil, 'the terrain known but no collision there yet: nothing (tried again later)')
  castRayStatic, core_terrain = oldRay, oldCt
end
print(string.format('%d passed, %d failed', pass, fail))
os.exit(fail == 0 and 0 or 1)
