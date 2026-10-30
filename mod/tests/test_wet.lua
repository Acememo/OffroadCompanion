-- luajit test_wet.lua (from mod/tests): wet ground after rain (wet.lua): the ground models' grip scaled with the
-- wetness and put back, puddles only in closed dips of the track, filled part way, the same for the same ground.
package.path = '../offroad_companion/lua/ge/extensions/?.lua;' .. package.path
local pass, fail = 0, 0
local function check(cond, name) if cond then pass = pass + 1 else fail = fail + 1; print('FAIL: ' .. name) end end
local function near(a, b, eps) return math.abs(a - b) < (eps or 1e-6) end

function vec3(x, y, z) return { x = x, y = y, z = z } end
function log() end

-- the engine's ground models (groundmodels.json values), with the getter / setter BeamNG has
local models = {
  DIRT = { staticFrictionCoefficient = 0.70, slidingFrictionCoefficient = 0.73, shearStrength = 0 },
  GRASS = { staticFrictionCoefficient = 0.61, slidingFrictionCoefficient = 0.65, shearStrength = 0 },
  ASPHALT = { staticFrictionCoefficient = 0.98, slidingFrictionCoefficient = 0.70, shearStrength = 0 },
  ROCK = { staticFrictionCoefficient = 0.93, slidingFrictionCoefficient = 0.65, shearStrength = 3 },  -- (left alone)
  SAND = { staticFrictionCoefficient = 0.6, slidingFrictionCoefficient = 0.6, shearStrength = 0 },
}
local sets = 0
be = {}
function be:getGroundModel(name)
  local m = models[name]
  if not m then return nil end
  local copy = {}
  for k, v in pairs(m) do copy[k] = v end
  return { data = copy }
end
function be:setGroundModel(name, d)
  sets = sets + 1
  for k, v in pairs(d) do models[name][k] = v end
end

-- the ground: a flat track (z 0) with whoops: troughs every 10.5 m along x, 0.2 m deep, the edges of the track (|y| >
-- 2.6) back at the natural ground 0.25 m higher
local function groundAt(x, y)
  local wave = 0.1 * (1 - math.cos(2 * math.pi * x / 10.5))      -- 0 at the troughs, 0.2 at the crests
  local z = wave
  if math.abs(y) > 2.6 then z = math.max(z, 0.25) end
  return z
end
local objects, nextId = {}, 0
function castRayStatic(from, dir, len)
  return from.z - groundAt(from.x, from.y)
end
local function newObj(class)
  nextId = nextId + 1
  local o = { class = class, fields = {}, id = nextId }
  function o:setField(k, _, v) self.fields[k] = v end
  function o:setPosition(p) self.pos = p end
  function o:setTransform(m) self.pos = m.pos; self.yaw = m.euler and m.euler.z end
  function o:setScale(s) self.scale = s end
  function o:registerObject(name) self.name = name; objects[name] = self end
  function o:getId() return self.id end
  function o:delete() objects[self.name] = nil end
  return o
end
function createObject(class) return newObj(class) end
function MatrixF()
  local m = {}
  function m:setFromEuler(e) self.euler = e end
  function m:setPosition(p) self.pos = p end
  return m
end
local rainObj = nil
scenetree = { MissionGroup = { addObject = function() end },
  findObject = function(name) if name == 'bngEarthRain' then return rainObj end return objects[name] end,
  findObjectById = function(id) for _, o in pairs(objects) do if o.id == id then return o end end end }

local wet = require('offroadCompanion/wet')
local poly = require('offroadCompanion/poly')
local markers = require('offroadCompanion/markers')

-- pure parts
local s, d = wet.factor('DIRT', 1)
check(near(s, 0.86) and near(d, 0.84), 'soaked dirt: the full-wet multipliers')
s = wet.factor('DIRT', 0.5)
check(near(s, 0.93), 'half wet: half way')
check(wet.factor('SAND', 1) == 1, 'sand left as it is')
check(wet.wetness({ w = 0.2 }, false) == 0.2 and wet.wetness({ w = 0.2 }, true) == wet.RAIN_W, 'the game\'s rain: at least RAIN_W')
check(wet.wetness(nil, false) == 0, 'nothing known: dry')

local h = {}
for i = 1, 81 do h[i] = groundAt((i - 1) * 0.5, 0) end
local dips = wet.dips(h, 0.5)
check(#dips >= 3, 'the whoops\' troughs found: ' .. #dips)
for _, dd in ipairs(dips) do
  local x = (dd.i - 1) * 0.5
  check(math.abs((x / 10.5) - math.floor(x / 10.5 + 0.5)) < 0.06, 'a trough at a multiple of 10.5 m: ' .. x)
  check(near(dd.rim - dd.floor, 0.2, 0.01), 'its depth up to the crests')
end
local flat = {}
for i = 1, 40 do flat[i] = 1 + 0.03 * i end
check(#wet.dips(flat, 0.5) == 0, 'a slope holds no water')
check(near(wet.level({ floor = 0, rim = 0.2 }, wet.PUDDLE_W), 0.2 * wet.FILL[1]), 'just wet enough: a little water')
check(near(wet.level({ floor = 0, rim = 0.2 }, 1), 0.2 * wet.FILL[2]), 'soaked: fuller')
local b = wet.box(h, 0.5, dips[1].i, 0.05, function(sr, off) return groundAt(sr, off) end)
check(b and b.hw == 3.0, 'the trough runs across the track: held by its edges, the narrowest box they close')
local rut = wet.box(h, 0.5, dips[1].i, 0.05, function(sr, off) return math.abs(off) >= 1 and 0.3 or groundAt(sr, 0) end)
check(rut and rut.hw == 1.0, 'a narrow dip: a narrow puddle')
check(b and b.s1 - b.s0 > 1 and b.s1 - b.s0 < 5, 'along the track: the wet run of the trough')
local open = wet.box(h, 0.5, dips[1].i, 0.05, function(sr, off) return -1 end)
check(open == nil, 'ground lower beside it: no puddle (it would spill)')

-- grip: set with the wetness, put back when dry
wet.onWetness({ w = 0.8, level = 'soaked', last24 = 12 })
wet.update(1, nil, nil, nil, markers.halfAt, 0)
check(near(models.DIRT.staticFrictionCoefficient, 0.70 * select(1, wet.factor('DIRT', 0.8))), 'dirt grips less')
check(near(models.ASPHALT.slidingFrictionCoefficient, 0.70 * select(2, wet.factor('ASPHALT', 0.8))), 'asphalt too')
check(models.ROCK.staticFrictionCoefficient == 0.93, 'a model reading back a shear strength: left alone')
check(models.SAND.staticFrictionCoefficient == 0.6, 'sand untouched')
local before = sets
wet.update(1, nil, nil, nil, markers.halfAt, 1)
check(sets == before, 'no change: not written again')
wet.onWetness({ w = 0 })
wet.update(1, nil, nil, nil, markers.halfAt, 2)
check(near(models.DIRT.staticFrictionCoefficient, 0.70) and near(models.GRASS.slidingFrictionCoefficient, 0.65),
      'dry again: the game\'s own values back')
rainObj = { getField = function(_, k) return k == 'numDrops' and '800' or '' end }
wet.update(1, nil, nil, nil, markers.halfAt, 3)
check(wet.w == wet.RAIN_W and models.DIRT.staticFrictionCoefficient < 0.70, 'the game\'s rain falling: wet')
rainObj = nil

-- puddles along a course down the x axis
local xs, ys = {}, {}
for i = 0, 60 do xs[#xs + 1] = i * 10; ys[#ys + 1] = 0 end
local e = poly.fromXY(xs, ys)
local anchor = {}
e.anchor = anchor
local crs = { e = e, s = 100, sides = nil }
wet.onWetness({ w = 0.9, level = 'soaked' })
local car = { x = 100, y = 0, z = 0.3 }
for k = 0, 10 do wet.update(1, crs, anchor, car, markers.halfAt, 10 + k * 3) end
check(wet.nPuddles > 0 and wet.nPuddles <= wet.MAX, 'puddles in the troughs near the car: ' .. wet.nPuddles)
local okAll = true
for _, p in pairs(wet.puddles) do
  local o = scenetree.findObjectById(p.id)
  if not o or o.class ~= 'WaterBlock' then okAll = false end
  local tx = (p.x / 10.5) - math.floor(p.x / 10.5 + 0.5)
  if math.abs(tx) > 0.08 then okAll = false end
  if p.z <= groundAt(p.x, 0) or p.z > groundAt(p.x, 0) + 0.2 then okAll = false end
end
check(okAll, 'each a water block at a trough, its surface over the floor and under the crests')
local first = {}
for k, p in pairs(wet.puddles) do first[k] = p.z end
wet.clear()
for k = 0, 10 do wet.update(1, crs, anchor, car, markers.halfAt, 100 + k * 3) end
local same = true
for k, z in pairs(first) do if not wet.puddles[k] or wet.puddles[k].z ~= z then same = false end end
check(same, 'the same ground: the same puddles')
wet.onWetness({ w = 0.2 })
wet.update(1, crs, anchor, car, markers.halfAt, 200)
check(wet.nPuddles == 0, 'dried: the puddles gone')
-- the puddles' look by how fresh the rain is
check(wet.look(nil, true) == 'fresh' and wet.look({ rainMmH = 1.2, last24 = 6 }, false) == 'fresh', 'raining: fresh water')
check(wet.look({ rainMmH = 0, last24 = 8 }, false) == 'settled', 'rained today: settled')
check(wet.look({ rainMmH = 0, last24 = 0.5 }, false) == 'mud', 'days ago: mud holes')
wet.onWetness({ w = 0.9, level = 'soaked', rainMmH = 0, last24 = 0 })
for k = 0, 10 do wet.update(1, crs, anchor, car, markers.halfAt, 300 + k * 3) end
local mudOk = wet.nPuddles > 0
for _, p in pairs(wet.puddles) do
  local o = scenetree.findObjectById(p.id)
  if not o or o.fields.baseColor ~= wet.LOOKS.mud.base or o.fields.clarity ~= '0.0' then mudOk = false end
end
check(mudOk, 'long after the rain: mud-coloured, opaque')
rainObj = { getField = function(_, k) return k == 'numDrops' and '800' or '' end }
wet.update(1, crs, anchor, car, markers.halfAt, 340)
check(wet.nPuddles == 0 or wet.lookNow == 'fresh', 'it rains again: made again as fresh water')
for k = 0, 10 do wet.update(1, crs, anchor, car, markers.halfAt, 350 + k * 3) end
local freshOk = wet.nPuddles > 0
for _, p in pairs(wet.puddles) do
  local o = scenetree.findObjectById(p.id)
  if not o or o.fields.baseColor ~= wet.LOOKS.fresh.base then freshOk = false end
end
check(freshOk, 'fresh water while it rains')
rainObj = nil
-- far enough ahead to see: the course scanned to AHEAD_M, the nearest made first
local far = 0
for _, p in pairs(wet.puddles) do if p.x > car.x + 140 then far = far + 1 end end
check(wet.AHEAD_M >= 400, 'made out to ' .. wet.AHEAD_M .. ' m along the course')

-- the wet look on BeamNG.Earth's ground tiles
local mats = {}
local function mat(name, version, layers)
  local m = { name = name, f = { version = version or '1', diffuseColor = '1 1 1 1', roughnessFactor = '1',
                                 baseColorFactor = '1 1 1 1', activeLayers = layers or '1' }, f1 = {}, reloads = 0 }
  function m:getField(k, i) if i == 1 then return self.f1[k] or '' end return self.f[k] or '' end
  function m:setField(k, i, v) if i == 1 then self.f1[k] = v else self.f[k] = v end end
  function m:flush() end
  function m:reload() self.reloads = self.reloads + 1 end
  mats[name] = m
  return m
end
mat('bngEarthFar_s1_1'); mat('bngEarthFar_s1_2', '1.5', '2'); mat('grass_material')
local fb = mat('bngEarthFar_s1_3'); fb.f.diffuseColor = wet.FALLBACK_COLOR
scenetree.findClassObjects = function(cls) local out = {}; for k in pairs(mats) do out[#out + 1] = k end; return out end
local oldFind = scenetree.findObject
scenetree.findObject = function(name) return mats[name] or oldFind(name) end
local L1 = wet.groundLook(1)
check(L1.color == '0.680 0.680 0.680 1' and L1.rough == '0.450', 'soaked: darker and glossier')
check(wet.groundLook(0.04).w == 0, 'quantised')
for t = 1, 5 do wet.lookTick(1, 1000 + t) end
check(mats.bngEarthFar_s1_1.f.diffuseColor == L1.color and mats.bngEarthFar_s1_1.f.roughnessFactor == L1.rough,
      'a ground tile\'s photo wet')
check(mats.bngEarthFar_s1_2.f.baseColorFactor == L1.color and mats.bngEarthFar_s1_2.f1.roughnessFactor == L1.arough,
      'a tile with its asphalt layer: both wet')
check(mats.grass_material.f.roughnessFactor == '1', 'other materials left alone')
check(fb.f.diffuseColor == wet.FALLBACK_COLOR and fb.f.roughnessFactor == '1', 'a tile without its photo left alone')
local reloads = mats.bngEarthFar_s1_1.reloads
for t = 1, 5 do wet.lookTick(1, 1010 + t) end
check(mats.bngEarthFar_s1_1.reloads == reloads, 'unchanged: not reloaded again')
for t = 1, 5 do wet.lookTick(0, 1020 + t) end
check(mats.bngEarthFar_s1_1.f.diffuseColor == '1.000 1.000 1.000 1' and mats.bngEarthFar_s1_1.f.roughnessFactor == '1.000'
      and mats.bngEarthFar_s1_2.f1.roughnessFactor == '0.900', 'dry again: as BeamNG.Earth made them')
wet.lookTick(0.6, 1030)
wet.restoreLook()
check(mats.bngEarthFar_s1_1.f.roughnessFactor == '1.000', 'turned off: dry look at once')
scenetree.findObject = oldFind
scenetree.findClassObjects = nil

wet.setEnabled(false)
check(near(models.DIRT.staticFrictionCoefficient, 0.70), 'turned off: grip as the game has it')

print(pass .. ' passed, ' .. fail .. ' failed')
if fail > 0 then os.exit(1) end
