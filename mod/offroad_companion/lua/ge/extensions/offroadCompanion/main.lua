-- Offroad Companion: the game side of the app (ui/modules/apps/OffroadCompanion).
--
-- Road navigation: a destination searched in the app goes to BeamNG.Earth's own GPS (beamngEarth/gps.lua: the
-- stock route arrows on the road, the world map's line, Autodrive) and, for turn-by-turn, to the Offroad Companion
-- (OffroadCompanion/earth_gpsd.py: the same OSRM route with its maneuvers), followed here (nav.lua).
-- Race courses: the companion lists and loads courses (SCORE, race.mx, OpenStreetMap circuits, your files, a
-- link); course.lua guides along one and ribbon.lua draws it on the ground.
-- The car's place in the world (lat / lon, the world frame) and the street come from BeamNG.Earth (core's state,
-- statusbar.lua's street from the world server's map data).
--
-- Every UI_S the app gets one 'OffroadCompanionUpdate' hook while it is on screen; its buttons call the ui* functions.
local link = require('offroadCompanion/link')
local nav = require('offroadCompanion/nav')
local course = require('offroadCompanion/course')
local ribbon = require('offroadCompanion/ribbon')
local tracks = require('offroadCompanion/tracks')
local fmt = require('offroadCompanion/fmt')
local poly = require('offroadCompanion/poly')
local streetmap = require('offroadCompanion/streetmap')
local editor = require('offroadCompanion/editor')
local markers = require('offroadCompanion/markers')
local replaysync = require('offroadCompanion/replaysync')
local crowds = require('offroadCompanion/crowds')
local crowdsound = require('offroadCompanion/crowdsound')
local mphold = require('offroadCompanion/mphold')
local earthfix = require('offroadCompanion/earthfix')
local wet = require('offroadCompanion/wet')

local M = {}

M.UI_S = 0.2
M.CHECK_S = 0.2
M.REROUTE_S = 8
M.SETTINGS_FILE = '/settings/offroadCompanion.json'
M.OLD_SETTINGS_FILE = '/settings/earthGps.json'   -- (the project was BeamNG.Earth GPS before 1.2.0)
M.VERSION = '1.7.7'           -- (OffroadCompanion/VERSION: the same; the release zips are named after it)
M.BUILD = '2026-11-08 23:30'       -- (the app's own, app.js APP_BUILD, and the companion's copy of the mod are compared: a stale copy shows)

local settings = { lang = 'en', units = 'auto', ribbon = true, autoRoute = true, zoom = 600, paint = true, paintSize = 1.0,
                   clearCourse = true, clearRoute = true, streets = true, markers = 'checkpoints', ruts = 'auto', rough = 'auto',
                   replays = true, notes = 'top', spectators = 'some', crowdSound = true,
                   nightLights = 'on', wetGround = true,
                   uiScale = 1.0,       -- Settings' App size: the app's text and controls (0.7-2.5)
                   -- a ground code pasted for a course (Settings): the terrain version it was made with, for that course
                   groundTv = 0, groundTvFor = '',
                   -- the defaults' generation the saved settings were made with (2: Track terrain Auto, 1.6.1)
                   defaults = 2 }
M.MARKERS_S = 1.0
M.TRACK_WAIT_S = 240
-- Dirt tracks painted along the course where no road runs (the companion hands the course to BeamNG.Earth's server
-- started with the course painter, OffroadCompanion/start_earth_with_tracks.py)
local wetReq, wetAt, wetWhere = nil, -math.huge, nil
M.WET_S = 600               -- the rain of the last days asked for again this often (the companion caches an hour) ...
M.WET_MOVED_DEG = 0.05      -- ... or after moving this far (~5 km)
local codeReq = nil         -- a pasted ground code being checked
local paint = { sent = nil, state = nil, painter = nil, error = nil, refreshAt = nil, statusAt = -math.huge,
                helloSeen = false, mode = 'off', installAt = -math.huge,
                -- drawn in the game (no server painter, e.g. BeamNG.Earth's .exe): the companion's windows of track
                near = { busy = nil, at = -math.huge, lat = nil, lon = nil, cid = nil, have = {}, pending = 0, errors = nil,
                         total = nil } }
M.NEAR_EVERY_S, M.NEAR_PENDING_S, M.NEAR_MOVED_M = 8, 2, 400
M.PAINT_STATUS_S = 15
M.JUMP_HOLD_S = 20         -- s the car's own pose waits after a teleport to the course's start (the start's goes first)
M.TERRAIN_SETTLE_S = 5      -- s after the companion has a replay's ground before it is built (the server's processes
                            -- read the course file every 2 s)
M.REFRESH_DELAY_S = 4       -- the server's processes read the new course within ~2 s
M.REFRESH_NEAR_M = 2500     -- the roads around the car are sent again when it is this close to the course
-- The GPS road route cleared like a course (BeamNG.Earth's server with the course painter): Earth's own GPS route
-- (a search here or in its menu, a marker on its big map), else this app's.
local rclear = { sent = nil, at = -math.huge, dest = nil, clearing = false, error = nil }
M.ROUTE_CLEAR_S = 5         -- a new route sent at most this often
-- Where the car is, for BeamNG.Earth's server: its course painter plans the dirt track around it in the background,
-- so the road data is ready before the world streams in there (companion: pose.json)
M.POSE_S = 3
-- Where the course's track or road is (its width and middle, from the BeamNG.Earth server's profiles through the
-- companion): asked around the car every SIDES_S, so the course signs stand beside it (markers.placeFor)
M.SIDES_S, M.SIDES_BACK_M, M.SIDES_AHEAD_M = 5, 1000, 2500
-- ... and for the course's other passes near the car (out and back along one road: the other pass's road width, so a
-- sign stands clear of both): those within SIDES_PASS_M of the car, SIDES_PASS_PAD_M either side, SIDES_PASS_MAX of them
M.SIDES_PASS_M, M.SIDES_PASS_PAD_M, M.SIDES_PASS_MAX = 400, 400, 3
local poseAt = -math.huge
local poseHoldUntil = -math.huge   -- (a teleport to the course's start: its pose sent, the car's held a while)
-- The streets around the car for the map (companion: OpenStreetMap ways in tiles)
local streets = { busy = nil, at = -math.huge, lat = nil, lon = nil, pending = 0, error = nil, resend = true }
M.STREETS_EVERY_S, M.STREETS_PENDING_S, M.STREETS_MOVED_M = 15, 2, 300
-- The track editor's save in flight and its outcome for the app
local edit = { save = nil, note = nil, error = nil }
-- The whole course on the map (the app's Course button): sent once on its own hook (OffroadCompanionOverview) per course
-- and anchor, then every frame only where the car is on it
local overview = { on = false, key = nil, version = 0, data = nil }
local companion = { hello = nil, sources = {}, tracksDir = nil }
local nextId = 0
local dest = nil              -- { lat, lon, name }
local navi = nil              -- nav.lua instance
local navState = nil
local routeReq = nil          -- { id, at, reroute }
local routeError = nil
local lastRouteAt = -math.huge
local crs = nil               -- course.lua instance
local sidesReq, sidesAt = nil, -math.huge   -- course_sides asked (markers beside the track)
local sidesQueue = {}                         -- ({s0, s1} still to ask this round: the other passes near the car)
local crsState = nil
local trackReq = nil          -- { id, at }
local trackError = nil
local lists = {}              -- request id -> result (taken by the app)
local mountedUntil = -math.huge
local clock = 0
local lastCheck, lastUi = -math.huge, -math.huge
local lastTarget = nil        -- waypoint courses: the target last routed to
local markersAt = -math.huge

-- -- helpers --------------------------------------------------------------------------------------------------
local function ext(name) return rawget(_G, name) end
local function earthCore() return ext('beamngEarth_core') end
local function earthRoute()
  local ok, g = pcall(require, 'beamngEarth/gps')
  return ok and g or nil
end
local function decode(s)
  local f = rawget(_G, 'jsonDecode')
  if f then return f(s, 'offroadCompanion') end
  return nil
end
local function encode(t) return jsonEncode(t) end
local function send(msg) return link.send(msg, encode) end
local function newId() nextId = nextId + 1; return nextId end

local function imperial()
  if settings.units == 'imperial' then return true end
  if settings.units == 'metric' then return false end
  local s = rawget(_G, 'settings')
  local ok, v = pcall(function() return s and s.getValue and s.getValue('uiUnitLength') end)
  return ok and v == 'imperial' or false
end

local function message(text, ttl)
  local f = rawget(_G, 'ui_message')
  if f then pcall(f, text, ttl or 4, 'offroadCompanion') end
end

local function loadSettings()
  local rd = rawget(_G, 'jsonReadFile')
  if not rd then return end
  local ok, t = pcall(rd, M.SETTINGS_FILE)
  if not (ok and type(t) == 'table') then          -- (saved under the old name, before 1.2.0)
    ok, t = pcall(rd, M.OLD_SETTINGS_FILE)
  end
  if ok and type(t) == 'table' then
    for k, v in pairs(t) do if settings[k] ~= nil then settings[k] = v end end
    -- (1.6.1, the user 2026-10-28: "make 'Auto' terrain the default setting instead of 'rough'": settings saved
    -- before it held Rough as the old default; they move to Auto once, a choice made after this stays)
    if (tonumber(t.defaults) or 1) < 2 then
      if settings.rough == 'on' then settings.rough = 'auto' end
      settings.defaults = 2
    end
  end
  ribbon.enabled = settings.ribbon and true or false
  settings.markers = markers.setMode(settings.markers)   -- (true / false before 2026-10-22)
  settings.spectators = crowds.setLevel(settings.spectators)
  settings.nightLights = crowds.setLights(settings.nightLights)
  settings.crowdSound = crowdsound.setEnabled(settings.crowdSound ~= false)
  settings.wetGround = wet.setEnabled(settings.wetGround ~= false)
  replaysync.setEnabled(settings.replays ~= false)
end
local function saveSettings()
  local wr = rawget(_G, 'jsonWriteFile')
  if wr then pcall(wr, M.SETTINGS_FILE, settings, true) end
end

-- The car: { x, y, z, lat, lon, speed, heading } in BeamNG.Earth's world frame, and the anchor; nil outside its world.
local function where()
  local c = earthCore()
  local st = c and c._state and c._state() or nil
  local anchor, pl = st and st.anchor, st and st.player
  if not anchor or not pl or not pl.lat then return nil end
  local veh = rawget(_G, 'getPlayerVehicle') and getPlayerVehicle(0)
  local heading = nil
  if veh then
    local ok, d = pcall(function() return veh:getDirectionVector() end)
    if ok and d and math.abs(d.x) + math.abs(d.y) > 1e-6 then heading = poly.bearing(d.x, d.y) end
  end
  return { x = pl.x, y = pl.y, z = pl.z, lat = pl.lat, lon = pl.lon, speed = pl.speed or 0, heading = heading }, anchor
end

local function streetNow()
  local ok, sb = pcall(require, 'beamngEarth/statusbar')
  if ok and sb and sb.location then
    local l = sb.location()
    return l.street or '', (l.place or ''), (l.country or '')
  end
  return '', '', ''
end

-- -- routing ------------------------------------------------------------------------------------------------------
local function requestRoute(car, reroute)
  if not dest or not car then return end
  local id = newId()
  if send({ type = 'route', id = id, lat0 = car.lat, lon0 = car.lon, lat1 = dest.lat, lon1 = dest.lon,
            bearing = car.heading and math.floor(car.heading + 0.5) % 360 or nil, lang = settings.lang }) then
    routeReq, lastRouteAt = { id = id, at = clock, reroute = reroute }, clock
  end
end

function M.navigateTo(lat, lon, name, keepCourse)
  lat, lon = tonumber(lat), tonumber(lon)
  if not lat or not lon then return { ok = false, error = 'bad coordinates' } end
  dest = { lat = lat, lon = lon, name = name ~= '' and name or nil }
  navi, navState, routeError, routeReq, lastRouteAt = nil, nil, nil, nil, -math.huge
  local g = earthRoute()
  if g and g.setDestination then pcall(g.setDestination, lat, lon, dest.name) end
  local car = where()
  if car then requestRoute(car, false) end
  if not keepCourse then lastTarget = nil end
  return { ok = true }
end

function M.stopNav()
  dest, navi, navState, routeReq, routeError = nil, nil, nil, nil, nil
  local g = earthRoute()
  if g and g.clear then pcall(g.clear) end
  return { ok = true }
end

-- -- painting the course --------------------------------------------------------------------------------------------
-- What the server should paint now: the loaded course (with a real line) at the size setting, or nothing.
-- (and its corridor cleared of buildings, low bridges and walls: settings.clearCourse, BeamNG.Earth's server only)
-- A replay's ground (replaysync.lua): while one plays back, the course and settings it was recorded with, pinned to
-- the snapshot of its ground the companion kept (paint.override; nil: the player's own).
local function paintWanted()
  local o = paint.override
  if o then
    return { enabled = true, trackId = o.trackId, scale = o.scale or 1.0, paint = o.paint ~= false,
             clear = o.clear ~= false, ruts = o.ruts or 'auto', rough = o.rough or 'on', pin = o.pin, tv = o.tv,
             key = 'replay:' .. tostring(o.pin) .. ':' .. tostring(o.seal) }
  end
  local p, c = settings.paint and true or false, settings.clearCourse ~= false
  if not (p or c) or not crs or not crs.hasLine or crs.track.approximate then
    return { enabled = false, key = 'off' }
  end
  local size = tonumber(settings.paintSize) or 1.0
  local r = settings.ruts or 'auto'
  local g = settings.rough or 'auto'
  -- (a ground code pasted for this course: the terrain version it was made with)
  local tv = (settings.groundTvFor == crs.track.id and tonumber(settings.groundTv) or 0) > 0 and tonumber(settings.groundTv) or nil
  return { enabled = true, trackId = crs.track.id, scale = size, paint = p, clear = c, ruts = r, rough = g, tv = tv,
           key = tostring(crs.track.id) .. '@' .. size .. (p and 'p' or '') .. (c and 'c' or '') .. r .. '/' .. g
             .. (tv and ('/T' .. tv) or '') }
end

local function sendPaint(withPoints)
  local w = paintWanted()
  local msg = { type = 'paint', id = newId(), enabled = w.enabled, trackId = w.trackId, scale = w.scale,
                paint = w.paint, clear = w.clear, ruts = w.ruts, rough = w.rough, pin = w.pin, tv = w.tv }
  if withPoints and w.enabled and crs and crs.track.id == w.trackId then
    msg.points, msg.name = crs.track.points, crs.track.name
  end
  if send(msg) then paint.sent, paint.error = w.key, nil end
end

local function syncPaint()
  if not link.connected() then return end
  local w = paintWanted()
  if paint.sent ~= w.key then sendPaint(false) end
end

-- Who lays the track: 'server' (BeamNG.Earth's server has the course painter: graded ground, dirt surface),
-- 'game' (drawn here from the companion's plan: BeamNG.Earth's .exe), 'wait' (the companion has not said yet), 'off'.
local function paintMode()
  if not settings.paint or not crs or not crs.hasLine or crs.track.approximate then return 'off' end
  if paint.painter then return 'server' end
  if paint.helloSeen and link.connected() then return 'game' end
  return 'wait'
end

local function anchorFor(aid)
  local c = earthCore()
  local st = c and c._state and c._state() or nil
  if st and st.anchor and st.anchorId == aid then return st.anchor end
end

local function askNear(car)
  local nr = paint.near
  local have = {}
  for k in pairs(nr.have) do have[#have + 1] = k end
  local id = newId()
  if send({ type = 'paint_near', id = id, trackId = crs.track.id, scale = tonumber(settings.paintSize) or 1.0,
            lat = car.lat, lon = car.lon, have = have }) then
    nr.busy, nr.at, nr.lat, nr.lon = { id = id, at = clock }, clock, car.lat, car.lon
  end
end

local function gamePaint(car)
  local nr = paint.near
  if nr.busy and clock - nr.busy.at > 20 then nr.busy = nil end
  if nr.busy or not car then return end
  local moved = math.huge
  if nr.lat then
    local dy = (car.lat - nr.lat) * 111320
    local dx = (car.lon - nr.lon) * 111320 * math.cos(math.rad(car.lat))
    moved = math.sqrt(dx * dx + dy * dy)
  end
  local every = nr.pending > 0 and M.NEAR_PENDING_S or M.NEAR_EVERY_S
  if clock - nr.at >= every or moved >= M.NEAR_MOVED_M then askNear(car) end
end

-- The roads around the car sent again (BeamNG.Earth: roads off and on, its roads_reset): the new course's tracks
-- appear near the car at once instead of after the next rebase. BeamNG.Earth 1.7.3+ keeps its trees and far buildings
-- as geotiles across rebases and teleports near (trees.lua geoPlacement): with the course painter in its server (it
-- answers), the trees go too and the server is asked for both again (GEO_RESET, after roads_reset: earthpatch.py
-- refresh_geo), so no tree or building kept from before stands on the new track. (1.6.8-1.6.11 had the server send
-- them again into the trees the game kept: trees hung in the sky far off, the user 2026-10-31.)
M.GEO_RESET = 'offroad_geo_reset'
local function refreshRoads()
  local okR, roads = pcall(require, 'beamngEarth/roads')
  local c = earthCore()
  if not (okR and roads and roads.enabled and c and c.setRoadsEnabled) then return end
  pcall(c.setRoadsEnabled, false)
  pcall(c.setRoadsEnabled, true)
  if not paint.painter then return end
  local okT, trees = pcall(require, 'beamngEarth/trees')
  local okN, net = pcall(require, 'beamngEarth/net')
  if okT and type(trees) == 'table' and trees.geoPlacement and type(trees.clear) == 'function'
      and okN and type(net) == 'table' and type(net.send) == 'function' then
    pcall(trees.clear)
    pcall(net.send, { type = M.GEO_RESET })
  end
end

-- -- the GPS route cleared of blockages ----------------------------------------------------------------------------------
-- The route to clear now: { key, points = {{lat, lon}...}, name, dest } or nil.
local function routeWanted()
  if settings.clearRoute == false or not dest then return nil end
  local g = earthRoute()
  local r = g and g.route and g.route() or nil
  if r and r.points and #r.points >= 2 then
    return { key = 'earth:' .. tostring(r.version), points = r.points, name = dest.name }
  end
  if navi and navi.route and navi.route.points and #navi.route.points >= 2 then
    return { key = 'app:' .. tostring(navi.route), points = navi.route.points, name = dest.name }
  end
  return nil
end

local function syncRouteClear(car)
  if not link.connected() then return end
  local w = routeWanted()
  local key = w and w.key or 'off'
  if key == rclear.sent or clock - rclear.at < M.ROUTE_CLEAR_S then return end
  local pts = {}
  if w then for i, q in ipairs(w.points) do pts[i] = { q[1], q[2] } end end
  if send({ type = 'route_clear', id = newId(), enabled = w ~= nil, points = w and pts or nil,
            name = w and w.name or nil }) then
    rclear.sent, rclear.at = key, clock
    -- a new destination: the roads around the car again once the server has the route (not on every reroute)
    local dk = dest and (dest.lat .. ',' .. dest.lon) or nil
    if w and dk ~= rclear.dest and paint.painter then paint.refreshAt = clock + M.REFRESH_DELAY_S end
    rclear.dest = w and dk or nil
  end
end

-- -- the streets for the map ---------------------------------------------------------------------------------------
local function syncStreets(car)
  -- (for the app's map while it shows; and for the spectators while a course is loaded: they keep off every road
  -- and track OpenStreetMap has, crowds.lua)
  local forMap = settings.streets ~= false and clock < mountedUntil
  local forCrowds = settings.spectators ~= 'off' and crs ~= nil
  if not car or not link.connected() or not (forMap or forCrowds) then return end
  if streets.busy and clock - streets.busy.at > 30 then streets.busy = nil end
  if streets.busy then return end
  local moved = math.huge
  if streets.lat then
    local dy = (car.lat - streets.lat) * 111320
    local dx = (car.lon - streets.lon) * 111320 * math.cos(math.rad(car.lat))
    moved = math.sqrt(dx * dx + dy * dy)
  end
  local every = streets.pending > 0 and M.STREETS_PENDING_S or M.STREETS_EVERY_S
  if moved < M.STREETS_MOVED_M and clock - streets.at < every then return end
  local id = newId()
  local r = math.max(1500, (tonumber(settings.zoom) or 600) * 2.2)
  if send({ type = 'streets', id = id, lat = car.lat, lon = car.lon, radius = r, have = streetmap.haveKeys() }) then
    streets.busy, streets.at, streets.lat, streets.lon = { id = id, at = clock }, clock, car.lat, car.lon
  end
end

-- -- messages from the companion ------------------------------------------------------------------------------------
local function onMessage(m)
  local t = m.type
  if t == '_connected' then
    send({ type = 'hello', client = 'offroadCompanion', version = M.VERSION })
    paint.sent = nil                  -- (a restarted companion: told again)
    paint.near.busy = nil
    rclear.sent, rclear.at, streets.busy, streets.at = nil, -math.huge, nil, -math.huge
    if dest and not navi then lastRouteAt = -math.huge end
  elseif t == '_disconnected' then
    routeReq, trackReq = nil, nil
    if edit.save then edit.save, edit.error = nil, 'the Offroad Companion stopped' end
  elseif t == 'hello' then
    companion.hello, companion.sources, companion.tracksDir = m, m.sources or {}, m.tracksDir
    companion.features = {}
    for _, f in ipairs(m.features or {}) do companion.features[f] = true end
    companion.outdated = nil
    paint.painter = m.painter
    paint.helloSeen = true
  elseif t == 'route_result' then
    if routeReq and m.id == routeReq.id then
      routeReq = nil
      if m.error or not m.points or #m.points < 2 then
        routeError = m.error or 'no route'
      else
        routeError = nil
        navi = nav.new({ points = m.points, steps = m.steps or {}, dist = m.dist, dur = m.dur }, dest)
      end
    end
  elseif t == 'course_sides_result' then
    if crs and sidesReq and m.id == sidesReq.id and type(m.hw) == 'table' and m.step then
      local sd = crs.sides or { step = m.step, hw = {}, ctr = {}, version = 0 }
      local i0, got = tonumber(m.i0) or 0, 0
      for j, h in ipairs(m.hw) do
        local c = m.ctr and m.ctr[j]
        if type(h) == 'number' and type(c) == 'number' and (sd.hw[i0 + j - 1] ~= h or sd.ctr[i0 + j - 1] ~= c) then
          sd.hw[i0 + j - 1], sd.ctr[i0 + j - 1], got = h, c, got + 1
        end
      end
      if got > 0 then sd.version = sd.version + 1 end
      crs.sides = sd
      pcall(crowds.merge, crs, m)       -- (where spectators gather on this stretch: the jumps, the crossings)
    end
    sidesReq = nil
  elseif t == 'geocode_result' then
    lists[m.id] = { results = m.results or {}, error = m.error, source = m.source, retry = m.retry, q = m.q }
  elseif t == 'error' then
    if m.id ~= nil and lists[m.id] == false then lists[m.id] = { error = tostring(m.error or 'error'), results = {} } end
    -- a companion older than this mod answers what it does not know with this (the zip was replaced but the
    -- companion window not restarted)
    if tostring(m.error or ''):find('unknown message type') then companion.outdated = tostring(m.error) end
  elseif t == 'paint_near_result' then
    local nr = paint.near
    if nr.busy and m.id == nr.busy.id then nr.busy = nil end
    if m.need then
      sendPaint(true)                 -- the companion lost the course: the points go along
      nr.at = -math.huge
    elseif m.cid and paint.mode == 'game' and crs and m.trackId == crs.track.id then
      if m.cid ~= nr.cid then nr.cid, nr.have = m.cid, {} end
      tracks.addWindows(m.cid, m.windows)
      for _, w in ipairs(m.windows or {}) do
        nr.have[w.k] = #(w.pieces or {})
      end
      nr.pending, nr.errors, nr.total = tonumber(m.pending) or 0, m.errors, m.total
    end
  elseif t == 'paint_result' then
    paint.painter = m.painter
    if m.seal ~= nil then paint.seal, paint.terrain, paint.earth, paint.code = m.seal, m.terrain, m.earth, m.code end
    if m.pinMissing and log then log('W', 'offroadCompanion', 'replay: the ground kept with it is gone: ' .. tostring(m.pinMissing)) end
    if m.need then
      sendPaint(true)                 -- the companion lost the course: the points go along
    elseif m.error then
      paint.error, paint.state = m.error, nil
    elseif m.painting ~= nil then
      local was = paint.state
      paint.state = m.painting and paint.sent or nil
      if paint.state ~= was then paint.stateAt = clock end
      -- newly painting, near the course: the roads around the car again once the server has the course
      if m.painting and m.painter and paint.state ~= was and crs and crs.off and crs.off < M.REFRESH_NEAR_M then
        paint.refreshAt = clock + M.REFRESH_DELAY_S
      end
    end
  elseif t == 'wetness_result' then
    wetReq = nil
    if m.error and log then log('I', 'offroadCompanion', 'wet ground: ' .. tostring(m.error)) end
    wet.onWetness(m)
  elseif t == 'ground_code_result' then
    codeReq = nil
    if m.ok and type(m.settings) == 'table' and crs then
      local st = m.settings
      settings.paint, settings.clearCourse = st.paint ~= false, st.clear ~= false
      settings.rough, settings.ruts = st.rough or 'on', st.ruts or 'auto'
      settings.paintSize = math.max(0.5, math.min(2.0, tonumber(st.scale) or 1.0))
      settings.groundTv, settings.groundTvFor = tonumber(st.tv) or 0, crs.track.id
      saveSettings()
      paint.codeNote, paint.codeErr = 'Ground code applied: the same ground as ' .. tostring(m.seal) .. ' (it loads as the world streams in)', false
    elseif m.ok then
      paint.codeNote, paint.codeErr = 'Same ground: the codes match', false
    else
      paint.codeNote, paint.codeErr = tostring(m.error or 'that code could not be used'), true
    end
  elseif t == 'route_clear_result' then
    rclear.clearing, rclear.error = m.clearing and true or false, m.error
    if m.painter ~= nil then paint.painter = m.painter end
  elseif t == 'streets_result' then
    if streets.busy and m.id == streets.busy.id then streets.busy = nil end
    streetmap.addTiles(m.tiles)
    streets.pending, streets.error = tonumber(m.pending) or 0, m.error
  elseif t == 'track_save_result' then
    if edit.save and m.id == edit.save.id then
      edit.save = nil
      if m.ok then
        edit.error, edit.note = nil, tostring(m.path or m.ref)
        message('Track saved: ' .. tostring(m.path or m.ref), 5)
        editor.clear()
        editor.setMode('off')
        M.uiTrackLoad('local', m.ref)       -- loaded as the course: cleared and laid like any course
      else
        edit.error = m.error or 'could not save the track'
      end
    end
  elseif t == 'track_list_result' then
    lists[m.id] = { items = m.items or {}, note = m.note, error = m.error, source = m.source }
  elseif t == 'track_result' then
    if trackReq and m.id == trackReq.id then
      trackReq = nil
      if m.error or not m.track then
        trackError = m.error or 'could not load the course'
      else
        trackError = nil
        crs, crsState, lastTarget = course.new(m.track), nil, nil
        ribbon.reset()
        message('Course loaded: ' .. tostring(m.track.name), 4)
        if m.track.note then
          message(tostring(m.track.note), 10)
          if crs.event then pcall(crs.event, crs, tostring(m.track.note), 'info', clock) end
        end
      end
    end
  end
end

-- -- the frame --------------------------------------------------------------------------------------------------------
local function navText(st)
  local imp, lang = imperial(), settings.lang
  if not st then return nil end
  local out = { remaining = fmt.dist(st.remaining, imp), eta = st.eta and fmt.duration(st.eta) or nil,
                arrived = st.arrived, offRoute = st.offRoute, road = st.road }
  if st.next then
    out.next = { text = st.next.text, icon = st.next.icon, road = st.next.road, exit = st.next.exit,
                 dist = st.next.dist < 25 and fmt.t(lang, 'now') or fmt.dist(st.next.dist, imp), distM = st.next.dist }
  end
  if st['then'] then out['then'] = { text = st['then'].text, icon = st['then'].icon } end
  return out
end

local function courseText(st)
  if not st or not crs then return nil end
  local imp, lang = imperial(), settings.lang
  local t = crs.track
  local o = { name = t.name, kind = t.kind, source = t.source, attribution = t.attribution, approximate = t.approximate,
              closed = t.closed, length = fmt.dist(crs.length, imp), events = st.events }
  if st.waypoints then
    o.waypoints = true
    o.total = st.total
    o.finished = st.finished
    if st.target then
      o.target = { name = st.target.name, index = st.target.index, dist = fmt.dist(st.target.dist, imp),
                   bearing = st.target.bearing, dir = st.target.dir }
      o.remaining = fmt.dist(st.remaining, imp)
      o.after = st.after and st.after.name or nil
    end
    return o
  end
  o.progress = st.progress
  o.done = fmt.dist(st.s, imp)
  o.left = fmt.dist(math.max(0, crs.length - st.s), imp)
  o.rm = string.format('%.1f', st.rm or 0)
  o.wrongWay = st.wrongWay
  if st.offCourse then o.off = { text = st.offText, bearing = st.offCourse.bearing, dist = fmt.dist(st.offCourse.dist, imp) } end
  if st.corner then
    o.corner = { text = st.corner.text, dir = st.corner.dir, grade = st.corner.grade, into = st.corner.into,
                 dist = st.corner.dist < 15 and fmt.t(lang, 'now') or fmt.dist(st.corner.dist, imp) }
  end
  o.ahead = {}
  for i, a in ipairs(st.ahead or {}) do
    o.ahead[i] = { name = a.name, kind = a.kind, dist = fmt.dist(a.dist, imp), limit = a.limit and fmt.limit(a.limit, imp) }
  end
  if st.nextRm then o.nextRm = { name = st.nextRm.name, dist = fmt.dist(st.nextRm.dist, imp) } end
  if st.zone then
    o.zone = { name = st.zone.name, limit = st.zone.limit and fmt.limit(st.zone.limit, imp), speeding = st.zone.speeding,
               toEnd = fmt.dist(st.zone.toEnd, imp) }
  end
  if st.zoneAhead then
    o.zoneAhead = { limit = st.zoneAhead.limit and fmt.limit(st.zoneAhead.limit, imp), dist = fmt.dist(st.zoneAhead.dist, imp) }
  end
  if st.danger then o.danger = { name = st.danger.name, dist = fmt.dist(st.danger.dist, imp) } end
  if st.timing then
    local tm = st.timing
    o.timing = { mode = tm.mode, lap = tm.lap, current = tm.current and fmt.laptime(tm.current),
                 last = tm.last and fmt.laptime(tm.last), best = tm.best and fmt.laptime(tm.best),
                 elapsed = tm.elapsed and fmt.laptime(tm.elapsed), finished = tm.finished }
  end
  o.vcp = st.vcp
  return o
end

local function check(dt)
  syncPaint()
  if link.connected() and clock - paint.statusAt > M.PAINT_STATUS_S then
    paint.statusAt = clock
    send({ type = 'paint_status', id = newId() })
  end
  if paint.refreshAt and clock >= paint.refreshAt then
    paint.refreshAt = nil
    refreshRoads()
  end
  if clock - paint.installAt > 2 then
    paint.installAt = clock
    tracks.install()                  -- (BeamNG.Earth's road tiles: recorded from the start, drawn on in game mode)
    pcall(markers.ensureMaterials)    -- (the markers' and the server's wheel ruts' materials)
    pcall(earthfix.apply)             -- (small fixes to BeamNG.Earth's own code: its big map in BeamMP)
    if not crs then pcall(markers.update, nil); pcall(crowds.update, nil); pcall(crowdsound.update, nil) end
  end
  local mode = paintMode()
  if mode ~= paint.mode then
    paint.mode = mode
    if mode ~= 'game' then
      tracks.setActive(false)
      paint.near.cid, paint.near.have, paint.near.pending, paint.near.errors = nil, {}, 0, nil
    end
  end
  if mode == 'game' then tracks.setActive(true, anchorFor) end
  local car, anchor = where()
  if mode == 'game' then gamePaint(car) end
  syncRouteClear(car)
  if car and mode == 'server' and companion.features and companion.features.pose and link.connected()
      and clock - poseAt >= M.POSE_S and clock >= poseHoldUntil then
    poseAt = clock
    send({ type = 'pose', lat = car.lat, lon = car.lon, speed = car.speed,
           heading = car.heading and math.floor(car.heading + 0.5) or nil })
  end
  if car and settings.wetGround ~= false and companion.features and companion.features.wetness and link.connected()
      and not wetReq and (clock - wetAt >= M.WET_S or not wetWhere
        or (car.lat - wetWhere[1]) ^ 2 + ((car.lon - wetWhere[2]) * math.cos(math.rad(car.lat))) ^ 2 > M.WET_MOVED_DEG ^ 2) then
    wetAt, wetWhere = clock, { car.lat, car.lon }
    local id = newId()
    if send({ type = 'wetness', id = id, lat = car.lat, lon = car.lon }) then wetReq = { id = id, at = clock } end
  end
  if wetReq and clock - wetReq.at > 60 then wetReq = nil end
  do
    local okW, errW = pcall(wet.update, M.CHECK_S, crs, anchor, car, markers.halfAt, clock)
    if not okW and log then log('E', 'offroadCompanion', 'wet ground: ' .. tostring(errW)) end
  end
  if not car then return end
  syncStreets(car)
  editor.update(car.lat, car.lon)
  if edit.save and clock - edit.save.at > 30 then edit.save, edit.error = nil, 'the companion did not answer' end
  local lang, imp = settings.lang, imperial()
  -- road route: ask when there is none (companion came back), follow it, replan when left
  if dest then
    if not navi and not routeReq and link.connected() and clock - lastRouteAt > M.REROUTE_S then requestRoute(car, false) end
    if navi then
      navState = navi:update(anchor, car.x, car.y, clock)
      if navState.offRoute and not routeReq and clock - lastRouteAt > M.REROUTE_S then requestRoute(car, true) end
      if navState.arrived then
        message(fmt.t(lang, 'arrived') .. (dest.name and (': ' .. dest.name) or ''), 5)
        M.stopNav()
      end
    end
    if routeReq and clock - routeReq.at > 30 then routeReq = nil end
  end
  -- course
  if crs then
    crsState = crs:update(anchor, car.x, car.y, car.heading, car.speed, clock, lang, imp)
    -- waypoint courses: road directions to each waypoint in turn
    if crs.s and paint.mode == 'server' and companion.features and companion.features.course_sides
        and link.connected() and not (sidesReq and clock - sidesReq.at < 20)
        and (#sidesQueue > 0 or clock - sidesAt >= M.SIDES_S) then
      if #sidesQueue == 0 then
        -- a new round: the stretch around the car, then the other passes of the course near it
        sidesAt = clock
        local a, b = crs.s - M.SIDES_BACK_M, crs.s + M.SIDES_AHEAD_M
        sidesQueue = { { a, b } }
        local e = crs.e and crs.e.anchor == anchor and crs.e or nil
        local okP, near = pcall(markers.passesNear, e, car.x, car.y, M.SIDES_PASS_M, a, b, M.SIDES_PASS_PAD_M)
        for k, r in ipairs(okP and near or {}) do
          if k <= M.SIDES_PASS_MAX then sidesQueue[#sidesQueue + 1] = r end
        end
      end
      local r = table.remove(sidesQueue, 1)
      local id = newId()
      if send({ type = 'course_sides', id = id, s0 = r[1], s1 = r[2] }) then
        sidesReq = { id = id, at = clock }
      else
        sidesQueue = {}
      end
    end
    if clock - markersAt >= M.MARKERS_S then
      markersAt = clock
      local okM, errM = pcall(markers.update, crs, anchor, car)
      pcall(markers.testCleanup)
      if not okM and log then log('E', 'offroadCompanion', 'markers: ' .. tostring(errM)) end
      local _, _, ctry = streetNow()
      if ctry and ctry ~= '' then crowds.country = ctry end      -- (Mexico's flags in Mexico)
      local okC, errC = pcall(crowds.update, crs, anchor, car)
      if not okC and log then log('E', 'offroadCompanion', 'crowds: ' .. tostring(errC)) end
      local okS, errS = pcall(crowdsound.update, crowds.cheers(), car, crowds.hash, crs)   -- (the crowds near you heard)
      if not okS and log then log('E', 'offroadCompanion', 'crowd sound: ' .. tostring(errS)) end
    end
    if crsState.waypoints and settings.autoRoute and crsState.target and lastTarget ~= crsState.target.index then
      lastTarget = crsState.target.index
      local w = crs.track.waypoints[crsState.target.index]
      if w then M.navigateTo(w.lat, w.lon, w.name, true) end
    end
  end
  -- (a course from OpenStreetMap can wait minutes on its busy servers: the companion tries each, twice)
  if trackReq and clock - trackReq.at > M.TRACK_WAIT_S then trackReq, trackError = nil, 'the companion did not answer' end
end

-- BeamNG.Earth's game mod older than its server (the user, 2026-11-05: a friend's dirt roads, the course's track
-- among them, solid orange with the engine's missing-material texture). From 1.8 BeamNG.Earth's server draws dirt and
-- gravel roads as rutted strips with materials its 1.8 game mod defines (dirtroad.materials.json); a 1.7 game mod
-- speaks the same protocol and works otherwise, without them. On BeamMP every player gets the server's
-- Resources/Client/beamng_earth.zip (and their own mods are turned off), so an old copy there does it to everyone
-- whose BeamNG.Earth app is 1.8. {server = its version, mp = on BeamMP} when so, else nil; checked every few seconds.
M.DIRT_MATERIAL = 'bne_dirt_variation_01'
M.DIRT_MATERIALS_FILE = '/levels/beamng_earth/art/shapes/beamngEarth/dirtroad.materials.json'
M.STALE_CHECK_S = 5
local stale = { at = -math.huge, got = nil }

local function versionAtLeast(v, major, minor)
  local a, b = tostring(v or ''):match('^%s*(%d+)%.(%d+)')
  a, b = tonumber(a), tonumber(b)
  if not a then return false end
  return a > major or (a == major and b >= minor)
end
M._versionAtLeast = versionAtLeast

local function earthModStale()
  if clock - stale.at < M.STALE_CHECK_S then return stale.got end
  stale.at, stale.got = clock, nil
  local core = earthCore()
  local h = core and core.serverHello and core.serverHello() or nil
  if not h then return nil end                  -- (no BeamNG.Earth server yet: nothing to compare)
  local sv = h.appVersion
  if sv == nil or sv == '' then sv = paint.earth end
  if not versionAtLeast(sv, 1, 8) then return nil end
  local st, fs = rawget(_G, 'scenetree'), rawget(_G, 'FS')
  local have = false
  pcall(function() have = st ~= nil and st.findObject ~= nil and st.findObject(M.DIRT_MATERIAL) ~= nil end)
  if not have then
    pcall(function() have = fs ~= nil and fs:fileExists(M.DIRT_MATERIALS_FILE) and true or false end)
  end
  if have then return nil end
  local mp = rawget(_G, 'MPCoreNetwork')
  local onMp = false
  pcall(function() onMp = mp ~= nil and mp.isMPSession ~= nil and mp.isMPSession() and true or false end)
  stale.got = { server = tostring(sv), mp = onMp }
  return stale.got
end
M._earthModStale = earthModStale

local function payload()
  local car, anchor = where()
  local street, place, country = streetNow()
  local imp = imperial()
  local g = earthRoute()
  local gst = g and g.status and g.status() or nil
  local p = {
    version = M.VERSION, build = M.BUILD, modBuild = companion.hello and companion.hello.modBuild or nil,
    link = link.state(), linkError = link.lastError, earth = car ~= nil,
    units = imp and 'imperial' or 'metric', lang = settings.lang, settings = settings,
    car = car and { speed = fmt.speed(car.speed, imp), heading = car.heading, street = street, place = place,
                    country = country, lat = car.lat, lon = car.lon } or nil,
    dest = dest, routeError = routeError, planning = routeReq ~= nil,
    nav = navText(navState), autodrive = gst and gst.autodrive or false,
    course = courseText(crsState), trackLoading = trackReq ~= nil, trackError = trackError,
    trackSlow = trackReq ~= nil and clock - trackReq.at > 15 or nil,
    sources = companion.sources, tracksDir = companion.tracksDir, earthStale = earthModStale(),
    paint = { on = settings.paint, painting = paint.state ~= nil, painter = paint.painter ~= nil and paint.painter ~= false,
              error = paint.error, canPaint = crs ~= nil and crs.hasLine and not crs.track.approximate,
              course = type(paint.painter) == 'table' and paint.painter.course or nil, mode = paint.mode,
              clear = settings.clearCourse ~= false, outdated = companion.outdated, markers = markers.status(),
              crowds = crowds.status(), crowdSound = crowdsound.status(),
              replay = replaysync.status(), seal = paint.state and paint.seal or nil,
              code = paint.state and paint.code or nil, codeNote = paint.codeNote, codeErr = paint.codeErr,
              codeBusy = codeReq ~= nil, wet = wet.status(),
              replayGround = paint.override ~= nil,
              route = { on = settings.clearRoute ~= false, clearing = rclear.clearing, error = rclear.error },
              game = paint.mode == 'game' and (function()
                local ts = tracks.status()
                local planned, withTrack = 0, 0
                for _, n in pairs(paint.near.have) do
                  planned = planned + 1
                  if type(n) == 'number' and n > 0 then withTrack = withTrack + 1 end
                end
                return { pieces = ts.pieces, roads = ts.roads, tiles = ts.tiles, queued = ts.queued,
                         pending = paint.near.pending, errors = paint.near.errors, hooked = ts.hooked,
                         planned = planned, withTrack = withTrack, drawErrors = ts.errors, lastError = ts.lastError }
              end)() or nil },
  }
  -- Earth's own GPS when the companion has no route: distance / time from it
  if dest and not p.nav and gst then
    p.nav = { remaining = fmt.dist(gst.remaining or gst.dist, imp), eta = gst.eta and fmt.duration(gst.eta) or nil,
              bearing = gst.bearing, basic = true }
  end
  -- minimap geometry, car-relative metres
  if car then
    local r = tonumber(settings.zoom) or 600
    p.map = { radius = r, heading = car.heading }
    if navi then p.map.route = navi:mapLine(car.x, car.y, r * 0.3, r * 1.6, math.max(8, r / 50)) end
    if crs then
      local md = crs:mapData(car.x, car.y, r)
      p.map.course, p.map.wps = md.line, md.wps
    end
    -- the streets: a new selection goes out on its own hook (OffroadCompanionStreets) when due; every frame only where the
    -- car is in it
    if settings.streets ~= false then
      local sel = streetmap.select(anchor, car.x, car.y, r)
      if sel or streets.resend then
        sel = sel or (function() streetmap.invalidate(); return streetmap.select(anchor, car.x, car.y, r) end)()
        streets.resend = false
        local gh = rawget(_G, 'guihooks')
        if sel and gh and gh.trigger then gh.trigger('OffroadCompanionStreets', sel) end
      end
      p.map.sx, p.map.sy, p.map.sv = streetmap.offset(car.x, car.y)
      p.map.streetsPending, p.map.streetsError = streets.pending, streets.error
    end
    if overview.on and crs then
      local key = tostring(crs) .. '@' .. tostring(anchor)
      if overview.key ~= key then
        if not crs.e or crs.e.anchor ~= anchor then pcall(function() crs:frame(anchor) end) end
        overview.data = crs:overview(1500)
        overview.key = overview.data and key or nil
        overview.version = overview.version + 1
        local gh = rawget(_G, 'guihooks')
        if overview.data and gh and gh.trigger then
          gh.trigger('OffroadCompanionOverview', { version = overview.version, pts = overview.data.pts, wps = overview.data.wps,
                                          closed = overview.data.closed, step = overview.data.step })
        end
      end
      local o = overview.data
      if o then
        p.map.ov = { v = overview.version, x = car.x - o.ox, y = car.y - o.oy,
                     done = (crs.s and o.step > 0) and math.floor(crs.s / o.step) or 0 }
      end
    elseif overview.on then
      overview.on = false
    end
    if editor.mode() ~= 'off' or editor.state().n > 0 then
      p.map.draft, p.map.draftCps = editor.mapLines(anchor, car.x, car.y, r * 2)
    end
  end
  local es = editor.state()
  p.editor = { mode = es.mode, n = es.n, checkpoints = es.checkpoints, length = fmt.dist(es.length, imp),
               saving = edit.save ~= nil, note = edit.note, error = edit.error }
  return p
end

local function onUpdate(dtReal, dtSim)
  clock = clock + (dtReal or 0)
  local ok, msgs = pcall(link.update, dtReal or 0, decode)
  if ok then
    for _, m in ipairs(msgs) do
      local ok2, err = pcall(onMessage, m)
      if not ok2 and log then log('E', 'offroadCompanion', 'message ' .. tostring(m.type) .. ': ' .. tostring(err)) end
    end
  end
  local okR, errR = pcall(replaysync.update, dtReal, dtSim)
  if not okR and log then log('E', 'offroadCompanion', 'replay: ' .. tostring(errR)) end
  if clock - lastCheck >= M.CHECK_S then
    lastCheck = clock
    local ok3, err = pcall(check, dtReal)
    if not ok3 and log then log('E', 'offroadCompanion', 'check: ' .. tostring(err)) end
  end
  if clock < mountedUntil and clock - lastUi >= M.UI_S then
    lastUi = clock
    local ok4, p = pcall(payload)
    if ok4 then
      local gh = rawget(_G, 'guihooks')
      if gh and gh.trigger then gh.trigger('OffroadCompanionUpdate', p) end
    elseif log then
      log('E', 'offroadCompanion', 'ui: ' .. tostring(p))
    end
  end
end

local function onPreRender(dtReal)
  pcall(mphold.tick)                              -- (BeamMP: our car kept still while BeamNG.Earth holds it)
  local okT, errT = pcall(tracks.update)          -- (the in-game track's DecalRoads, a few per frame)
  if not okT and log then log('E', 'offroadCompanion', 'tracks: ' .. tostring(errT)) end
  if crs then                                     -- (the spectators near the car turn to watch it)
    local car = where()
    if car then pcall(crowds.tick, dtReal, car); pcall(crowdsound.tick, dtReal, car) end
  end
  if not crs or not ribbon.enabled then return end
  local car, anchor = where()
  if not car then return end
  crs:frame(anchor)
  ribbon.draw(crs, vec3(car.x, car.y, car.z), clock)
end

-- -- the app's calls (bngApi.engineLua) ---------------------------------------------------------------------------
function M.uiMounted(on, fresh)
  mountedUntil = on and (clock + 6) or -math.huge
  lastUi = -math.huge
  if fresh then streets.resend = true; overview.key = nil end   -- (a newly shown app has no streets / overview yet)
  return true
end

-- Search: through the Offroad Companion (Photon with a longer wait, OpenStreetMap's Nominatim when submitted: Enter or
-- the button) when it can; else BeamNG.Earth's own search (one Photon request at a time on its server).
-- The bindable key (lua/ge/extensions/core/input/actions/offroadCompanion.json): the app hides to a small button, or comes
-- back (the app keeps the state; while hidden it asks for nothing, so nothing is sent to it)
function M.toggleApp()
  local gh = rawget(_G, 'guihooks')
  if gh and gh.trigger then gh.trigger('OffroadCompanionToggle', {}) end
  return true
end

function M.uiSearch(q, submitted)
  if link.connected() and companion.features and companion.features.geocode then
    local car = where()
    local id = newId()
    if send({ type = 'geocode', id = id, q = tostring(q or ''), submitted = submitted and true or false,
              lat = car and car.lat, lon = car and car.lon, lang = settings.lang }) then
      lists[id] = false                 -- (pending: an error answer for it is kept too)
      return { id = id, via = 'companion' }
    end
  end
  local s = ext('beamngEarth_settings')
  if not s or not s.uiGeocode then return { error = 'BeamNG.Earth is not loaded' } end
  local r = s.uiGeocode(q)
  if type(r) == 'table' then r.via = 'earth' end
  return r
end
function M.uiSearchResult(id, via)
  if via == 'companion' then
    id = tonumber(id)
    local r = lists[id]
    if r then lists[id] = nil; return r end
    return nil
  end
  local s = ext('beamngEarth_settings')
  return s and s.uiGeocodeResult and s.uiGeocodeResult(id) or nil
end
function M.uiGo(lat, lon, name) return M.navigateTo(lat, lon, name) end
function M.uiStop() return M.stopNav() end
function M.uiAutodrive(on)
  local g = earthRoute()
  if not g or not g.setAutodrive then return { ok = false } end
  return { ok = true, autodrive = g.setAutodrive(on) }
end

function M.uiTrackList(source, q, radius)
  local car = where()
  local id = newId()
  local ok = send({ type = 'track_list', id = id, source = source, q = q, radius = tonumber(radius),
                    lat = car and car.lat, lon = car and car.lon })
  if not ok then return { error = 'Offroad Companion not running: start OffroadCompanion/run_companion_only' } end
  return { id = id }
end
function M.uiTrackListResult(id)
  id = tonumber(id)
  local r = lists[id]
  lists[id] = nil
  return r
end
function M.uiTrackLoad(source, ref)
  local car = where()
  local id = newId()
  if not send({ type = 'track_get', id = id, source = source, ref = ref, lat = car and car.lat, lon = car and car.lon }) then
    return { error = 'Offroad Companion not running' }
  end
  trackReq, trackError = { id = id, at = clock }, nil
  return { id = id }
end

-- course buttons: 'route_start' (road route to the start), 'route_course' (to the course ahead / next waypoint),
-- 'teleport_start', 'restart', 'skip', 'unload'
function M.uiTrackAction(action)
  if not crs then return { ok = false, error = 'no course loaded' } end
  if action == 'refresh_roads' then
    refreshRoads()
    return { ok = true }
  end
  if action == 'unload' then
    crs, crsState, lastTarget = nil, nil, nil
    ribbon.reset()
    return { ok = true }
  elseif action == 'restart' then
    crs:restart(); lastTarget = nil
    return { ok = true }
  elseif action == 'skip' then
    crs:skip(); return { ok = true }
  end
  local lat, lon, name
  if action == 'route_start' or action == 'teleport_start' then
    lat, lon = crs:startLatLon()
    name = (crs.track.name or 'Course') .. ' start'
  elseif action == 'route_course' then
    lat, lon, name = crs:targetLatLon()
    name = name or crs.track.name
  end
  if not lat then return { ok = false, error = 'the course has no start' } end
  if action == 'teleport_start' then
    local okP, places = pcall(require, 'beamngEarth/places')
    if okP and places.goTo then
      -- the server's painter plans the track around the start before the world is built there (BeamNG.Earth 1.6
      -- paints the roads into the first block's photo as soon as it lands, from what is planned by then)
      if paint.mode == 'server' and companion.features and companion.features.pose and link.connected() then
        send({ type = 'pose', lat = lat, lon = lon, speed = 0, jump = true })
        poseHoldUntil = clock + M.JUMP_HOLD_S
      end
      local ok, why = places.goTo(lat, lon, name)
      if ok then crs:restart() end
      return { ok = ok and true or false, error = (not ok) and why or nil }
    end
    return { ok = false, error = 'BeamNG.Earth is not loaded' }
  end
  return M.navigateTo(lat, lon, name, true)
end

function M.uiSet(key, value)
  if settings[key] == nil then return { ok = false } end
  if key == 'zoom' then value = math.max(150, math.min(5000, tonumber(value) or 600)) end
  if key == 'paintSize' then value = math.max(0.5, math.min(2.0, tonumber(value) or 1.0)) end
  if key == 'uiScale' then value = math.floor(math.max(0.7, math.min(2.5, tonumber(value) or 1.0)) * 20 + 0.5) / 20 end
  if key == 'paint' or key == 'clearCourse' or key == 'clearRoute' or key == 'streets' or key == 'replays' then
    value = value and true or false
  end
  if key == 'ruts' and value ~= 'auto' and value ~= 'on' and value ~= 'off' then value = 'auto' end
  if key == 'notes' and value ~= 'top' and value ~= 'bottom' and value ~= 'left' and value ~= 'right' then value = 'top' end
  if key == 'spectators' and value ~= 'off' and value ~= 'some' and value ~= 'lots' then value = 'some' end
  if key == 'nightLights' and value ~= 'off' and value ~= 'on' and value ~= 'bright' then value = 'on' end
  if key == 'crowdSound' or key == 'wetGround' then value = value and true or false end
  if key == 'rough' and value ~= 'off' and value ~= 'mild' and value ~= 'on' and value ~= 'extra' and value ~= 'auto'
      and value ~= 'default' then     -- (auto: the app's Baja; default: BeamNG.Earth's own track)
    value = 'auto'
  end
  settings[key] = value
  if key == 'ribbon' then ribbon.enabled = value and true or false; ribbon.failed = nil end
  if key == 'clearRoute' then rclear.at = -math.huge end
  if key == 'zoom' then streetmap.invalidate() end
  if key == 'markers' then settings.markers = markers.setMode(value); markersAt = -math.huge end
  if key == 'spectators' then settings.spectators = crowds.setLevel(value); markersAt = -math.huge end
  if key == 'nightLights' then settings.nightLights = crowds.setLights(value); markersAt = -math.huge end
  if key == 'crowdSound' then crowdsound.setEnabled(value) end
  if key == 'wetGround' then settings.wetGround = wet.setEnabled(value) end
  -- (a track setting changed by hand: the pasted code's terrain version no longer holds)
  if key == 'paint' or key == 'paintSize' or key == 'ruts' or key == 'rough' or key == 'clearCourse' then
    settings.groundTv, settings.groundTvFor = 0, ''
    paint.codeNote = nil
  end
  if key == 'replays' then replaysync.setEnabled(value) end
  saveSettings()
  return { ok = true, settings = settings }
end

-- (Settings' ground code) the code to the clipboard, to send a friend.
function M.uiCopyCode()
  local c = paint.state and paint.code
  local cb = rawget(_G, 'setClipboard')
  if not c then return { ok = false, error = 'no ground code yet' } end
  if cb then pcall(cb, c) end
  paint.codeNote, paint.codeErr = 'Copied ' .. c .. ': send it to your friends; they paste it here with the same course loaded', false
  lastUi = -math.huge
  return { ok = cb ~= nil, code = c }
end

-- (Settings' ground code) a friend's code pasted: the companion checks it against the loaded course and sends the
-- settings that make that ground (ground_code_result applies them).
function M.uiPasteCode(code)
  code = tostring(code or ''):gsub('^%s+', ''):gsub('%s+$', '')
  if code == '' then return { ok = false } end
  if not (link.connected() and companion.features and companion.features.ground_code) then
    paint.codeNote, paint.codeErr = 'Needs the Offroad Companion running (1.5.9 or newer)', true
    return { ok = false }
  end
  local id = newId()
  if send({ type = 'ground_code', id = id, code = code }) then
    codeReq = { id = id, at = clock }
    paint.codeNote, paint.codeErr = nil, false
  end
  lastUi = -math.huge
  return { ok = true }
end

-- (Settings' "Test markers") one post of each model file 12 m ahead of the car: which ones the game shows.
function M.uiMarkerTest()
  local car = where()
  if not car then return { ok = false, error = 'not in BeamNG.Earth' } end
  local ok, r = pcall(markers.test, car, car.heading)
  if not ok then return { ok = false, error = tostring(r) } end
  lastUi = -math.huge
  return { ok = true }
end

-- (Settings' "Test crowd") a cheer 25 m ahead of the car: whether the game plays it, and how.
function M.uiCrowdTest()
  local car = where()
  if not car then return { ok = false, error = 'not in BeamNG.Earth' } end
  local ok, err = crowdsound.test(car, car.heading)
  lastUi = -math.huge
  return { ok = ok, error = not ok and tostring(err) or nil }
end

-- The whole course on the map, or the map around the car again.
function M.uiOverview(on)
  overview.on = (on and crs ~= nil) and true or false
  if overview.on then overview.key = nil end
  lastUi = -math.huge
  return { ok = true, on = overview.on }
end

-- The track editor: action 'record' | 'plan' | 'stop' | 'add_here' | 'checkpoint' | 'add_rel' (a, b: metres east,
-- north of the car: a tap on the map) | 'undo' | 'clear' | 'save' (a: the name)
function M.uiEditor(action, a, b)
  local car, anchor = where()
  if action == 'record' or action == 'plan' then
    editor.setMode(action)
    edit.note, edit.error = nil, nil
    if action == 'record' and car then editor.add(car.lat, car.lon) end
  elseif action == 'stop' then
    editor.setMode('off')
  elseif action == 'add_here' or action == 'checkpoint' then
    if not car then return { ok = false, error = 'not in BeamNG.Earth' } end
    if action == 'add_here' then editor.add(car.lat, car.lon) else editor.checkpoint(car.lat, car.lon) end
  elseif action == 'add_rel' then
    local dx, dy = tonumber(a), tonumber(b)
    if not car or not anchor or not dx or not dy then return { ok = false } end
    local lat, lon = anchor:enuToGeodetic(car.x + dx, car.y + dy, car.z or 0)
    editor.add(lat, lon)
  elseif action == 'undo' then
    editor.undo()
  elseif action == 'clear' then
    editor.clear()
    edit.note, edit.error = nil, nil
  elseif action == 'save' then
    local pts = editor.points()
    if #pts < 2 then return { ok = false, error = 'add at least two points' } end
    local id = newId()
    local name = tostring(a or '')
    if name == '' then name = 'My track ' .. os.date('%Y-%m-%d %H%M') end
    local copy = {}
    for i, q in ipairs(pts) do copy[i] = { q[1], q[2] } end
    if not send({ type = 'track_save', id = id, name = name, points = copy, checkpoints = editor.checkpoints() }) then
      edit.error = 'Offroad Companion not running: start OffroadCompanion/run_companion_only'
      return { ok = false, error = edit.error }
    end
    edit.save, edit.error = { id = id, at = clock }, nil
  else
    return { ok = false }
  end
  return { ok = true, editor = editor.state() }
end

-- (dev) the state for the console: dump(offroadCompanion_main.debug())
function M.debug()
  return { link = link.state(), err = link.lastError, dest = dest, nav = navState, course = crsState,
           ribbonFailed = ribbon.failed, settings = settings, paintMode = paint.mode, painter = paint.painter,
           near = paint.near, tracks = tracks.status(), outdated = companion.outdated, routeClear = rclear,
           streets = { tiles = streetmap.tileCount(), pending = streets.pending, error = streets.error,
                       version = streetmap.version() }, editor = editor.state(), markers = markers.status(),
           replay = replaysync.status() }
end

-- Replays in BeamNG.Earth's world (replaysync.lua): the game side
replaysync.setEnv({
  state = function() local c = earthCore(); return c and c._state and c._state() or nil end,
  mod = function(name) return package.loaded[name] end,       -- (BeamNG.Earth's own modules, only when it is loaded)
  read = function(path)
    local rd = rawget(_G, 'jsonReadFile')
    if not rd then return nil end
    local ok, t = pcall(rd, path)
    return ok and t or nil
  end,
  write = function(path, t) local wr = rawget(_G, 'jsonWriteFile'); if wr then wr(path, t, false) end end,
  remove = function(path) local fs = rawget(_G, 'FS'); if fs and fs.removeFile then fs:removeFile(path) end end,
  clock = function() return clock end,
  time = function() return os.time() end,
  setPause = function(on) local s = rawget(_G, 'simTimeAuthority'); if s and s.pause then s.pause(on) end end,
  isPaused = function() local s = rawget(_G, 'simTimeAuthority'); return s and s.getPause and s.getPause() or false end,
  pollState = function()
    local r = rawget(_G, 'core_replay')
    if r and type(r.getState) == 'function' then return r.getState() end
    return nil
  end,
  log = function(level, text) if log then log(level, 'offroadCompanion', text) end end,
  diag = function()          -- (the playback's first seconds: what vehicles the game has)
    local out = {}
    local okB, n = pcall(function() return be:getObjectCount() end)
    out[#out + 1] = 'vehicles ' .. tostring(okB and n or '?')
    local okP, id = pcall(function() return be:getPlayerVehicleID(0) end)
    out[#out + 1] = 'player id ' .. tostring(okP and id or '?')
    local okV, v = pcall(function()
      local o = be:getObject(0)
      if not o then return 'none' end
      local p = o:getPosition()
      local okJ, jb = pcall(function() return o:getJBeamFilename() end)
      return string.format('#%s %s at %.0f %.0f %.0f', tostring(o:getID()), tostring(okJ and jb or ''), p.x, p.y, p.z)
    end)
    out[#out + 1] = 'first ' .. tostring(okV and v or '?')
    return table.concat(out, ', ')
  end,
  message = function(text) message(text, 8) end,
  -- the course's ground (the companion's seal: the same seal, the same ground; nil when nothing is painted)
  terrain = function()
    if paint.override or not paint.state or not paint.seal then return nil end
    local w = paintWanted()
    if not w.enabled then return nil end
    return { trackId = w.trackId, scale = w.scale, paint = w.paint, clear = w.clear, ruts = w.ruts, rough = w.rough,
             seal = paint.seal, tv = paint.terrain, earth = paint.earth }
  end,
  seal = function() return paint.state and paint.seal or nil end,
  earth = function() return paint.earth end,      -- (BeamNG.Earth's version, as the companion found it)
  snapshot = function(name)       -- the ground kept with the recording (the companion copies its windows)
    if not (link.connected() and companion.features and companion.features.terrain_snapshot) then return false end
    return send({ type = 'terrain_snapshot', id = newId(), name = name }) and true or false
  end,
  applyTerrain = function(t, pin)
    if not (link.connected() and companion.features and companion.features.terrain_snapshot) then return false end
    paint.override = { trackId = t.trackId, scale = t.scale, paint = t.paint, clear = t.clear, ruts = t.ruts,
                       rough = t.rough, tv = t.tv, seal = t.seal, pin = pin }
    syncPaint()
    return true
  end,
  terrainReady = function()
    local w = paint.override and paintWanted()
    return w and paint.state == w.key and paint.stateAt ~= nil and clock - paint.stateAt >= M.TERRAIN_SETTLE_S or false
  end,
  restoreTerrain = function()
    if not paint.override then return false end
    paint.override = nil
    syncPaint()
    return true
  end,
  canToggle = function()
    local r = rawget(_G, 'core_replay')
    return r ~= nil and type(r.toggleRecording) == 'function'
  end,
  toggleRecording = function()
    local r = rawget(_G, 'core_replay')
    if r and type(r.toggleRecording) == 'function' then r.toggleRecording() else error('no core_replay.toggleRecording') end
  end,
  fileSize = function(path)
    local fs = rawget(_G, 'FS')
    if not fs then return nil end
    if fs.stat then
      local ok, st = pcall(function() return fs:stat(path) end)
      if ok and type(st) == 'table' then return tonumber(st.filesize or st.size) end
    end
    if fs.fileSize then
      local ok, n = pcall(function() return fs:fileSize(path) end)
      if ok then return tonumber(n) end
    end
    return nil
  end,
})

M.onReplayStateChanged = function(s)
  local ok, err = pcall(replaysync.onHook, s)
  if not ok and log then log('E', 'offroadCompanion', 'replay: ' .. tostring(err)) end
end

-- Leaving a BeamMP server (BeamMP's own hook): the player's own copy of this mod switched back on. Joining, BeamMP
-- switches off every mod the server did not send, and leaving it deletes the server's copy and leaves the player's off
-- (BeamNG.Earth 1.6.2 does the same for its own mod). Runs in the server's copy (when the server sends this mod);
-- a player without it: nothing (the mod manager has no such mod).
M.LOCAL_MOD = 'offroad_companion'
function M.onBeamMPServerLeave()
  local mm = rawget(_G, 'core_modmanager')
  if type(mm) ~= 'table' or type(mm.getModDB) ~= 'function' or type(mm.activateMod) ~= 'function' then return false end
  local ok, entry = pcall(mm.getModDB, M.LOCAL_MOD)
  if not ok or type(entry) ~= 'table' or entry.active then return false end
  if log then log('I', 'offroadCompanion', 'BeamMP: left the server: Offroad Companion (' .. M.LOCAL_MOD .. ') switched back on') end
  return (pcall(mm.activateMod, M.LOCAL_MOD))
end

M.onUpdate = onUpdate

M.onPreRender = onPreRender
M.onExtensionLoaded = function() loadSettings(); pcall(tracks.install); pcall(markers.ensureMaterials) end
M.onExtensionUnloaded = function() pcall(tracks.uninstall); pcall(wet.clear); pcall(wet.restore); pcall(wet.restoreLook) end
M.onClientEndMission = function()
  pcall(wet.clear)
  pcall(wet.restore)
  pcall(wet.restoreLook)
  streetmap.reset()
  pcall(markers.clear)
  pcall(crowds.clear)
  pcall(crowdsound.stopAll)
  if crs then crs.e = nil end
  if navi then navi.e = nil end
  ribbon.reset()
end

return M
