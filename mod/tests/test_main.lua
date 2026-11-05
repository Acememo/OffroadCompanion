-- luajit test_main.lua (from mod/tests): offroadCompanion/main.lua wired to stubbed BeamNG.Earth globals and a fake socket.
package.path = '../offroad_companion/lua/ge/extensions/?.lua;' .. package.path

local pass, fail = 0, 0
local function check(cond, name)
  if cond then pass = pass + 1 else fail = fail + 1; print('FAIL: ' .. name) end
end

-- JSON stand-ins: frames carry keys into a table store
local store, nextKey = {}, 0
function jsonEncode(t) nextKey = nextKey + 1; local k = 'K' .. nextKey; store[k] = t; return k end
function jsonDecode(s) return store[s] end
function vec3(x, y, z) return { x = x, y = y, z = z } end
function log(l, t, m) if l == 'E' then print('LOG', m) end end

-- fake luasocket: connects at once; what the game sends is decoded into `sent`, `inbox` frames are received
local link = require('offroadCompanion/link')
local sent, inbox = {}, {}
package.preload['socket'] = function()
  return { tcp = function()
    local s = {}
    function s:settimeout() end
    function s:connect() return 1 end
    function s:setoption() end
    function s:getpeername() return '127.0.0.1' end
    function s:close() end
    function s:send(data, i)
      local r = link.newReader(); r.feed(data:sub(i or 1))
      local p = r.pop()
      if p then sent[#sent + 1] = store[p] end
      return #data
    end
    function s:receive()
      if #inbox > 0 then return table.remove(inbox, 1) end
      return nil, 'timeout', ''
    end
    return s
  end }
end
local function serverSays(t) inbox[#inbox + 1] = link.encode(jsonEncode(t)) end
local function lastSent(kind)
  for i = #sent, 1, -1 do if sent[i].type == kind then return sent[i] end end
end

-- BeamNG.Earth stand-ins
local LAT0, LON0, K = 31.8667, -116.6, 111195.0
local anchor = {}
function anchor:geodeticToEnu(lat, lon) return (lon - LON0) * K * math.cos(math.rad(LAT0)), (lat - LAT0) * K, 0 end
function anchor:enuToGeodetic(x, y, z) return LAT0 + y / K, LON0 + x / (K * math.cos(math.rad(LAT0))), z end
local function ll(x, y) return { LAT0 + y / K, LON0 + x / (K * math.cos(math.rad(LAT0))) } end
local car = { x = 0, y = 0, z = 5, speed = 15 }
local function setCar(x, y) car.x, car.y = x, y; local p = ll(x, y); car.lat, car.lon = p[1], p[2] end
setCar(0, 0)
beamngEarth_core = { _state = function() return { anchor = anchor, player = car } end }
function getPlayerVehicle() return { getDirectionVector = function() return { x = 1, y = 0, z = 0 } end } end
local earthDest, earthAuto, earthRoute = nil, false, nil
package.loaded['beamngEarth/gps'] = {
  route = function() return earthDest and earthRoute or nil end,
  setDestination = function(lat, lon, name) earthDest = { lat = lat, lon = lon, name = name }; return true end,
  clear = function() earthDest = nil end,
  status = function() return earthDest and { remaining = 1234, eta = 100, autodrive = earthAuto } or nil end,
  setAutodrive = function(on) earthAuto = on; return on end,
}
package.loaded['beamngEarth/statusbar'] = { location = function() return { street = 'Avenida Reforma', place = 'Ensenada', country = 'Mexico' } end }
local teleported = nil
package.loaded['beamngEarth/places'] = { goTo = function(lat, lon, name) teleported = { lat, lon, name }; return true end }
local hooks = {}
guihooks = { trigger = function(name, p) hooks[#hooks + 1] = { name = name, p = p } end }
local msgs = {}
function ui_message(t) msgs[#msgs + 1] = t end

local M = require('offroadCompanion/main')
local function frames(n, dt) for _ = 1, n do M.onUpdate(dt or 0.25, dt or 0.25) end end
local function lastHook() return hooks[#hooks] and hooks[#hooks].p end

-- connect: hello goes out, the companion answers
frames(14)
check(lastSent('hello') ~= nil, 'hello sent on connect')
serverSays({ type = 'hello', version = '1.0.0', sources = { { id = 'score', title = 'SCORE' } }, tracksDir = '/tracks' })
frames(1)
M.uiMounted(true)
frames(2)
local p = lastHook()
check(p and p.link == 'connected' and p.earth, 'payload: connected, in the Earth world')
check(p and p.car.street == 'Avenida Reforma', 'street from BeamNG.Earth')
check(p and #p.sources == 1, 'sources from the companion')

-- navigate: Earth GPS gets the destination, the companion gets a route request
local dst = ll(1000, -500)
M.uiGo(dst[1], dst[2], 'Hotel')
check(earthDest and earthDest.name == 'Hotel', 'Offroad Companion destination set (arrows, autodrive)')
local rq = lastSent('route')
check(rq and rq.bearing == 90, 'route requested with the car heading')
local pts, steps = {}, nil
for i = 0, 100 do pts[#pts + 1] = ll(i * 10, 0) end
for i = 1, 50 do pts[#pts + 1] = ll(1000, -i * 10) end
steps = { { text = 'Head east on A', icon = 'straight', type = 'depart', lat = pts[1][1], lon = pts[1][2], road = 'A' },
          { text = 'Turn right onto B', icon = 'right', type = 'turn', lat = pts[101][1], lon = pts[101][2], road = 'B' },
          { text = 'Arrive', icon = 'arrive', type = 'arrive', lat = pts[151][1], lon = pts[151][2], road = 'B' } }
serverSays({ type = 'route_result', id = rq.id, points = pts, steps = steps, dist = 1500, dur = 150 })
setCar(400, 1)
frames(3)
p = lastHook()
check(p.nav and p.nav.next and p.nav.next.text == 'Turn right onto B', 'turn-by-turn next maneuver')
check(p.nav and p.nav.next.dist == '600 m', 'distance to it: ' .. tostring(p.nav and p.nav.next and p.nav.next.dist))
check(p.map and p.map.route and #p.map.route > 5, 'minimap route line')
M.uiAutodrive(true)
check(earthAuto, 'autodrive forwarded to BeamNG.Earth')
-- arrive
setCar(1000, -495)
frames(2)
check(earthDest == nil and msgs[#msgs]:find('arrived'), 'arrival clears the route')

-- courses: list, load, guide
local lr = M.uiTrackList('score', '')
check(lr.id and lastSent('track_list').source == 'score', 'track list requested')
serverSays({ type = 'track_list_result', id = lr.id, source = 'score', items = { { id = 'u', name = 'Baja 500 Pro' } }, note = 'n' })
frames(1)
local res = M.uiTrackListResult(lr.id)
check(res and res.items[1].name == 'Baja 500 Pro', 'track list result taken by the app')
local tl = M.uiTrackLoad('score', 'u')
local cpts = {}
for i = 0, 200 do cpts[#cpts + 1] = ll(5000 + i * 10, 0) end
local v = ll(5600, 0)
serverSays({ type = 'track_result', id = tl.id, track = { name = 'Baja 500 Pro', kind = 'course', points = cpts, length = 2000,
  closed = false, approximate = false, waypoints = { { name = 'VCP 9', kind = 'vcp', lat = v[1], lon = v[2], s = 600, off = 0 } },
  zones = {}, rm = { { 0, 10 }, { 1609.344, 11 } }, attribution = 'Course: SCORE' } })
frames(1)
M.uiTrackAction('route_start')
check(earthDest and earthDest.name == 'Baja 500 Pro start', 'route to the course start')
M.uiTrackAction('teleport_start')
check(teleported and teleported[3] == 'Baja 500 Pro start', 'teleport to the start through BeamNG.Earth places')
setCar(5200, 20)
frames(3)
p = lastHook()
check(p.course and p.course.name == 'Baja 500 Pro', 'course in the payload')
check(p.course and p.course.rm == '10.1', 'race mile from anchors: ' .. tostring(p.course and p.course.rm))
check(p.course and p.course.ahead[1] and p.course.ahead[1].name == 'VCP 9', 'VCP coming up')
check(p.map and p.map.course and #p.map.course > 5 and p.map.wps and #p.map.wps == 1, 'minimap course + VCP')
-- the whole course on the map: sent once on its own hook, then only the car's place on it
hooks = {}
check(M.uiOverview(true).on, 'overview on')
frames(3)
local ovh, nOv = nil, 0
for _, h in ipairs(hooks) do if h.name == 'OffroadCompanionOverview' then ovh, nOv = h.p, nOv + 1 end end
check(ovh and #ovh.pts >= 4 and #ovh.pts % 2 == 0 and ovh.wps[1][3] == 'vcp', 'overview line and VCP sent')
check(nOv == 1, 'sent once: ' .. nOv)
p = lastHook()
check(p.map.ov and p.map.ov.v == ovh.version and math.abs(p.map.ov.x - 200) < 1 and p.map.ov.done > 0,
      'the car on the overview: ' .. tostring(p.map.ov and p.map.ov.x))
M.uiOverview(false)
frames(2)
check(lastHook().map.ov == nil, 'overview off')
-- painting: the loaded course goes to the companion; it lost it, so the points go along; once painting, the roads
-- around the car are sent again (BeamNG.Earth roads off and on)
local roadsToggles = {}
local earthNet = {}         -- (BeamNG.Earth's messages to its server, in order)
package.loaded['beamngEarth/roads'] = { enabled = true }
beamngEarth_core.setRoadsEnabled = function(on)
  roadsToggles[#roadsToggles + 1] = on
  if on then earthNet[#earthNet + 1] = 'roads_reset' end
end
local treesCleared = 0
package.loaded['beamngEarth/trees'] = { geoPlacement = function() end, clear = function()
  treesCleared = treesCleared + 1; earthNet[#earthNet + 1] = 'trees.clear' end }
package.loaded['beamngEarth/net'] = { send = function(m) earthNet[#earthNet + 1] = m.type end }
frames(2)
-- no course painter in BeamNG.Earth's server (its .exe): the track is planned by the companion, drawn in the game
local nearMsg = lastSent('paint_near')
check(nearMsg and nearMsg.trackId == nil and nearMsg.lat and nearMsg.scale == 1, 'game mode: the track near the car asked for')
check(lastHook().paint.mode == 'game', 'game mode shown')
local gp = { id = '~egpsX', w = 5, ll = { { -116.6, 31.8667 }, { -116.59, 31.8667 } }, z = { 1, 1 } }
serverSays({ type = 'paint_near_result', id = nearMsg.id, cid = 'cid1', windows = { { k = 0, pieces = { gp } } }, pending = 0 })
frames(1)
check(require('offroadCompanion/tracks').status().pieces == 1, 'pieces handed to the in-game track')
M.uiMounted(true)
frames(2)
check(lastHook().paint.game and lastHook().paint.game.planned == 1, 'planned windows counted for the status line')
-- an older companion does not know paint_near: said so
serverSays({ type = 'error', error = "unknown message type 'paint_near'" })
frames(2)
check(lastHook().paint.outdated ~= nil, 'an outdated companion is reported')
serverSays({ type = 'hello', version = '1.0.0', sources = {}, tracksDir = '/tracks' })
frames(1)
local pm = lastSent('paint')
check(pm and pm.enabled and pm.trackId == nil, 'paint sent for the course (no id from this test track): ' .. tostring(pm and pm.enabled))
check(pm.paint == true and pm.clear == true, 'dirt track and a clear corridor asked for')
serverSays({ type = 'paint_result', id = pm.id, need = 'x' })
frames(1)
pm = lastSent('paint')
check(pm.points and #pm.points == #cpts and pm.name == 'Baja 500 Pro', 'points sent when the companion needs them')
serverSays({ type = 'paint_result', id = pm.id, painting = true, painter = { course = 'Baja 500 Pro' } })
frames(2)
check(lastHook().paint.painting and lastHook().paint.painter, 'painting shown in the app')
check(lastHook().paint.mode == 'server' and require('offroadCompanion/tracks').status().pieces == 0,
  'a server painter takes over: the in-game track goes')
frames(24)   -- (REFRESH_DELAY_S)
check(#roadsToggles == 2 and roadsToggles[1] == false and roadsToggles[2] == true, 'roads around the car sent again')
check(table.concat(earthNet, ',') == 'roads_reset,trees.clear,offroad_geo_reset',
  'BeamNG.Earth 1.7.2+: its kept trees dropped too, then the server asked for them again: ' .. table.concat(earthNet, ','))
package.loaded['beamngEarth/trees'], package.loaded['beamngEarth/net'] = nil, nil
-- the car's place for the server's track prefetch: only to a companion that takes it
local nPose = 0
for _, m in ipairs(sent) do if m.type == 'pose' then nPose = nPose + 1 end end
check(nPose == 0, 'no pose to a companion without the feature')
serverSays({ type = 'hello', version = '1.0.0', sources = {}, tracksDir = '/tracks', features = { 'pose' },
             painter = { course = 'Baja 500 Pro' } })
frames(16)
local ps = lastSent('pose')
check(ps and math.abs(ps.lat - car.lat) < 1e-9 and ps.heading == 90, 'pose sent for the prefetch')
local nPose2 = 0
for _, m in ipairs(sent) do if m.type == 'pose' then nPose2 = nPose2 + 1 end end
check(nPose2 >= 1 and nPose2 <= 2, 'every few seconds: ' .. nPose2)
-- a teleport to the course's start: its place goes to the server's painter first (planned before the world is built
-- there), the car's own poses held meanwhile
M.uiTrackAction('teleport_start')
local jp = lastSent('pose')
check(jp and jp.jump and math.abs(jp.lat - teleported[1]) < 1e-9, 'the start\'s place sent before the teleport')
local nP = 0
for _, m in ipairs(sent) do if m.type == 'pose' then nP = nP + 1 end end
frames(40)
local nP2 = 0
for _, m in ipairs(sent) do if m.type == 'pose' then nP2 = nP2 + 1 end end
check(nP2 == nP, 'the car\'s own pose held meanwhile')
frames(60)
check(not lastSent('pose').jump, 'then the car\'s again')
local nPaint = 0
for _, m in ipairs(sent) do if m.type == 'paint' then nPaint = nPaint + 1 end end
M.uiSet('paintSize', '1.35')
frames(2)
check(lastSent('paint').scale == 1.35, 'size change re-sent')
check(lastSent('paint').rough == 'auto', 'track terrain: auto by default')
M.uiSet('rough', 'extra')
frames(2)
check(lastSent('paint').rough == 'extra', 'track terrain change re-sent')
M.uiSet('rough', 'auto')
frames(2)
check(lastSent('paint').rough == 'auto', 'track terrain: auto sent')
check(M.uiSet('rough', 'bumpy').settings.rough == 'auto', 'unknown track terrain: auto')
-- the ground's seal, and a replay's recorded ground (replaysync's side of main.lua)
serverSays({ type = 'hello', version = '1.0.0', sources = {}, tracksDir = '/tracks', features = { 'pose', 'terrain_snapshot' } })
frames(2)
local tp = lastSent('paint')
serverSays({ type = 'paint_result', id = tp.id, painting = true, painter = { course = 'Baja 500 Pro' }, seal = 'T1-c0ffee',
             terrain = 1 })
M.uiMounted(true)
frames(2)
check(lastHook().paint.seal == 'T1-c0ffee', 'the ground code shown')
local renv = require('offroadCompanion/replaysync')._env()
local tnow = renv.terrain()
check(tnow and tnow.seal == 'T1-c0ffee' and tnow.rough == 'auto' and tnow.tv == 1, 'the ground noted for a recording')
check(renv.snapshot('rec_1') and lastSent('terrain_snapshot').name == 'rec_1', 'and kept by the companion')
check(renv.applyTerrain({ trackId = 'score:b500', scale = 1.0, paint = true, clear = true, ruts = 'auto', rough = 'extra',
                          seal = 'T1-0ld000', tv = 1 }, 'rec_1'), 'a replay\'s ground asked for')
frames(1)
local rp = lastSent('paint')
check(rp.pin == 'rec_1' and rp.rough == 'extra' and rp.trackId == 'score:b500' and rp.tv == 1,
      'its course and settings, pinned to its snapshot')
check(not renv.terrainReady(), 'not ready before the companion has it')
serverSays({ type = 'paint_result', id = rp.id, painting = true, seal = 'T1-0ld000', terrain = 1 })
frames(2)
check(not renv.terrainReady(), 'nor before the server\'s processes read it')
frames(24)
M.uiMounted(true)
frames(1)
check(renv.terrainReady() and renv.seal() == 'T1-0ld000', 'then ready, with the recorded seal')
check(lastHook().paint.replayGround, 'shown as the replay\'s ground')
check(renv.terrain() == nil, 'never noted as the player\'s own ground')
check(renv.restoreTerrain(), 'the player\'s own back')
frames(1)
rp = lastSent('paint')
check(rp.pin == nil and rp.rough == 'auto', 'their own settings sent again')
check(not renv.restoreTerrain(), 'once')
check(M.uiSet('notes', 'right').settings.notes == 'right' and M.uiSet('notes', 'middle').settings.notes == 'top',
      'turn notes position')
check(M.uiSet('replays', false).settings.replays == false and M.uiSet('replays', true).settings.replays == true,
      'replays setting')
frames(2)
M.uiSet('paint', false)
frames(2)
check(lastSent('paint').paint == false and lastSent('paint').clear == true, 'turning the dirt track off is sent (the corridor stays cleared)')
M.uiSet('paint', true)
frames(2)
M.uiSet('clearCourse', false)
frames(2)
check(lastSent('paint').clear == false and lastSent('paint').paint == true, 'clearing off is sent')
M.uiSet('clearCourse', true)
frames(2)
-- ground codes: shown and copied; a friend's pasted, checked by the companion, its settings (and terrain version) used
local clip = nil
function setClipboard(s) clip = s end
serverSays({ type = 'hello', version = '1.5.9', sources = {}, tracksDir = '/tracks',
             features = { 'pose', 'terrain_snapshot', 'ground_code', 'wetness' } })
frames(2)
local cp = lastSent('paint')
serverSays({ type = 'paint_result', id = cp.id, painting = true, painter = { course = 'Baja 500 Pro' }, seal = 'T3-abc123',
             terrain = 3, code = 'T3-abc123-0R0B4VR0C1G0' })
frames(2)
M.uiMounted(true)
frames(1)
check(lastHook().paint.code == 'T3-abc123-0R0B4VR0C1G0', 'the ground code in the payload')
check(M.uiCopyCode().ok and clip == 'T3-abc123-0R0B4VR0C1G0', 'copied to the clipboard')
local pr = M.uiPasteCode('  T3-def456-0R0B4VR0C1G0 ')
local gq = lastSent('ground_code')
check(pr.ok and gq and gq.code == 'T3-def456-0R0B4VR0C1G0', 'a pasted code sent to the companion, trimmed')
serverSays({ type = 'ground_code_result', id = gq.id, ok = true, seal = 'T3-def456',
             settings = { paint = true, clear = true, rough = 'mild', ruts = 'off', scale = 1.2, tv = 3 } })
frames(2)
local gp2 = lastSent('paint')
check(gp2.rough == 'mild' and gp2.ruts == 'off' and gp2.scale == 1.2 and gp2.tv == 3, 'the code\'s settings sent')
M.uiMounted(true)
frames(1)
check(lastHook().paint.codeNote and not lastHook().paint.codeErr, 'said so')
M.uiSet('paintSize', '1.0')
frames(2)
check(lastSent('paint').tv == nil, 'a track setting changed by hand: the code\'s terrain version dropped')
gq = (M.uiPasteCode('T9-zzz') and lastSent('ground_code'))
serverSays({ type = 'ground_code_result', id = gq.id, ok = false, error = 'That code is for another course' })
frames(2)
M.uiMounted(true)
frames(1)
check(lastHook().paint.codeErr and lastHook().paint.codeNote:find('another course'), 'a code that does not fit: why')
-- wet ground: the rain of the last days asked for where the car is, the answer used
frames(4)
local wq = lastSent('wetness')
check(wq and math.abs(wq.lat - car.lat) < 1e-9, 'the wetness asked for at the car')
serverSays({ type = 'wetness_result', id = wq.id, w = 0.35, level = 'damp', last24 = 4.2 })
frames(2)
M.uiMounted(true)
frames(1)
check(lastHook().paint.wet and lastHook().paint.wet.w == 0.35 and lastHook().paint.wet.level == 'damp', 'the wetness shown')
check(M.uiSet('wetGround', false).settings.wetGround == false, 'wet ground off')
frames(2)
check(lastHook().paint.wet.w == 0, 'off: dry')
M.uiSet('wetGround', true)
-- settings
local r = M.uiSet('lang', 'es')
check(r.ok and M.debug().settings.lang == 'es', 'language setting')
check(not M.uiSet('nope', 1).ok, 'unknown setting refused')
M.uiMounted(true)                 -- (the app says it is on screen every 3 s)
M.uiTrackAction('unload')
frames(2)
check(lastHook().course == nil, 'course unloaded')
check(lastSent('paint').enabled == false, 'unloading stops the painting')

-- the GPS route cleared of blockages: BeamNG.Earth's own route (a search, a big-map marker) goes to the companion
local rpts = {}
for i = 0, 300 do rpts[#rpts + 1] = ll(-i * 50, 0) end
earthRoute = { version = 7, points = rpts }
M.uiGo(rpts[301][1], rpts[301][2], 'Tijuana')
frames(25)
local rc = lastSent('route_clear')
check(rc and rc.enabled and #rc.points == 301 and rc.name == 'Tijuana', 'BeamNG.Earth route sent for clearing')
local nRc = 0
for _, m in ipairs(sent) do if m.type == 'route_clear' then nRc = nRc + 1 end end
frames(30)
local nRc2 = 0
for _, m in ipairs(sent) do if m.type == 'route_clear' then nRc2 = nRc2 + 1 end end
check(nRc2 == nRc, 'the same route is not sent again')
earthRoute = { version = 8, points = { rpts[1], rpts[2], rpts[3] } }
frames(25)
check(lastSent('route_clear').enabled and #lastSent('route_clear').points == 3, 'a replanned route is sent')
serverSays({ type = 'route_clear_result', id = lastSent('route_clear').id, clearing = true, painter = { pid = 1 } })
M.uiMounted(true)
frames(2)
check(lastHook().paint.route.clearing, 'route clearing shown')
M.uiStop()
frames(25)
check(lastSent('route_clear').enabled == false, 'ending the route stops its clearing')
M.uiSet('clearRoute', false)
M.uiGo(rpts[301][1], rpts[301][2], 'Tijuana')
frames(25)
check(lastSent('route_clear').enabled == false, 'route clearing off: nothing cleared')
M.uiStop()
M.uiSet('clearRoute', true)

-- streets with names for the map
M.uiMounted(true, true)
frames(2)
local sq = lastSent('streets')
check(sq and sq.lat and sq.radius >= 1500, 'streets asked for around the car')
local a, b = ll(car.x - 200, car.y + 10), ll(car.x + 300, car.y + 10)
local c1, c2 = ll(car.x, car.y - 400), ll(car.x, car.y + 400)
serverSays({ type = 'streets_result', id = sq.id, pending = 0, tiles = { { key = '1_2', ways = {
  { c = 'primary', n = 'Avenida Reforma', r = '', p = { a, b } },
  { c = 'residential', n = '', r = 'BC 1', p = { c1, c2 } } } } } })
hooks = {}
frames(3)
local sh
for _, h in ipairs(hooks) do if h.name == 'OffroadCompanionStreets' then sh = h.p end end
check(sh and #sh.ways == 2 and sh.ways[1].n == 'Avenida Reforma' and sh.ways[1].c == 'primary', 'streets to the app, main roads first')
check(sh and sh.ways[2].n == 'BC 1', 'a road without a name shown by its ref')
p = lastHook()
check(p.map.sv == sh.version and p.map.sx ~= nil, 'the car placed in the street selection')
local again = 0
for _, h in ipairs(hooks) do if h.name == 'OffroadCompanionStreets' then again = again + 1 end end
check(again == 1, 'streets sent once, not every frame')
check(M.debug().streets.tiles == 1, 'tile kept')

-- the track editor: tap points on the map, record by driving, undo, save -> loaded as the course
M.uiEditor('plan')
M.uiEditor('add_rel', 100, 0)
M.uiEditor('add_rel', 200, 50)
M.uiEditor('add_rel', 300, 50)
M.uiEditor('undo')
frames(2)
p = lastHook()
check(p.editor.mode == 'plan' and p.editor.n == 2, 'planned points (one undone): ' .. tostring(p.editor.n))
check(p.map.draft and #p.map.draft == 1 and #p.map.draft[1] == 2 and math.abs(p.map.draft[1][1][1] - 100) < 1,
      'the draft on the map, car-relative')
M.uiEditor('record')
for i = 1, 10 do setCar(car.x + 5, car.y); frames(1) end
p = lastHook()
check(p.editor.mode == 'record' and p.editor.n >= 7 and p.editor.n <= 10, 'recorded every 8 m: ' .. tostring(p.editor.n))
M.uiEditor('checkpoint')
M.uiEditor('stop')
local sv = M.uiEditor('save', 'Arroyo run')
local ts = lastSent('track_save')
check(sv.ok and ts and ts.name == 'Arroyo run' and #ts.points == p.editor.n and #ts.checkpoints == 1, 'saved to the companion')
serverSays({ type = 'track_save_result', id = ts.id, ok = true, ref = 'Arroyo run.gpx', path = '/tracks/Arroyo run.gpx' })
frames(2)
local tg = lastSent('track_get')
check(tg and tg.source == 'local' and tg.ref == 'Arroyo run.gpx', 'the saved track loaded as the course')
check(lastHook().editor.n == 0 and lastHook().editor.note:find('Arroyo'), 'editor cleared, saved file shown')
check(not M.uiEditor('save', 'x').ok, 'nothing to save refused')

-- search: through the companion when it can (Photon / Nominatim), else BeamNG.Earth's own
local earthSearches = 0
beamngEarth_settings = { uiGeocode = function(q) earthSearches = earthSearches + 1; return { id = 77 } end,
                         uiGeocodeResult = function(id) return { results = { { name = 'Earth result' } } } end }
local sr = M.uiSearch('clairmont drive', false)
check(sr.via == 'earth' and earthSearches == 1, 'a companion without search: BeamNG.Earth searches')
check(M.uiSearchResult(77, 'earth').results[1].name == 'Earth result', 'BeamNG.Earth result')
serverSays({ type = 'hello', version = '1.0.0', sources = {}, tracksDir = '/tracks', features = { 'geocode', 'streets' } })
frames(1)
sr = M.uiSearch('clairmont drive san diego', true)
local gq = lastSent('geocode')
check(sr.via == 'companion' and gq and gq.q == 'clairmont drive san diego' and gq.submitted == true and gq.lat,
      'the companion searches, with the car position and Enter passed on')
check(M.uiSearchResult(sr.id, 'companion') == nil, 'pending')
serverSays({ type = 'geocode_result', id = gq.id, q = gq.q, source = 'nominatim',
             results = { { name = 'Clairemont Drive', detail = 'San Diego', lat = 32.83, lon = -117.19 } } })
frames(1)
local res = M.uiSearchResult(sr.id, 'companion')
check(res and res.source == 'nominatim' and res.results[1].name == 'Clairemont Drive', 'companion result taken')
check(M.uiSearchResult(sr.id, 'companion') == nil, 'taken once')
sr = M.uiSearch('x y z', false)
serverSays({ type = 'error', id = lastSent('geocode').id, error = "unknown message type 'geocode'" })
frames(1)
res = M.uiSearchResult(sr.id, 'companion')
check(res and res.error, 'an error answer ends the search')

-- the companion goes away
inbox[#inbox + 1] = nil
-- settings saved under the project's old name (before 1.2.0) are read when there are none under the new one
do
  local files = { ['/settings/earthGps.json'] = { rough = 'extra', notes = 'left' } }
  _G.jsonReadFile = function(p) return files[p] end
  M.onExtensionLoaded()
  local st = M.uiSet('ruts', 'auto').settings
  check(st.rough == 'extra' and st.notes == 'left', 'old settings carried over')
  files['/settings/offroadCompanion.json'] = { rough = 'mild' }
  M.onExtensionLoaded()
  check(M.uiSet('ruts', 'auto').settings.rough == 'mild', 'the new name\'s first once there')
  -- Track terrain's default became Auto (1.6.1): settings saved before with Rough (the old default) move to Auto
  -- once; Rough chosen after that stays
  files['/settings/offroadCompanion.json'] = { rough = 'on' }
  M.onExtensionLoaded()
  check(M.uiSet('ruts', 'auto').settings.rough == 'auto', 'the old default Rough: now Auto')
  files['/settings/offroadCompanion.json'] = { rough = 'on', defaults = 2 }
  M.onExtensionLoaded()
  check(M.uiSet('ruts', 'auto').settings.rough == 'on', 'Rough chosen since: kept')
  _G.jsonReadFile = nil
end

-- leaving a BeamMP server: the player's own copy of the mod switched back on (BeamMP leaves it off)
do
  local db = { offroad_companion = { active = false } }
  local activated = nil
  _G.core_modmanager = { getModDB = function(n) return db[n] end, activateMod = function(n) activated = n; db[n].active = true end }
  check(M.onBeamMPServerLeave() and activated == 'offroad_companion', 'our own mod back on after a BeamMP session')
  activated = nil
  check(not M.onBeamMPServerLeave() and activated == nil, 'already on: nothing')
  db.offroad_companion = nil
  check(not M.onBeamMPServerLeave(), 'a player without the mod: nothing')
  _G.core_modmanager = nil
end

-- the spectators' setting
check(M.uiSet('spectators', 'lots').settings.spectators == 'lots', 'spectators: lots')
check(M.uiSet('spectators', 'crowded').settings.spectators == 'some', 'spectators: an unknown value is some')
check(require('offroadCompanion/crowds').level == 'some', 'the crowds told')

-- out and back along one road (the user, 2026-10-25: a sign on a highway the course comes back along): the track's
-- widths asked for around the car, then for the course's other pass near it (far along the course, here on the ground)
do
  local ob = {}
  for i = 0, 200 do ob[#ob + 1] = ll(5000 + i * 10, 0) end         -- out 2 km east ...
  for i = 0, 200 do ob[#ob + 1] = ll(7000 - i * 10, 8) end         -- ... back 8 m beside it
  local function sidesAsked()
    local out = {}
    for _, m in ipairs(sent) do if m.type == 'course_sides' then out[#out + 1] = m end end
    return out
  end
  setCar(5300, 0)
  local n0 = #sidesAsked()
  local tl2 = M.uiTrackLoad('score', 'ob')
  serverSays({ type = 'track_result', id = tl2.id, track = { name = 'Out and back', kind = 'course', points = ob,
    length = 4008, closed = false, approximate = false, waypoints = {}, zones = {}, rm = { { 0, 0 } } } })
  serverSays({ type = 'hello', version = '1.0.0', sources = {}, tracksDir = '/tracks', features = { 'pose', 'course_sides' },
               painter = { course = 'Out and back' } })
  frames(2)
  local pm2 = lastSent('paint')
  serverSays({ type = 'paint_result', id = pm2.id, painting = true, painter = { course = 'Out and back' } })
  frames(30)
  local asked = sidesAsked()
  local first = asked[n0 + 1]
  local function has(r, s) return r and r.s0 <= s and r.s1 >= s end
  -- (out and back, the car is on both passes: s 300 out, s 3708 back; it follows one of them)
  check(first and (has(first, 300) ~= has(first, 3708)), 'the stretch around the car (one pass) asked first')
  serverSays({ type = 'course_sides_result', id = first and first.id, step = 10, i0 = 0, hw = {}, ctr = {},
               spots = {}, spotsFrom = first and first.s0, spotsTo = first and first.s1 })
  frames(2)
  asked = sidesAsked()
  local second = asked[n0 + 2]
  check(second and (has(first, 300) and has(second, 3708) or has(first, 3708) and has(second, 300))
    and (second.s1 < first.s0 or second.s0 > first.s1),
    'then the other pass past here: ' .. tostring(second and second.s0) .. ' .. ' .. tostring(second and second.s1))
end

-- BeamMP: while BeamNG.Earth holds our car (gravity off), its motion stopped every frame, not once (the user,
-- 2026-10-25: the car rose "like a balloon" while waiting for the ground, and fell when it came)
do
  local stops, heldNow = {}, true
  package.loaded['beamngEarth/simhold'] = { carHeld = function() return heldNow end }
  local origGet = getPlayerVehicle
  getPlayerVehicle = function() return { getRefNodeId = function() return 7 end, getDirectionVector = function()
    return { x = 1, y = 0, z = 0 } end,
    applyClusterVelocityScaleAdd = function(_, node, scale, x, y, z) stops[#stops + 1] = { node, scale, x, y, z } end } end
  for _ = 1, 5 do M.onPreRender(0.016) end
  check(#stops == 5 and stops[1][1] == 7 and stops[1][2] == 0 and stops[5][3] == 0,
    'held: the car\'s motion stopped every frame: ' .. #stops)
  heldNow = false
  for _ = 1, 5 do M.onPreRender(0.016) end
  check(#stops == 5, 'let go: left alone')
  package.loaded['beamngEarth/simhold'] = nil
  M.onPreRender(0.016)
  check(#stops == 5, 'a BeamNG.Earth without the hold: nothing')
  getPlayerVehicle = origGet
end

-- BeamNG.Earth's big map in a BeamMP session with nobody else known: its empty player list reached the page as {}
-- (not an array), and the map's render failed every second (the user, 2026-10-25: the console full of
-- "(state.value.others || []).map is not a function"); handed on as none, a list with players untouched
do
  local others = {}
  beamngEarth_settings = { uiMapState = function() return { connected = true, others = others, places = {} } end }
  frames(12)                                        -- (the fixes are put in every couple of seconds)
  local st = beamngEarth_settings.uiMapState()
  check(st.others == nil and st.connected == true, 'an empty player list: none (the page makes it [])')
  others = { { name = 'Ana', lat = 31.8, lon = -116.6 } }
  check(#beamngEarth_settings.uiMapState().others == 1, 'players there: as they are')
  local wrapped = beamngEarth_settings.uiMapState
  frames(12)
  check(beamngEarth_settings.uiMapState == wrapped, 'put in once')
  beamngEarth_settings = nil
end

-- the bindable key hides or shows the app (the action file names main.toggleApp)
do
  local n0 = #hooks
  check(M.toggleApp() and hooks[#hooks] and hooks[#hooks].name == 'OffroadCompanionToggle' and #hooks == n0 + 1,
    'the key: the app told to hide or show')
  local f = io.open('../offroad_companion/lua/ge/extensions/core/input/actions/offroadCompanion.json')
  local txt = f and f:read('*a') or ''
  if f then f:close() end
  check(txt:find('offroadCompanion_main.toggleApp()', 1, true) and txt:find('"ctx": "tlua"', 1, true),
    'the action file calls it')
end

-- BeamNG.Earth's game mod older than its server: told (orange dirt roads, 2026-11-05)
do
  M.STALE_CHECK_S = 0
  local hello = nil
  beamngEarth_core.serverHello = function() return hello end
  local mats, files = {}, {}
  scenetree = scenetree or {}
  local oldFind = scenetree.findObject
  scenetree.findObject = function(name) return mats[name] end
  FS = { fileExists = function(_, path) return files[path] == true end }
  check(M._earthModStale() == nil, 'no BeamNG.Earth server yet: nothing said')
  hello = { appVersion = '1.7.3-beta' }
  check(M._earthModStale() == nil, 'a 1.7 server draws no strips: nothing said')
  hello = { appVersion = '1.8.1-beta' }
  local got = M._earthModStale()
  check(got and got.server == '1.8.1-beta' and got.mp == false, 'a 1.8 server, the mod without its strips: said')
  MPCoreNetwork = { isMPSession = function() return true end }
  got = M._earthModStale()
  check(got and got.mp == true, 'on BeamMP: said so (the server\'s copy)')
  MPCoreNetwork = nil
  files[M.DIRT_MATERIALS_FILE] = true
  check(M._earthModStale() == nil, 'the 1.8 game mod mounted: nothing said')
  files[M.DIRT_MATERIALS_FILE] = nil
  mats[M.DIRT_MATERIAL] = {}
  check(M._earthModStale() == nil, 'its material there: nothing said')
  check(M._versionAtLeast('1.10.0', 1, 8) and not M._versionAtLeast('1.7.9', 1, 8) and not M._versionAtLeast(nil, 1, 8),
    'versions compared as numbers')
  scenetree.findObject, FS, beamngEarth_core.serverHello = oldFind, nil, nil
end

print(string.format('%d passed, %d failed', pass, fail))
os.exit(fail == 0 and 0 or 1)
