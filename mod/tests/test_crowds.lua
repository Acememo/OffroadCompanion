-- luajit test_crowds.lua (from mod/tests): spectators where people gather at a desert race, the same for everyone,
-- past the track's edge, facing the course, turning to watch the car, streamed around it.
package.path = '../offroad_companion/lua/ge/extensions/?.lua;' .. package.path
local pass, fail = 0, 0
local function check(cond, name) if cond then pass = pass + 1 else fail = fail + 1; print('FAIL: ' .. name) end end

function vec3(x, y, z) return { x = x, y = y, z = z } end
function log() end
local objects, nextId, deleted = {}, 0, 0
function createObject(class)
  nextId = nextId + 1
  local o = { class = class, fields = {}, id = nextId }
  function o:setField(k, _, v) self.fields[k] = v end
  function o:setPosition(p) self.pos = p end
  function o:setTransform(m) self.pos = m.pos; self.yaw = m.euler and -m.euler.z end
  function o:getPosition() return self.pos end
  function o:registerObject(name) self.name = name; objects[name] = self end
  function o:getID() return self.id end
  function o:delete() objects[self.name] = nil; deleted = deleted + 1 end
  return o
end
function MatrixF()
  local m = {}
  function m:setFromEuler(e) self.euler = e end
  function m:setPosition(p) self.pos = p end
  return m
end
scenetree = { MissionGroup = { addObject = function() end },
  findObject = function(name) return objects[name] end,
  findObjectById = function(id) for _, o in pairs(objects) do if o.id == id then return o end end end }
function castRayStatic(from) return from.z - 0 end

local poly = require('offroadCompanion/poly')
local crowds = require('offroadCompanion/crowds')
local markers = require('offroadCompanion/markers')

-- 1. the hash: in [0, 1), spread, and fixed (the same numbers on every computer, from integer arithmetic only)
local lo, hi, sum = 1, 0, 0
for i = 1, 5000 do
  local h = crowds.hash(i * 7919, -i * 31, i % 13)
  lo, hi, sum = math.min(lo, h), math.max(hi, h), sum + h
end
check(lo >= 0 and hi < 1 and math.abs(sum / 5000 - 0.5) < 0.02, 'hash in [0, 1), spread: ' .. sum / 5000)
check(crowds.hash(12345, 678, 9) == crowds.hash(12345, 678, 9), 'hash the same twice')
local golden = string.format('%.12f %.12f %.12f', crowds.hash(0, 0, 0), crowds.hash(123456789, -42, 7),
  crowds.hash(4294967295, 99, 3))
check(golden == '0.551037016790 0.297163970536 0.484450553311' or print('hash golden: ' .. golden) or false,
  'hash fixed (golden values)')

-- 2. a 20 km course east with a hairpin at 9 km; start, a checkpoint at 6 km, danger at 14 km, finish
local xs, ys = {}, {}
for i = 0, 90 do xs[#xs + 1], ys[#ys + 1] = i * 100, 0 end
for k = 1, 12 do local a = math.pi * k / 12; xs[#xs + 1], ys[#ys + 1] = 9000 + 60 * math.sin(a), 60 - 60 * math.cos(a) end
for i = 1, 110 do xs[#xs + 1], ys[#ys + 1] = 9000 - i * 100, 120 end
local e = poly.fromXY(xs, ys)
e.length = e.cum[#e.cum]
local L = e.length
local wps = { { kind = 'start', s = 0, off = 0 }, { kind = 'checkpoint', s = 6000, off = 0 },
              { kind = 'vcp', s = 3000, off = 0 }, { kind = 'danger', s = 14000, off = 0 },
              { kind = 'finish', s = L, off = 0 } }
local extra = { { s = 2500, kind = 'jump', size = 0.8 }, { s = 2900, kind = 'crossing' }, { s = 12100, kind = 'crossing' },
                { s = 6100, kind = 'jump', size = 0.5 } }
local sp = crowds.spots(e, wps, L, false, extra, 'some')
local kinds = {}
for _, p in ipairs(sp) do kinds[p.kind] = (kinds[p.kind] or 0) + 1 end
check(kinds.start == 1 and kinds.finish == 1 and kinds.checkpoint == 1, 'the gates always')
check(kinds.vcp == nil, 'no crowd at a VCP (a GPS point, nobody there)')
check(kinds.jump == 1, 'the jump at 2.5 km (the one at 6.1 km is too near the checkpoint)')
check(kinds.crossing == 1, 'one crossing: 2.9 km is in the jump\'s stretch, the jump wins; 12.1 km has its own')
check(kinds.danger == 1 and kinds.hairpin == 1, 'the danger spot and the hairpin: ' .. tostring(kinds.danger) .. ' '
  .. tostring(kinds.hairpin))
local hp
for _, p in ipairs(sp) do if p.kind == 'hairpin' then hp = p end end
check(hp and hp.side == -1, 'the hairpin\'s crowd on its inside (a left turn: the left)')
local bins = {}
for _, p in ipairs(sp) do
  if p.kind ~= 'start' and p.kind ~= 'finish' and p.kind ~= 'checkpoint' then
    local b = math.floor(p.s / crowds.BIN_M.some)
    check(not bins[b], 'one crowd a stretch at most')
    bins[b] = true
  end
end
local lots = crowds.spots(e, wps, L, false, extra, 'lots')
check(#lots >= #sp, 'Lots: as many places or more')
check(#crowds.spots(e, wps, L, false, extra, 'off') == 0, 'Off: none')
-- a stretch whose jumps are not all known yet: no crowd there (it would differ from someone else's)
local partial = crowds.spots(e, wps, L, false, extra, 'some', function(b) return b ~= 1 end)
local hasJump = false
for _, p in ipairs(partial) do if p.kind == 'jump' then hasJump = true end end
check(not hasJump, 'an incomplete stretch: no crowd yet')
-- a window around the car: the same spots there as for the whole course
local win = crowds.spots(e, wps, L, false, extra, 'some', nil, { 2000, 7000 })
local whole = {}
for _, p in ipairs(sp) do whole[p.kind .. '@' .. p.s] = true end
local inWin = 0
for _, p in ipairs(win) do
  check(whole[p.kind .. '@' .. p.s], 'a window\'s spot is the whole course\'s: ' .. p.kind .. '@' .. p.s)
  inWin = inWin + 1
end
check(inWin >= 2, 'the window has its spots')

-- 3. a crowd: past the edge, facing the course, the same every time
local start = sp[1]
local g = crowds.group(start, 1)
local g2 = crowds.group(start, 1)
check(#g == #g2 and g[5].key == g2[5].key and g[5].lat == g2[5].lat, 'the same crowd every time')
local fans, both = 0, { [1] = 0, [-1] = 0 }
for _, o in ipairs(g) do
  if o.fan then fans = fans + 1; both[o.side] = both[o.side] + 1 end
  check(o.lat >= crowds.KINDS.start.setback, 'past the edge plus the setback')
end
check(fans >= 24 and both[1] > 0 and both[-1] > 0, 'a big crowd both sides of the start: ' .. fans)
local big = 0
for _, o in ipairs(crowds.group(start, crowds.SCALE.lots)) do if o.fan then big = big + 1 end end
check(big > fans, 'Lots: more people')
local sides = { step = 10, hw = {}, ctr = {} }
for i = 0, 2000 do sides.hw[i], sides.ctr[i] = 6.0, 2.0 end
for _, o in ipairs(g) do
  o.kind = 'start'
  local x, y, yaw = crowds.placeOf(e, L, o, sides)
  local cx, cy = poly.at(e, math.max(0, math.min(L, o.s)))
  local mid = cy + 2.0                     -- (the road's middle: 2 m left of the line, which runs east: north)
  local d = math.abs(y - mid)
  check(d >= 6.0 + 2.0, 'stands past the road\'s edge (half width 6): ' .. d)
  -- the model's front (-y turned by yaw: (sin yaw, -cos yaw)) points toward the course
  local fx, fy = math.sin(yaw), -math.cos(yaw)
  local toward = (mid - y) * fy
  if not o.fan then toward = 1 end
  check(toward > 0, 'faces the course')
end

-- 3b. nobody on the course (the user, 2026-10-25: "the spectators are blocking the route on some instances"): a tight
-- hairpin's inside is its other leg; an out-and-back passes itself a few metres away
local function clearAll(name, cxs, cys, extraSpots, sd)
  local ce = poly.fromXY(cxs, cys)
  ce.length = ce.cum[#ce.cum]
  local cw = { { kind = 'start', s = 0, off = 0 }, { kind = 'finish', s = ce.length, off = 0 } }
  local placed, left, bad = 0, 0, 0
  for _, spot in ipairs(crowds.spots(ce, cw, ce.length, false, extraSpots, 'lots')) do
    for _, o in ipairs(crowds.group(spot, crowds.SCALE.lots)) do
      o.kind = spot.kind
      local x, y = crowds.placeOf(ce, ce.length, o, sd)
      if x then
        placed = placed + 1
        -- brute force: the nearest point of the track's middle (ctr m left of the line), every segment
        local hw, ctr = 4.0, 0.0
        if sd then hw, ctr = 6.0, 1.0 end
        local best = math.huge
        for i = 1, ce.n - 1 do
          local _, t = poly.nearest(ce, x, y, i, i + 1)
          local dx, dy = ce.x[i + 1] - ce.x[i], ce.y[i + 1] - ce.y[i]
          local L = math.sqrt(dx * dx + dy * dy)
          local mx, my = ce.x[i] + t * dx - dy / L * ctr, ce.y[i] + t * dy + dx / L * ctr
          local d = math.sqrt((mx - x) ^ 2 + (my - y) ^ 2)
          if d < best then best = d end
        end
        if best < hw + 1.5 then
          bad = bad + 1
          if bad <= 3 then print(string.format('  %s %s at %.1f m from the line', name, o.model, best)) end
        end
      else
        left = left + 1
      end
    end
  end
  check(bad == 0, name .. ': nobody on the course (' .. bad .. ' of ' .. placed .. ')')
  return placed, left
end
local hx, hy = {}, {}
for i = 0, 60 do hx[#hx + 1], hy[#hy + 1] = i * 50, 0 end                         -- 3 km east ...
for k = 1, 11 do local a = math.pi * k / 12; hx[#hx + 1], hy[#hy + 1] = 3000 + 9 * math.sin(a), 9 - 9 * math.cos(a) end
for i = 0, 60 do hx[#hx + 1], hy[#hy + 1] = 3000 - i * 50, 18 end                 -- ... a hairpin, legs 18 m apart, back
local placed, left = clearAll('a tight hairpin', hx, hy, {})
check(placed > 0, 'its crowds still there: ' .. placed .. ' placed, ' .. left .. ' left out')
local sd = { step = 10, hw = {}, ctr = {} }
for i = 0, 1000 do sd.hw[i], sd.ctr[i] = 6.0, 1.0 end
clearAll('a tight hairpin, a wide track', hx, hy, {}, sd)
local ox, oy = {}, {}
for i = 0, 80 do ox[#ox + 1], oy[#oy + 1] = i * 50, 0 end                         -- out 4 km ...
for i = 0, 80 do ox[#ox + 1], oy[#oy + 1] = 4000 - i * 50, 14 end                 -- ... back 14 m beside it
clearAll('an out-and-back', ox, oy, { { s = 1200, kind = 'jump', size = 1 }, { s = 6500, kind = 'crossing' } })
-- the ordinary course: nobody left out
local all = 0
for _, o in ipairs(g) do if crowds.placeOf(e, L, o, sides) then all = all + 1 end end
check(all == #g, 'an open start: every one placed')

-- 4. watching the car: turns toward it, at most so far, and at most so fast
local base = markers.faceYaw(0, -1)        -- (facing +y: a spectator south of the course)
local y1 = crowds.watchYaw(0, 0, base, base, 50, 20, 0.1)
check(y1 ~= base and math.abs(y1 - base) <= math.rad(crowds.TURN_DEG_S) * 0.1 + 1e-9, 'turns toward the car, smoothly')
local y9 = base
for _ = 1, 100 do y9 = crowds.watchYaw(0, 0, base, y9, 50, 20, 0.1) end
local fx, fy = math.sin(y9), -math.cos(y9)
check(fx * 50 + fy * 20 > 0.95 * math.sqrt(50 * 50 + 20 * 20), 'then looks at it')
local yb = crowds.watchYaw(0, 0, base, y9, 5000, 0, 10)
check(math.abs(yb - base) < 1e-9, 'and back to the course once it has gone')

-- 5. in the world: only near the car, a few at a time, taken away behind it, turning as it passes
local crs = { e = e, track = { waypoints = wps }, length = L, closed = false, s = 0, spots = extra,
              spotRanges = { { -1000, 30000 } }, spotsVersion = 1 }
e.anchor = 'A'
crowds.setLevel('some')
local car = { x = 0, y = -30, z = 0 }
crowds.update(crs, 'A', car)
local n1 = crowds.status().live
check(n1 > 0 and n1 <= crowds.PER_UPDATE, 'made a few at a time: ' .. n1)
for _ = 1, 10 do crowds.update(crs, 'A', car) end
local st = crowds.status()
check(st.live > 20 and st.live < st.planned, 'the start\'s crowd made, the far ones not: ' .. st.live .. '/' .. st.planned)
local statics = 0
for _, o in pairs(objects) do
  if o.class == 'TSStatic' then statics = statics + 1; check(o.fields.collisionType == 'None', 'nothing collides') end
end
check(statics > 0, 'spectators in the scene')
-- the car comes by: the fans near it turn
local l0 = {}
for k, l in pairs(crowds._live()) do l0[k] = l.yaw end
car = { x = 40, y = 0, z = 0 }
for _ = 1, 30 do crowds.tick(0.1, car) end
local turned = 0
for k, l in pairs(crowds._live()) do if l.fan and math.abs(l.yaw - l0[k]) > 0.05 then turned = turned + 1 end end
check(turned > 10, 'fans turn to watch the car: ' .. turned)
-- far away: the start's crowd taken away
crs.s = 9000
car = { x = 9000, y = 60, z = 0 }
for _ = 1, 20 do crowds.update(crs, 'A', car) end
local nearStart = 0
for _, l in pairs(crowds._live()) do if l.x < 1000 then nearStart = nearStart + 1 end end
check(nearStart == 0 and deleted > 0, 'the start\'s crowd gone behind the car')
check(crowds.status().live > 0, 'the hairpin\'s crowd made')
crowds.setLevel('off')
crowds.update(crs, 'A', car)
check(crowds.status().live == 0, 'Off: all taken away')
check(markers.MATERIALS.egps_fan_a and markers.MATERIALS.egps_canopy_red, 'their materials made with the markers\'')

-- 6. the companion's answers merged: spots once each, the stretches covered joined, a new version when anything changed
local c2 = {}
check(crowds.merge(c2, { spots = { { s = 500, kind = 'jump', size = 0.3 } }, spotsFrom = -1000, spotsTo = 2500 }),
  'the first answer: changed')
check(#c2.spots == 1 and c2.spotRanges[1][1] == -1000 and c2.spotRanges[1][2] == 2500, 'its spot and stretch')
check(not crowds.merge(c2, { spots = { { s = 500, kind = 'jump', size = 0.3 } }, spotsFrom = 0, spotsTo = 2000 }),
  'the same again: nothing changed')
check(crowds.merge(c2, { spots = { { s = 3100, kind = 'crossing' } }, spotsFrom = 2000, spotsTo = 5000 }),
  'more ahead: changed')
check(#c2.spots == 2 and #c2.spotRanges == 1 and c2.spotRanges[1][2] == 5000, 'the stretches joined')
check(crowds.covered(c2.spotRanges, 1600, 3200) and not crowds.covered(c2.spotRanges, 4800, 6400), 'covered or not')
check(not crowds.merge(c2, { hw = {} }), 'an answer without spots (an older companion): nothing')

-- 7. after dark (the user, 2026-10-25: "add some lights to the spectators to make it more immersive at night")
-- the sun: high at noon, under the horizon at midnight; Ensenada on 25 October (UTC-7): up at 17:00, down by 18:30
local function tod(hh, mm, extra)
  local t = { time = ((hh + mm / 60) / 24 - 0.5) % 1 }
  for k, v in pairs(extra or {}) do t[k] = v end
  return t
end
check(crowds.sunElevation(tod(12, 0), 0, 0) > 80, 'noon at the equator: overhead')
check(crowds.sunElevation(tod(0, 0), 31.9, -116.6) < -30, 'midnight: well down')
local ens = { year = 2026, month = 10, day = 25, utcOffset = -7, latitude = 31.87, longitude = -116.6 }
local e17, e1830 = crowds.sunElevation(tod(17, 0, ens)), crowds.sunElevation(tod(18, 30, ens))
check(e17 > 5 and e1830 < -2, 'Ensenada, 25 October: 17:00 up (' .. string.format('%.1f', e17) .. '), 18:30 down ('
  .. string.format('%.1f', e1830) .. ')')
check(crowds.sunElevation(tod(18, 30, { month = 6, day = 21, utcOffset = -7, latitude = 31.87, longitude = -116.6 })) > 5,
  'in June it is still up at 18:30')
-- the night things: a lantern under each canopy (the same place), a light tower at the gates, a campfire elsewhere
local function byModel(objs, prefix)
  local out = {}
  for _, o in ipairs(objs) do if o.model:sub(1, #prefix) == prefix then out[#out + 1] = o end end
  return out
end
local gs = crowds.group(start, 1)
local cans, lans = byModel(gs, 'canopy'), byModel(gs, 'lantern')
check(#cans > 0 and #lans == #cans, 'a lantern for every canopy: ' .. #lans .. ' / ' .. #cans)
local same = true
for _, ln in ipairs(lans) do
  local found = false
  for _, c in ipairs(cans) do
    if c.side == ln.side and c.lat == ln.lat and c.along == ln.along and c.turn == ln.turn then found = true end
  end
  same = same and found and ln.night and ln.light == 'lantern'
end
check(same, 'each under its canopy, lit, at night only')
check(#byModel(gs, 'light_tower') == 2 and #byModel(gs, 'lamps') == 2, 'two light towers at the start (both sides)')
check(not byModel(gs, 'light_tower')[1].night and byModel(gs, 'lamps')[1].night, 'the tower stands by day, its lamps lit at night')
check(#byModel(gs, 'campfire') == 0, 'no campfire at the start')
local hpSpot
for _, p in ipairs(sp) do if p.kind == 'hairpin' or p.kind == 'jump' then hpSpot = p end end
local gh = crowds.group(hpSpot, 1)
check(#byModel(gh, 'campfire') >= 1 and #byModel(gh, 'flames') == #byModel(gh, 'campfire'), 'a campfire with its flames')
check(#byModel(gh, 'light_tower') == 0, 'no light tower there')
-- placed alike: the flames on their fire, the lamps on their tower, the lantern under its canopy (also when moved)
local pairsOk, nPairs = true, 0
local function samePlace(p, q, kind)
  p.kind, q.kind = kind, kind
  local ax, ay = crowds.placeOf(e, L, p, sides)
  local bx, by = crowds.placeOf(e, L, q, sides)
  nPairs = nPairs + 1
  return ax and bx and math.abs(ax - bx) < 1e-6 and math.abs(ay - by) < 1e-6
end
for _, ln in ipairs(lans) do
  for _, c in ipairs(cans) do
    if c.side == ln.side and c.along == ln.along then pairsOk = pairsOk and samePlace(c, ln, 'start') end
  end
end
for _, grp in ipairs({ { gs, 'light_tower', 'lamps', 'start' }, { gh, 'campfire', 'flames', hpSpot.kind } }) do
  local a, b = byModel(grp[1], grp[2]), byModel(grp[1], grp[3])
  for i = 1, #a do pairsOk = pairsOk and samePlace(a[i], b[i], grp[4]) end
end
check(pairsOk and nPairs >= 5, 'lit parts stand exactly on their own (lantern / canopy, lamps / tower, flames / fire): ' .. nPairs)
-- in the world at night: the night things made, a few real lights near the car; by day none
local envTime = tod(0, 30, ens)
core_environment = { getTimeOfDay = function() return envTime end }
crowds.clear()
crowds.setLevel('some')
crowds.setLights('on')
crs.s = 0
local car2 = { x = 0, y = -30, z = 0, lat = 31.87, lon = -116.6 }
for _ = 1, 40 do crowds.update(crs, 'A', car2) end
local function count(class)
  local n = 0
  for _, o in pairs(objects) do if o.class == class then n = n + 1 end end
  return n
end
local st7 = crowds.status()
local towers, lampsOn = 0, 0
for _, o in pairs(objects) do
  local sh = o.fields.shapeName or ''
  if sh:find('light_tower') then towers = towers + 1 end
  if sh:find('/lamps%.') then lampsOn = lampsOn + 1 end
end
check(st7.night == true and st7.sun < 0, 'night: ' .. tostring(st7.sun))
check(towers == 2 and lampsOn == 2, 'the start\'s towers and their lamps: ' .. towers .. ', ' .. lampsOn)
local nl = count('PointLight')
check(nl > 0 and nl <= crowds.MAX_LIGHTS and crowds.status().lit == nl, 'lights near the car: ' .. nl)
local okFields = true
for _, o in pairs(objects) do
  if o.class == 'PointLight' then
    okFields = okFields and o.fields.castShadows == '0' and tonumber(o.fields.radius) > 0 and o.pos and o.pos.z > 0
  end
end
check(okFields, 'no shadows, a reach, above the ground')
-- at most MAX_LIGHTS of them, the nearest
crowds.MAX_LIGHTS = 2
crowds.update(crs, 'A', car2)
check(count('PointLight') == 2 and crowds.status().lit == 2, 'at most MAX_LIGHTS: ' .. count('PointLight'))
crowds.MAX_LIGHTS = 16
crowds.update(crs, 'A', car2)
check(count('PointLight') == nl, 'and back')
-- Bright: the lights made again, stronger
local before = {}
for _, o in pairs(objects) do if o.class == 'PointLight' then before[#before + 1] = tonumber(o.fields.intensity) end end
crowds.setLights('bright')
crowds.update(crs, 'A', car2)
local after = {}
for _, o in pairs(objects) do if o.class == 'PointLight' then after[#after + 1] = tonumber(o.fields.intensity) end end
table.sort(before); table.sort(after)
check(#after == #before and after[#after] > before[#before], 'Bright: stronger lights')
-- the campfires flicker (gently)
local fl = {}
for i = 0, 50 do fl[#fl + 1] = crowds.flicker(i * 0.05, 1.3) end
table.sort(fl)
check(fl[1] >= 0.74 and fl[#fl] <= 1.0001 and fl[#fl] - fl[1] > 0.1, 'a flicker between 0.75 and 1')
-- sunrise: the night things and the lights go
envTime = tod(12, 0, ens)
for _ = 1, 3 do crowds.update(crs, 'A', car2) end
lampsOn = 0
for _, o in pairs(objects) do if (o.fields.shapeName or ''):find('/lamps%.') then lampsOn = lampsOn + 1 end end
check(count('PointLight') == 0 and lampsOn == 0 and crowds.status().night == false, 'day: no lights, no lamps lit')
-- night again, Night lights Off: none
envTime = tod(0, 30, ens)
crowds.setLights('off')
for _ = 1, 3 do crowds.update(crs, 'A', car2) end
check(count('PointLight') == 0, 'Night lights Off: none')
crowds.setLights('on')
-- the crowds that cheer: the middle of each one's people, how many
local ch = crowds.cheers()
check(#ch > 0 and ch[1].n > 0 and ch[1].gate == true and ch[1].key:find('^start:'), 'the start cheers: ' .. #ch)
core_environment = nil
crowds.clear()
-- every model in the mod (its picture, .dae and .cdae), the glowing ones' materials glowing, the cheers there
local missing = {}
for _, n in ipairs(crowds.MODELS) do
  for _, ext in ipairs({ '.png', '.dae', '.cdae' }) do
    local f = io.open('../offroad_companion/art/offroadcompanion/' .. n .. ext, 'rb')
    if f then f:close() else missing[#missing + 1] = n .. ext end
  end
end
check(#missing == 0, 'every model file in the mod: ' .. table.concat(missing, ', '))
local glow = true
for _, n in ipairs(crowds.GLOWING) do
  local found = false
  for _, f in ipairs(markers.MATERIALS['egps_' .. n] or {}) do if f[1] == 'emissive' and f[2] == '1' then found = true end end
  glow = glow and found
end
check(glow, 'the flames, lamps and lanterns glow')
local cs = require('offroadCompanion/crowdsound')
local nsnd = 0
for _, f in ipairs(cs.FILES) do
  local h = io.open('../offroad_companion' .. cs.DIR .. f, 'rb')
  if h then nsnd = nsnd + 1; h:close() end
end
check(nsnd == 3, 'the three cheers in the mod')

-- 8. Lots: the course lined like a Baja race (the user, 2026-10-25: photos; "The closer to urban centers the larger the
-- crowd"): fence, packed people, canopies, parked trucks, longer and denser near towns
local jumpSpot = { s = 2500, kind = 'jump', side = 0, size = 0.8 }
local function tally(objs)
  local c = { fence = 0, people = 0, canopy = 0, vehicle = 0, lantern = 0, flag = 0, tower = 0, n = #objs }
  local lo, hi = math.huge, -math.huge
  local keys, dup = {}, false
  for _, o in ipairs(objs) do
    if keys[o.key] then dup = true end
    keys[o.key] = true
    local m = o.model
    if m == 'fence_orange' then c.fence = c.fence + 1 end
    if o.people then c.people = c.people + o.people; lo, hi = math.min(lo, o.along), math.max(hi, o.along) end
    if m:find('^canopy') then c.canopy = c.canopy + 1 end
    if m:find('^pickup') or m:find('^suv') then c.vehicle = c.vehicle + 1 end
    if m == 'lantern' then c.lantern = c.lantern + 1; check(o.night and o.light == 'lantern', 'a lantern: lit, at night') end
    if m:find('^flag') then c.flag = c.flag + 1 end
    if m == 'light_tower' then c.tower = c.tower + 1 end
    check(o.line and o.lat >= crowds.FENCE_LAT, 'line objects past the fence line')
  end
  c.len, c.dup = hi - lo, dup
  return c
end
local rural, town = tally(crowds.line(jumpSpot, 0.0)), tally(crowds.line(jumpSpot, 1.0))
check(not rural.dup and not town.dup, 'each thing its own key')
check(rural.people > 0 and town.fence > 0 and town.canopy > 0 and town.vehicle > 0 and town.flag > 0,
  'a fence, people, canopies, trucks, flags')
-- the fence only in town or along a really big crowd (the user, 2026-10-25)
check(rural.fence == 0, 'out of town, a small crowd: no fence')
check(tally(crowds.line(jumpSpot, 0.45)).fence == 0 and tally(crowds.line(jumpSpot, 0.55)).fence > 0,
  'a fence from FENCE_MIN_U up')
check(tally(crowds.line({ s = 0, kind = 'start', side = 0 }, 0.4)).fence > 0, 'a big crowd (the start) has one anyway')
-- laid from its ends: end to end along a straight, joined along a gentle curve, left out on a sharp corner
local function fencesOn(ce, spot, u)
  local out = {}
  for _, o in ipairs(crowds.line(spot, u)) do
    if o.fence and o.side == 1 then
      o.kind = spot.kind
      local x, y, yaw = crowds.placeOf(ce, ce.length, o, nil)
      out[#out + 1] = { x = x, y = y, yaw = yaw, s = o.s }
    end
  end
  return out
end
local straight = fencesOn(e, { s = 2500, kind = 'jump', side = 0 }, 1.0)
local gaps = 0
for i = 2, #straight do
  local a, b = straight[i - 1], straight[i]
  if a.x and b.x then
    local d = math.sqrt((a.x - b.x) ^ 2 + (a.y - b.y) ^ 2)
    if math.abs(d - crowds.FENCE_M) > 0.05 or math.abs(a.yaw - b.yaw) > 1e-6 then gaps = gaps + 1 end
  else
    gaps = gaps + 1
  end
end
check(#straight > 20 and gaps == 0, 'a straight: every piece placed, end to end, in line: ' .. gaps)
local gx, gy = {}, {}                       -- a gentle curve: 400 m radius
for i = 0, 200 do local a = i * 0.01; gx[#gx + 1], gy[#gy + 1] = 400 * math.sin(a), 400 - 400 * math.cos(a) end
local ge = poly.fromXY(gx, gy); ge.length = ge.cum[#ge.cum]
local gentle = fencesOn(ge, { s = 300, kind = 'jump', side = 0 }, 1.0)
local placed, worst = 0, 0
for _, f in ipairs(gentle) do if f.x then placed = placed + 1 end end
for i = 2, #gentle do
  local a, b = gentle[i - 1], gentle[i]
  if a.x and b.x then
    -- the end of one piece to the start of the next (each 5 m long, along its own yaw)
    local function ends(f)
      local ux, uy = math.cos(f.yaw), math.sin(f.yaw)   -- (the model's x axis turned by yaw)
      return f.x + ux * 2.5, f.y + uy * 2.5, f.x - ux * 2.5, f.y - uy * 2.5
    end
    local a1x, a1y, a0x, a0y = ends(a)
    local b1x, b1y, b0x, b0y = ends(b)
    local d = math.min(math.sqrt((a1x - b0x) ^ 2 + (a1y - b0y) ^ 2), math.sqrt((a0x - b1x) ^ 2 + (a0y - b1y) ^ 2),
                       math.sqrt((a1x - b1x) ^ 2 + (a1y - b1y) ^ 2), math.sqrt((a0x - b0x) ^ 2 + (a0y - b0y) ^ 2))
    worst = math.max(worst, d)
  end
end
check(placed == #gentle and worst < 0.3, 'a gentle curve: every piece, joined (worst gap ' .. string.format('%.2f', worst) .. ' m)')
local cx, cy = {}, {}                       -- a town corner: straight, a 90 degree turn of 12 m radius, straight
for i = 0, 30 do cx[#cx + 1], cy[#cy + 1] = i * 5, 0 end
for k = 1, 9 do local a = math.pi / 2 * k / 10; cx[#cx + 1], cy[#cy + 1] = 150 + 12 * math.sin(a), 12 - 12 * math.cos(a) end
for i = 0, 30 do cx[#cx + 1], cy[#cy + 1] = 162, 12 + i * 5 end
local ce2 = poly.fromXY(cx, cy); ce2.length = ce2.cum[#ce2.cum]
local cornerS = 150 + math.pi / 2 * 12 / 2
local onCorner, crossed = 0, 0
local corner = fencesOn(ce2, { s = cornerS, kind = 'hairpin', side = 0 }, 1.0)
for _, f in ipairs(corner) do
  if f.x and math.abs(f.s - cornerS) < 12 then onCorner = onCorner + 1 end
end
for i = 1, #corner do
  for j = i + 1, #corner do
    local a, b = corner[i], corner[j]
    if a.x and b.x and math.sqrt((a.x - b.x) ^ 2 + (a.y - b.y) ^ 2) < 2.0 then crossed = crossed + 1 end
  end
end
check(onCorner == 0, 'a sharp corner: no pieces round it: ' .. onCorner)
check(crossed == 0, 'none piled on each other: ' .. crossed)
check(town.len > 3 * rural.len, 'in town the line is much longer: ' .. math.floor(rural.len) .. ' m -> ' .. math.floor(town.len) .. ' m')
check(town.people / town.len > 1.5 * rural.people / rural.len, 'and more packed: '
  .. string.format('%.1f -> %.1f people a metre', rural.people / rural.len, town.people / town.len))
check(town.people > 300, 'hundreds of people at a jump in town: ' .. town.people)
check(town.vehicle > 3 * math.max(1, rural.vehicle) and town.canopy > 2 * math.max(1, rural.canopy), 'more camps in town')
check(rural.tower == 0 and tally(crowds.line({ s = 0, kind = 'start', side = 0 }, 0.5)).tower == 4,
  'light towers at the ends of a gate\'s line (both sides)')
local sameAgain = crowds.line(jumpSpot, 1.0)
check(#sameAgain == town.n and sameAgain[100].model == crowds.line(jumpSpot, 1.0)[100].model, 'the same line every time')
-- room left at the fence for the spot's own (turning) spectators
local withSkip = crowds.line(jumpSpot, 1.0, { [1] = { 18.0 }, [-1] = {} })
local blocked = false
for _, o in ipairs(withSkip) do if o.people and o.side == 1 and math.abs(o.along - 18.0) < 1.0 then blocked = true end end
check(not blocked, 'a gap in the line where a turning spectator stands')
-- placed: clear of the course like everything else, not pushed out by the start banner's own distance
local tooFar = 0
for _, o in ipairs(crowds.line({ s = 0, kind = 'start', side = 0 }, 0.5)) do
  o.kind = 'start'
  local x, y = crowds.placeOf(e, L, o, sides)
  if x and o.model == 'fence_orange' then
    local px, py = poly.at(e, math.max(0, math.min(L, o.s)))
    local mid = py + 2.0
    if math.abs(y - mid) > 6.0 + crowds.FENCE_LAT + 0.5 then tooFar = tooFar + 1 end
  end
end
check(tooFar == 0, 'the start\'s fence right at the track, not set back: ' .. tooFar)
-- plain lines near towns where nothing else happens (Lots only)
local function plain(level, u)
  local n = 0
  for _, p in ipairs(crowds.spots(e, wps, L, false, {}, level, nil, nil, function() return u end)) do
    if p.kind == 'line' then n = n + 1 end
  end
  return n
end
check(plain('lots', 0.8) >= 4 and plain('lots', 0.1) == 0 and plain('some', 0.8) == 0,
  'plain lines on Lots near towns: ' .. plain('lots', 0.8) .. ', none out of town, none on Some')
check(#crowds.spots(e, wps, L, false, {}, 'lots', nil, nil, nil) == #crowds.spots(e, wps, L, false, {}, 'lots'),
  'how urban not known: as before')
-- the companion's urban values merged; a stretch waits for them (Lots), then plans its line
local c3 = {}
crowds.merge(c3, { spots = {}, spotsFrom = 0, spotsTo = 5000, urbState = 'pending' })
check(c3.urbanOn and c3.urban == nil, 'towns still being fetched: nothing yet')
local urb = {}
for i = 1, 51 do urb[i] = 0.9 end
check(crowds.merge(c3, { spots = {}, spotsFrom = 0, spotsTo = 5000, urbState = 'ok', urbStep = 100, urbK0 = 0, urb = urb }),
  'urban values: changed')
check(c3.urban.v[10] == 0.9 and crowds.covered(c3.urbRanges, 0, 5000), 'kept, the stretch noted')
-- in the world: a gate on Lots, nearest first, many at a time
crowds.clear()
crowds.setLevel('lots')
local crsL = { e = e, track = { waypoints = wps }, length = L, closed = false, s = 0, spots = {},
               spotRanges = { { -1000, 30000 } }, spotsVersion = 1, urban = { step = 100, v = {} }, urbanOn = true,
               urbRanges = { { -1000, 30000 } } }
for k = -10, 300 do crsL.urban.v[k] = 0.8 end
local carL = { x = 0, y = -30, z = 0 }
crowds.update(crsL, 'A', carL)
local first = crowds.status().live
check(first > crowds.PER_UPDATE and first <= crowds.PER_UPDATE_LOTS, 'Lots: more made each time: ' .. first)
local far = 0
for _, l in pairs(crowds._live()) do if (l.x - carL.x) ^ 2 + (l.y - carL.y) ^ 2 > 150 ^ 2 then far = far + 1 end end
check(far == 0, 'the nearest first')
for _ = 1, 30 do crowds.update(crsL, 'A', carL) end
local stL = crowds.status()
check(stL.live > 300, 'the start lined: ' .. stL.live .. ' things')
local ch2 = crowds.cheers()
check(ch2[1] and ch2[1].n > 100, 'its cheer counts the line\'s people: ' .. tostring(ch2[1] and ch2[1].n))
crowds.clear()
crowds.setLevel('some')

-- 9. a start line at the course's very start (the user, 2026-10-25, a screenshot: the half before the start stood at
-- the start, fences crossed, people heaped), turns, and roads
local startLine = crowds.line({ s = 0, kind = 'start', side = 0 }, 0.8)
local gStart = crowds.group({ s = 0, kind = 'start', side = 0 }, 1)
crowds.fitOn(startLine, L)
crowds.fitOn(gStart, L)
local before0, fenceAt = 0, {}
local stacked = false
for _, o in ipairs(startLine) do
  if o.s < 0 then before0 = before0 + 1 end
  if o.model == 'fence_orange' then
    local k = o.side .. ':' .. math.floor(o.s * 10 + 0.5)
    if fenceAt[k] then stacked = true end
    fenceAt[k] = true
  end
end
for _, o in ipairs(gStart) do if o.s < 0 then before0 = before0 + 1 end end
check(before0 == 0 and not stacked, 'all on the course, after its start; no two fence pieces in one place')
local endLine = crowds.fitOn(crowds.line({ s = L, kind = 'finish', side = 0 }, 0.8), L)
local past = 0
for _, o in ipairs(endLine) do if o.s > L then past = past + 1 end end
check(past == 0, 'the finish line before the course\'s end')
-- a tight corner: the line's inside left out (it would overlap), the outside kept
local cx, cy = {}, {}
for i = 0, 30 do cx[#cx + 1], cy[#cy + 1] = i * 10, 0 end                          -- east 300 m ...
for k = 1, 8 do local a = math.pi / 2 * k / 8; cx[#cx + 1], cy[#cy + 1] = 300 + 12 * math.sin(a), 12 - 12 * math.cos(a) end
for i = 1, 30 do cx[#cx + 1], cy[#cy + 1] = 312, 12 + i * 10 end                   -- ... a 12 m left turn, north
local ce = poly.fromXY(cx, cy); ce.length = ce.cum[#ce.cum]
local sCorner = 300 + 12 * math.pi / 4
local inL = crowds.insideTurn(ce, ce.length, { s = sCorner, side = -1, lat = crowds.FENCE_LAT })
local outR = crowds.insideTurn(ce, ce.length, { s = sCorner, side = 1, lat = crowds.FENCE_LAT })
local straight = crowds.insideTurn(ce, ce.length, { s = 100, side = -1, lat = crowds.FENCE_LAT })
check(inL and not outR and not straight, 'a tight left turn: its inside (left) left out, its outside kept, straights kept')
-- roads: the game's road map (BeamNG.Earth's, for its AI): nothing stands on a road
local roadsnear = require('offroadCompanion/roadsnear')
local nodes = { a = { pos = { x = 50, y = -100 }, radius = 5, links = { b = {} } },
                b = { pos = { x = 50, y = 100 }, radius = 5, links = { a = {} } } }      -- a 10 m street across, x = 50
local idx = roadsnear.build(nodes)
check(idx.n == 1, 'one street')
check(roadsnear.onRoad(idx, 50, 0) and roadsnear.onRoad(idx, 54, 30) and not roadsnear.onRoad(idx, 56, 30),
  'on it within its half width (and a margin), off it past that')
check(roadsnear.blocked(idx, 'fence_orange', 47, -10, 0) and not roadsnear.blocked(idx, 'fence_orange', 40, -10, 0),
  'a fence piece reaching into it: blocked; one stopping short: not')
check(roadsnear.blocked(idx, 'pickup_white', 50 - 7.5, 0, math.pi / 2) and not roadsnear.blocked(idx, 'pickup_white', 50 - 7.5, 0, 0),
  'a truck pointing into the street: blocked; parked along it: not')
-- in the world: a start line with a street across it, nothing on the street, and gone when the street appears later
map = { getMap = function() return { nodes = nodes } end }
roadsnear.reset()
crowds.clear()
crowds.setLevel('lots')
local crsR = { e = e, track = { waypoints = wps }, length = L, closed = false, s = 0, spots = {},
               spotRanges = { { -1000, 30000 } }, spotsVersion = 1, urban = { step = 100, v = {} }, urbanOn = true,
               urbRanges = { { -1000, 30000 } } }
for k = -10, 300 do crsR.urban.v[k] = 0.8 end
for _ = 1, 30 do crowds.update(crsR, 'A', { x = 0, y = -30, z = 0 }) end
local onStreet, n = 0, 0
for _, l in pairs(crowds._live()) do
  n = n + 1
  if roadsnear.onRoad(idx, l.x, l.y) then onStreet = onStreet + 1 end
end
check(n > 100 and onStreet == 0, 'the start lined, nobody on the street: ' .. n .. ' things, ' .. onStreet .. ' on it')
local nodes2 = { c = { pos = { x = 120, y = -100 }, radius = 6, links = { d = {} } },
                 d = { pos = { x = 120, y = 100 }, radius = 6, links = { c = {} } } }
local idx2 = roadsnear.build(nodes2)
local was = 0
for _, l in pairs(crowds._live()) do if roadsnear.onRoad(idx2, l.x, l.y) then was = was + 1 end end
map = { getMap = function() return { nodes = nodes2 } end }
roadsnear.reset()
crowds.update(crsR, 'A', { x = 0, y = -30, z = 0 })
local still = 0
for _, l in pairs(crowds._live()) do if roadsnear.onRoad(idx2, l.x, l.y) then still = still + 1 end end
check(was > 0 and still == 0, 'a street that came in later: those on it taken away (' .. was .. ')')
-- a street the course runs along, wider than the track was thought to be: the line steps back off it, not gone
local along = { p = { pos = { x = -200, y = 0 }, radius = 7.5, links = { q = {} } },
                q = { pos = { x = 3000, y = 0 }, radius = 7.5, links = { p = {} } } }
local idxA = roadsnear.build(along)
map = { getMap = function() return { nodes = along } end }
roadsnear.reset()
crowds.clear()
for _ = 1, 30 do crowds.update(crsR, 'A', { x = 0, y = -30, z = 0 }) end
local fences, onIt = 0, 0
for key, l in pairs(crowds._live()) do
  if key:find(':L') then
    if l.x > -200 and l.x < 3000 and math.abs(l.y) < 7.5 then onIt = onIt + 1 end   -- (in the street: 7.5 m each side)
    fences = fences + 1
  end
end
check(fences > 100 and onIt == 0, 'along a wide street: the line stands back past its edge (' .. fences .. ' things, '
  .. onIt .. ' on it)')
map = nil
roadsnear.reset()
-- OpenStreetMap's ways (a dirt track across the start, which the game's road map leaves out): nobody on it either
local wIdx = roadsnear.fromWays({ { c = 'track', x = { 80, 80, 80 }, y = { -300, 0, 300 } } })
check(roadsnear.onRoad(wIdx, 80, 150) and roadsnear.onRoad(wIdx, 82.2, -20) and not roadsnear.onRoad(wIdx, 83, 0),
  'a track: 2 m each side of its line (and the margin)')
local both = roadsnear.combine(nil, idx2, wIdx)
check(roadsnear.onRoad(both, 120, 0) and roadsnear.onRoad(both, 80, 10) and not roadsnear.onRoad(both, 100, 0),
  'the game\'s roads and OpenStreetMap\'s together')
local streetmap = require('offroadCompanion/streetmap')
local A = { geodeticToEnu = function(_, lat, lon) return lon, lat, 0 end }
streetmap.addTiles({ { key = 't1', ways = { { c = 'track', p = { { -300, 80 }, { 0, 80 }, { 300, 80 } } } } } })
crowds.clear()
crowds.setLevel('lots')
local oldAnchor = e.anchor
e.anchor = A
for _ = 1, 30 do crowds.update(crsR, A, { x = 0, y = -30, z = 0 }) end
e.anchor = oldAnchor
local nT, onTrack = 0, 0
for _, l in pairs(crowds._live()) do
  nT = nT + 1
  if roadsnear.onRoad(wIdx, l.x, l.y) then onTrack = onTrack + 1 end
end
check(nT > 100 and onTrack == 0, 'the start lined, nobody on the dirt track across it: ' .. nT .. ' things, ' .. onTrack)
streetmap.reset()
crowds.clear()
crowds.setLevel('some')

-- 6b. (1.7.8, the user 2026-11-09: "the props sometimes still block some of the courses") the track's widths come in
-- after the crowd is standing, together with new spots (planned again, not only moved): the ones standing where the
-- track turned out to be are made again past its edge; and nothing is made where the width is still to come
do
  crowds.clear()
  crowds.setLevel('lots')
  local oldReplan = crowds.REPLAN_S
  local oldAnchorW = e.anchor
  e.anchor = A
  crowds.REPLAN_S = 0
  local crsW = { e = e, track = { waypoints = wps }, length = L, closed = false, s = 0, spots = {},
                 spotRanges = { { -1000, 30000 } }, spotsVersion = 1 }
  local carW = { x = 0, y = -30, z = 0 }
  for _ = 1, 40 do crowds.update(crsW, A, carW) end
  local before = crowds.status().live
  -- the track: 3 m each side of a middle 9 m left of the course's line (a road the course follows beside its line)
  local sd = { step = 10, hw = {}, ctr = {}, version = 1 }
  for i = 0, 2100 do sd.hw[i], sd.ctr[i] = 3.0, 9.0 end
  crsW.sides, crsW.spotsVersion = sd, 2
  for _ = 1, 60 do crowds.update(crsW, A, carW) end
  local on, n = 0, 0
  for _, l in pairs(crowds._live()) do
    n = n + 1
    if crowds.clearance(e, l.x, l.y, sd) < 1.0 then on = on + 1 end
  end
  check(before > 50 and n > 50 and on == 0, 'widths in with new spots: nobody left on the track (' .. on .. ' of ' .. n .. ')')
  -- the same by the widths alone
  local sd2 = { step = 10, hw = {}, ctr = {}, version = 1 }
  for i = 0, 2100 do sd2.hw[i], sd2.ctr[i] = 3.0, -9.0 end
  crsW.sides = sd2
  for _ = 1, 60 do crowds.update(crsW, A, carW) end
  on, n = 0, 0
  for _, l in pairs(crowds._live()) do
    n = n + 1
    if crowds.clearance(e, l.x, l.y, sd2) < 1.0 then on = on + 1 end
  end
  check(n > 50 and on == 0, 'widths in alone: nobody left on the track (' .. on .. ' of ' .. n .. ')')
  -- widths known for the course's first 100 m only: nothing made past them yet, then all of it once they come
  crowds.clear()
  local sd3 = { step = 10, hw = {}, ctr = {}, version = 1 }
  for i = 0, 10 do sd3.hw[i], sd3.ctr[i] = 3.0, 0.0 end
  crsW.sides = sd3
  for _ = 1, 60 do crowds.update(crsW, A, carW) end
  local past = 0
  for _, l in pairs(crowds._live()) do if l.x > 110 then past = past + 1 end end
  check(crowds.status().live > 0 and past == 0, 'the width still to come: nothing made there yet (' .. past .. ')')
  check(crowds.sidesPending(sd3, 300) and not crowds.sidesPending(sd3, 50) and not crowds.sidesPending(nil, 300)
    and not crowds.sidesPending({ step = 10, hw = {}, ctr = {} }, 300), 'sidesPending: only where the companion has not said yet')
  crowds.REPLAN_S = oldReplan
  e.anchor = oldAnchorW
  crowds.clear()
  crowds.setLevel('some')
end

-- 6c. (1.7.10, the user 2026-11-10: spectators in the air) the ground under the ones standing near changes (the block
-- they were measured on replaced by the graded one, lower): they are put back on it
do
  crowds.clear()
  crowds.setLevel('some')
  local oldRe, oldPer = crowds.REGROUND_S, crowds.REGROUND_PER
  crowds.REGROUND_PER = 1000
  local oldAnchorG = e.anchor
  e.anchor = A
  crowds.REGROUND_S = 0
  local crsG = { e = e, track = { waypoints = wps }, length = L, closed = false, s = 0, spots = {},
                 spotRanges = { { -1000, 30000 } }, spotsVersion = 1 }
  local carG = { x = 0, y = -30, z = 0 }
  for _ = 1, 30 do crowds.update(crsG, A, carG) end
  local n0 = crowds.status().live
  castRayStatic = function(from) return from.z + 5 end        -- (the ground now 5 m lower)
  for _ = 1, 30 do crowds.update(crsG, A, carG) end
  local high, n = 0, 0
  for _, l in pairs(crowds._live()) do
    if (l.x - carG.x) ^ 2 + (l.y - carG.y) ^ 2 < crowds.SURE_M ^ 2 then
      n = n + 1
      if l.z > -4.5 then high = high + 1 end
    end
  end
  check(n0 > 10 and n > 10 and high == 0, 'the ground lowered under them: back on it (' .. high .. ' of ' .. n .. ' still high)')
  castRayStatic = function(from) return from.z - 0 end
  crowds.REGROUND_S, crowds.REGROUND_PER = oldRe, oldPer
  e.anchor = oldAnchorG
  crowds.clear()
end

-- 6d. (1.7.12, the user 2026-11-12: "I saw them pop up in the air and all subsequent props were in the air too") a layer
-- of static collision 20 m over the ground (the old place's, after a rebase): nobody stands on it
do
  crowds.clear()
  crowds.setLevel('some')
  local oldRe, oldPer = crowds.REGROUND_S, crowds.REGROUND_PER
  crowds.REGROUND_S, crowds.REGROUND_PER = 0, 1000
  local oldAnchorH = e.anchor
  e.anchor = A
  local crsH = { e = e, track = { waypoints = wps }, length = L, closed = false, s = 0, spots = {},
                 spotRanges = { { -1000, 30000 } }, spotsVersion = 1 }
  local carH = { x = 0, y = -30, z = 0 }
  core_terrain = { getTerrainHeight = function() return 0 end }
  for _ = 1, 20 do crowds.update(crsH, A, carH) end
  castRayStatic = function(from) if from.z > 20 then return from.z - 20 end return from.z end
  for _ = 1, 30 do crowds.update(crsH, A, carH) end
  local up, n = 0, 0
  for _, l in pairs(crowds._live()) do
    n = n + 1
    if l.z > 1 then up = up + 1 end
  end
  check(n > 10 and up == 0, 'a collision layer over the ground: nobody moved up onto it (' .. up .. ' of ' .. n .. ')')
  castRayStatic = function(from) return from.z - 0 end
  core_terrain = nil
  crowds.REGROUND_S, crowds.REGROUND_PER = oldRe, oldPer
  e.anchor = oldAnchorH
  crowds.clear()
end

-- 7. parked vehicles and canopies only on open, nearly level ground: not on a roof, not hanging off a slope
do
  local v, why = crowds.footprint({ 0, 0.1, 0, 0.2, 0 }, { 0, 0, 0, 0, 0 }, 0.45)
  check(v == 'ok' and why > 0 and why < 0.1, 'level ground: stands there, a little into the low side')
  check(select(2, crowds.footprint({ 6, 6, 6, 6, 6 }, { 0, 0, 0, 0, 0 }, 0.45)) == 'structure', 'a roof: no')
  check(select(2, crowds.footprint({ 0, 0.9, 0, -0.2, 0 }, { 0, 0.9, 0, -0.2, 0 }, 0.45)) == 'slope', 'a slope: no')
  check(crowds.footprint({}, nil, 0.45) == 'wait', 'the ground not there yet: wait')
  check(crowds.footKind('pickup_red') == 'vehicle' and crowds.footKind('canopy_blue') == 'canopy'
    and crowds.footKind('crowd_a') == nil, 'which need a footprint')
  -- in the world: a block of buildings along the course's north side from 9 to 40 m out, 6 m tall
  local function bld(x, y) return y >= 9 and y <= 40 end
  castRayStatic = function(from) return bld(from.x, from.y) and from.z - 6 or from.z end
  core_terrain = { getTerrainHeight = function() return 0 end }
  crowds.clear()
  crowds.setLevel('lots')
  local crs3 = { e = e, track = { waypoints = wps }, length = L, closed = false, s = 0, spots = {},
                 spotRanges = { { -1000, 30000 } }, spotsVersion = 1, urban = { step = 100, v = {} }, urbanOn = true,
                 urbRanges = { { -1000, 30000 } } }
  for k = -10, 300 do crs3.urban.v[k] = 0.8 end
  local car3 = { x = 0, y = -30, z = 0 }
  local oldAnchor = e.anchor
  e.anchor = A
  for _ = 1, 60 do crowds.update(crs3, A, car3) end
  e.anchor = oldAnchor
  local high, vehiclesSouth = 0, 0
  for _, l in pairs(crowds._live()) do
    if l.foot and l.z > 1 then high = high + 1 end
    if l.foot and l.y < -5 then vehiclesSouth = vehiclesSouth + 1 end
  end
  check(high == 0, 'no vehicle or canopy on the roofs: ' .. high)
  check(vehiclesSouth > 0, 'the open side has its camp: ' .. vehiclesSouth)
  castRayStatic = function(from) return from.z - 0 end
  core_terrain = nil
  crowds.clear()
  crowds.setLevel('some')
end

print(string.format('%d passed, %d failed', pass, fail))
os.exit(fail == 0 and 0 or 1)
