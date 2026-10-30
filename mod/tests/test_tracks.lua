-- luajit test_tracks.lua (from mod/tests): the in-game dirt track on BeamNG.Earth's road tiles (stubbed engine).
package.path = '../offroad_companion/lua/ge/extensions/?.lua;' .. package.path

local pass, fail = 0, 0
local function check(cond, name)
  if cond then pass = pass + 1 else fail = fail + 1; print('FAIL: ' .. name) end
end

-- the engine
local objects, nextId = {}, 0
function vec3(x, y, z) return { x = x, y = y, z = z } end
local function newObj(class)
  nextId = nextId + 1
  local o = { id = nextId, class = class, fields = {}, nodes = {}, kids = {} }
  function o:setField(k, _, v) self.fields[k] = v end
  function o:registerObject(n) self.name = n; objects[self.id] = self end
  function o:addObject(c) self.kids[#self.kids + 1] = c end
  function o:insertNodeNoRegen(p, w) self.nodes[#self.nodes + 1] = { p.x, p.y, p.z, w } end
  function o:regenerate() self.regen = true end
  function o:getId() return self.id end
  function o:delete() objects[self.id] = nil end
  function o:getCount() return #self.kids end
  function o:deleteAllObjects() for _, k in ipairs(self.kids) do objects[k.id] = nil end; self.kids = {} end
  return o
end
function createObject(class) return newObj(class) end
scenetree = { MissionGroup = newObj('SimGroup') }
function scenetree.findObject(name) for _, o in pairs(objects) do if o.name == name then return o end end end
function scenetree.findObjectById(id) return objects[id] end
local function decals()
  local n, list = 0, {}
  for _, o in pairs(objects) do if o.class == 'DecalRoad' then n = n + 1; list[#list + 1] = o end end
  return n, list
end

-- BeamNG.Earth's roads module (the calls core.lua makes)
local roads = { calls = {} }
function roads.onTile(msg, aid) roads.calls[#roads.calls + 1] = 'tile'; return msg.anchorId == aid end
function roads.onDrop(msg) roads.calls[#roads.calls + 1] = 'drop' end
function roads.transform() roads.calls[#roads.calls + 1] = 'transform' end
function roads.clear() end
function roads.reset() end
function roads.fieldsFor(c) return { { 'material', c.m }, { 'textureLength', tostring(c.tl) }, { 'renderPriority', tostring(c.p) } } end
package.loaded['beamngEarth/roads'] = roads

-- a flat anchor (lat, lon <-> metres)
local LAT0, LON0, K = 31.0, -115.5, 111195.0
local KX = K * math.cos(math.rad(LAT0))
local function anchorAt(dx)
  local a = {}
  function a:geodeticToEnu(lat, lon, h) return (lon - LON0) * KX - dx, (lat - LAT0) * K, h or 0 end
  function a:enuToGeodetic(x, y, z) return LAT0 + y / K, LON0 + (x + dx) / KX, z end
  return a
end
local anchors = { [1] = anchorAt(0), [2] = anchorAt(1000) }
local function ll(x, y) return { LON0 + x / KX, LAT0 + y / K } end

local tracks = require('offroadCompanion/tracks')

-- clipping
do
  local r = tracks.clip({ { -10, 5, 0 }, { 10, 5, 1 }, { 30, 5, 2 } }, 0, 0, 20, 20)
  check(#r == 1 and #r[1] == 3 and r[1][1][1] == 0 and r[1][3][1] == 20 and math.abs(r[1][3][3] - 1.5) < 1e-9,
    'clipped to the box with z interpolated')
  local r2 = tracks.clip({ { 5, -5, 0 }, { 5, 25, 0 }, { 15, 25, 0 }, { 15, -5, 0 } }, 0, 0, 20, 20)
  check(#r2 == 2, 'a U through the box: two runs')
  check(#tracks.clip({ { -5, -5, 0 }, { -1, -1, 0 } }, 0, 0, 20, 20) == 0, 'outside: nothing')
end

check(tracks.install(), 'hooked')
check(tracks.install(), 'hooked once')
-- a piece along y = 100 from x = -100 to 600 (tiles 0_0, 1_0, 2_0 and -1_0)
local piece = { id = '~egpsA0', w = 6.5, ll = {}, z = {} }
for x = -100, 600, 10 do piece.ll[#piece.ll + 1] = ll(x, 100); piece.z[#piece.z + 1] = 12 end

-- tiles before the course: recorded, nothing drawn
roads.onTile({ anchorId = 1, key = '0_0' }, 1)
roads.onTile({ anchorId = 1, key = '1_0' }, 1)
roads.onTile({ anchorId = 1, key = '5_5' }, 1)
check(tracks.status().tiles == 3, 'tiles recorded')
tracks.setActive(true, function(aid) return anchors[aid] end)
check(tracks.addWindows('c1', { { k = 0, pieces = { piece } } }) == 1, 'one piece')
for _ = 1, 5 do tracks.update() end
local n, list = decals()
check(n == 2, 'drawn on the two tiles it crosses: ' .. n)
local ok = true
for _, o in ipairs(list) do
  check(o.fields.material == 'm_dirt_road', 'dirt material')
  for _, nd in ipairs(o.nodes) do
    if nd[4] ~= 6.5 or nd[3] ~= 12 then ok = false end
  end
  local xs = {}
  for _, nd in ipairs(o.nodes) do xs[#xs + 1] = nd[1] end
  check(math.min(unpack(xs)) >= -2.001 and math.max(unpack(xs)) <= 514.001, 'clipped to the tiles')
end
check(ok, 'width and height on every node')
-- the same windows again: nothing new
check(tracks.addWindows('c1', { { k = 0, pieces = { piece } } }) == 0, 'no duplicates')
-- a tile arriving later gets its part
roads.onTile({ anchorId = 1, key = '2_0' }, 1)
for _ = 1, 3 do tracks.update() end
check(decals() == 3, 'a later tile drawn on')
-- a dropped tile takes its part along
roads.onDrop({ anchorId = 1, key = '0_0' })
check(decals() == 2, 'dropped with its tile')
check(roads.calls[#roads.calls] == 'drop', "BeamNG.Earth's own onDrop still runs")
-- a rebase: everything goes (BeamNG.Earth deletes its DecalRoads), the new anchor's tiles are drawn on again
roads.transform()
check(decals() == 0 and tracks.status().tiles == 0, 'rebase: all gone')
roads.onTile({ anchorId = 2, key = '-3_0' }, 2)      -- the new frame is 1 km east: the piece is at x -1100 .. -400
for _ = 1, 3 do tracks.update() end
local _, l2 = decals()
check(#l2 == 1 and math.abs(l2[1].nodes[1][1] + 770) < 0.01 and math.abs(l2[1].nodes[#l2[1].nodes][1] + 510) < 0.01,
  'drawn in the new frame, clipped to tile -3_0: ' .. tostring(l2[1] and l2[1].nodes[1][1]))
-- a tile of an older anchor arriving late is refused by BeamNG.Earth: not recorded
roads.onTile({ anchorId = 1, key = '3_0' }, 2)
check(tracks.status().tiles == 1, 'a refused tile is not recorded')
-- another course: the old track goes
tracks.addWindows('c2', {})
check(decals() == 0, 'new course: old track gone')
-- off
tracks.addWindows('c2', { { k = 0, pieces = { piece } } })
for _ = 1, 3 do tracks.update() end
tracks.setActive(false)
check(decals() == 0 and tracks.status().tiles == 1, 'off: track gone, tiles still recorded')
tracks.uninstall()
check(roads.onTile ~= nil and tracks.status().hooked == false, 'unhooked')

-- BeamNG.Earth 1.7.2's road geotiles ('g17_x_y'): any anchor's, kept across rebases, the track drawn in the current one
do
  local z, x, y = tracks.geoParse('g17_23456_52000')
  check(z == 17 and x == 23456 and y == 52000 and tracks.geoParse('3_4') == nil, 'geotile keys')
  local b = tracks.geoBounds(17, 0, 0)
  check(math.abs(b[1] + 180) < 1e-9 and math.abs(b[4] - 85.0511287798) < 1e-6 and b[3] > b[1] and b[4] > b[2],
    'a geotile\'s bounds (west, south, east, north)')
  -- the geotile under the piece's middle (x 250, y 100 of anchor 1), as BeamNG.Earth's geotile.tileOf
  local la, lo = LAT0 + 100 / K, LON0 + 250 / KX
  local n = 2 ^ 17
  local gx = math.floor((lo + 180) / 360 * n)
  local lr = math.rad(la)
  local gy = math.floor((1 - math.log(math.tan(lr) + 1 / math.cos(lr)) / math.pi) / 2 * n)
  local gk = string.format('g17_%d_%d', gx, gy)
  local gb = tracks.geoBounds(17, gx, gy)
  check(lo >= gb[1] and lo <= gb[3] and la >= gb[2] and la <= gb[4], 'the piece\'s middle is in it')
  function roads.onTile(msg, cur) return true end
  function roads.replace(a, aid) end
  check(tracks.install(), 'hooked again')
  tracks.setActive(true, function(aid) return anchors[aid] end)
  tracks.addWindows('c3', { { k = 0, pieces = { piece } } })
  roads.onTile({ key = gk }, 1, anchors[1])
  for _ = 1, 5 do tracks.update() end
  local cnt, gl = decals()
  check(cnt == 1, 'drawn on the geotile: ' .. cnt)
  local xs = {}
  for _, nd in ipairs(gl[1].nodes) do xs[#xs + 1] = nd[1] end
  local x0 = (gb[1] - LON0) * KX
  local x1 = (gb[3] - LON0) * KX
  check(math.abs(math.min(unpack(xs)) - math.max(x0, -100)) < 0.01 and math.abs(math.max(unpack(xs)) - math.min(x1, 600)) < 0.01,
    'clipped at the geotile\'s edges')
  -- a rebase: the geotile stays and its track comes again in the new anchor's frame
  roads.transform()
  check(decals() == 0 and tracks.status().tiles == 1, 'rebase: the objects go, the geotile is kept')
  roads.replace(anchors[2], 2)
  for _ = 1, 5 do tracks.update() end
  local c2, g2 = decals()
  local xs2 = {}
  for _, nd in ipairs(g2[1].nodes) do xs2[#xs2 + 1] = nd[1] end
  check(c2 == 1 and math.abs(math.min(unpack(xs2)) - (math.max(x0, -100) - 1000)) < 0.01, 'drawn again in the new frame')
  roads.onDrop({ key = gk })
  check(decals() == 0 and tracks.status().tiles == 0, 'a dropped geotile takes its track along')
  tracks.uninstall()
end

print(string.format('%d passed, %d failed', pass, fail))
os.exit(fail == 0 and 0 or 1)
