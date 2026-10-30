-- Replays in BeamNG.Earth's world (the user, 2026-10-22: watching a replay, "the car drives well ... but the ground is
-- not what it was", several kilometres back from where the recording ended).
--
-- Why: BeamNG.Earth's world is a local frame around an anchor (a latitude / longitude), moved to a new anchor every
-- ~10 km as you drive (a rebase: the world and the car shift together). A replay stores the car's positions as they
-- were in the frame of their moment; played back later, BeamNG.Earth's frame is wherever the world is now, so the
-- recorded positions land somewhere else on the Earth: the car floats over the wrong ground, and BeamNG.Earth even
-- rebases and drop-holds around the replayed car as if it were driven there.
--
-- What this does:
--   recording: while the game records a replay, the anchor of each moment and the car's position in it are logged
--     every SAMPLE_S (a small file per recording, settings/offroadCompanion/replays/);
--   playback: the replayed car's position is matched to a log (by place: the replayed positions are the recorded ones,
--     so no replay clock is needed, and seeking works), and BeamNG.Earth is moved to that moment's anchor, its ground
--     centred on the car; the game is paused (as BeamNG.Earth's own drop hold does) until that ground is in. Where the
--     recording rebased, the playback does too. Meanwhile BeamNG.Earth's own rebases, drop hold and edge guard leave the
--     replayed car alone (they would move or pause it), and are back as they were once the playback ends.
-- Recordings made before this have no log: their playback is left as it was.
--
-- The ground itself (the user, 2026-10-22: "it needs to be more deterministic ... everyone races the exact same track
-- down to every bump and dip"): a recording also notes the course's ground (its course, track settings, terrain
-- version and seal: the companion's name for exactly that ground), and the companion keeps a snapshot of it under the
-- recording's name. A playback whose ground is not that one any more (other settings, another course loaded, a newer
-- terrain version) asks for the recorded one (the course and settings, the server pinned to the snapshot), rebuilds
-- the world's ground with it before the car moves, and gives the player's own back when the playback ends.
--
-- The game side is behind `env` (main.lua gives the real one; the tests a fake).
local M = {}

M.SAMPLE_S = 0.25           -- s of recording between two logged positions
M.CHECK_S = 0.2             -- s between two matches during a playback
M.MATCH_M = 8.0             -- m: a logged stretch this near the replayed car is where it is
M.WINDOW = 80               -- samples either side of the last match searched first
M.LOST_S = 1.0              -- s between two searches of every log while the car matches none
M.POLL_S = 1.0              -- s between two looks at the replay state when the game sends no hook
M.READY_MARGIN_M = 40       -- the ground counts as in once the car is this far inside the collidable block
M.WAIT_MAX_S = 20           -- s at most paused for a switch ...
M.RETRY_S = 30              -- ... then that frame is not asked for again for this long
M.KEEP = 30                 -- recordings' logs kept
M.DIR = '/settings/offroadCompanion/replays/'
M.OLD_DIR = '/settings/earthGps/replays/'    -- (recordings logged before 1.2.0, under the project's old name)
M.REQ_BASE = 7000000        -- our prepare_anchor request ids (BeamNG.Earth counts its own from 1)
M.enabled = true
-- BeamNG cannot read back a replay file over 2 GB (2^31 bytes: the user's 64-minute recording, 2.24 GB, listed as
-- "16384 PB" and played with no car after a restart, 2026-10-22). A recording is split before that: stopped (saved)
-- and started again, a second apart.
M.SPLIT_BYTES = 1.8e9
M.RATE_DEFAULT = 650e3      -- bytes a second of recording when the game cannot say the file's size (the user's: 590e3)
M.SIZE_CHECK_S = 5
M.RESTART_S = 1.0
-- A playback after a restart (the user, 2026-10-22: the camera went where the car would be, but no car, even for a small
-- replay): while the replay plays BeamNG.Earth's own setting down of the car (after its level start and its teleports)
-- is called off, the world is matched by the camera when there is no car to match, and what the game has is logged.
M.CAM_MATCH_M = 25.0        -- m: the camera follows the car this far off at most (the orbit camera)
-- BeamNG.Earth 1.6 places the car on a provisional block after a jump (no road levelling, no track relief: its grader
-- is not run) and swaps in the graded one when it is built (terrain_refresh): a playback waits for that one, the
-- ground the recording was driven on, up to WAIT_GRADED_S.
M.WAIT_GRADED_S = 90
M.DIAG_S, M.DIAG_FOR_S = 2.0, 30.0
M.TERRAIN_WAIT_S = 20       -- s at most waiting for the recorded ground to be planned before the world is rebuilt
M.RESTORE_S = 6             -- s after a playback before the ground is built again with the player's own settings

local env = nil
local mode = 'idle'         -- 'idle' | 'recording' | 'playback'
local rec = nil             -- the log being recorded: { anchors = {{lat, lon}...}, s = {a, x, y, z, ...} (flat), t, next }
local logs = nil            -- playback: { {name, anchors, s} ... }
local match = nil           -- { log, i }
local sw = nil              -- the switch under way: { lat, lon, id, at, committed, pausedByUs }
local checkAt = 0
local patched = nil
local stats = { switches = 0, lost = 0, lastFile = nil, note = nil }
local reqN = 0
local lostUntil = 0
local gaveUp = nil          -- { lat, lon, until }: a switch that did not come in time
local hookSeen, pollAt = false, 0
local split = nil           -- { phase = 'stopping' | 'starting', at }
local sizeAt = 0
local diag = nil            -- { from, at }: the playback's first seconds logged
local terr = nil            -- the playback's ground: { log = name, phase = 'waiting' | 'done', at, pausedByUs, applied }
local restoreAt = nil       -- after a playback that used its recorded ground: when to build the player's own again

function M.setEnv(e) env = e end

-- 'recording' | 'playback' | 'idle' from the game's replay state (onReplayStateChanged's table, or its state string)
function M.parseState(s)
  local v = s
  if type(s) == 'table' then v = s.state or s.mode or s.status end
  v = tostring(v or ''):lower()
  if v:find('record') then return 'recording' end
  if v:find('play') then return 'playback' end
  return 'idle'
end

local function anchorOf(st)
  local a = st and st.anchor
  if a and a.lat and a.lon then return a.lat, a.lon end
  return nil
end

local function same(lat1, lon1, lat2, lon2)
  return lat1 and lat2 and math.abs(lat1 - lat2) < 1e-9 and math.abs(lon1 - lon2) < 1e-9
end

-- -- recording ----------------------------------------------------------------------------------------------------
local lastSaved = nil       -- the file of the last recording saved (its size is not the next one's)
local function terrainNow()
  if not env.terrain then return nil end
  local ok, t = pcall(env.terrain)
  return ok and type(t) == 'table' and t or nil
end

local function startRecording(file)
  rec = { anchors = {}, s = {}, t = 0, next = 0, started = env.time and env.time() or 0,
          file = (file and file ~= lastSaved) and file or nil, terrain = terrainNow() }
end

local function sample(st)
  local lat, lon = anchorOf(st)
  local pl = st and st.player
  if not lat or not pl or pl.camera or st.rebasing or st.placeFrames then return end   -- (positions in neither frame;
                                                                                        -- no car: nothing to log)
  local na = #rec.anchors
  local last = rec.anchors[na]
  if not last or not same(last[1], last[2], lat, lon) then
    rec.anchors[na + 1] = { lat, lon }
    na = na + 1
  end
  local s = rec.s
  local n = #s
  s[n + 1], s[n + 2], s[n + 3], s[n + 4] = na, math.floor(pl.x * 10 + 0.5) / 10, math.floor(pl.y * 10 + 0.5) / 10,
    math.floor(pl.z * 10 + 0.5) / 10
end

local function fileSize(file)
  if not file or not env.fileSize then return nil end
  local ok, n = pcall(env.fileSize, file)
  return ok and type(n) == 'number' and n > 0 and n or nil
end

-- Bytes a second the recordings made so far took (the largest of the last few), or the default.
local function rate()
  local idx = env.read(M.DIR .. 'index.json')
  local r = type(idx) == 'table' and tonumber(idx.rate) or nil
  return r and r > 1000 and r or M.RATE_DEFAULT
end

local function saveRecording(file)
  local size, secs = fileSize(file), rec and rec.t or 0
  if size and secs > 30 then           -- (learnt: how fast this player's recordings grow)
    local idx = env.read(M.DIR .. 'index.json')
    idx = type(idx) == 'table' and type(idx.list) == 'table' and idx or { list = {} }
    local r = size / secs
    idx.rate = math.max(r, (tonumber(idx.rate) or 0) * 0.8)
    pcall(env.write, M.DIR .. 'index.json', idx)
  end
  lastSaved = file
  if not rec or #rec.s < 8 then rec = nil; return end
  local name = 'rec_' .. tostring(rec.started or 0) .. '_' .. tostring(#rec.s)
  local obj = { version = 1, file = file, anchors = rec.anchors, s = rec.s, seconds = rec.t, sample = M.SAMPLE_S }
  -- the ground it was driven on: noted, and kept by the companion under this recording's name
  local t0, t1 = rec.terrain, terrainNow()
  local t = t0 or t1
  if t then
    obj.terrain = t
    if t0 and t1 and t0.seal ~= t1.seal then obj.terrain.changed = t1.seal end   -- (settings changed while recording)
    if env.snapshot then
      local ok, sent = pcall(env.snapshot, name)
      obj.terrain.kept = ok and sent or false
    end
  end
  pcall(env.write, M.DIR .. name .. '.json', obj)
  local idx = env.read(M.DIR .. 'index.json')
  idx = type(idx) == 'table' and type(idx.list) == 'table' and idx or { list = {} }
  table.insert(idx.list, 1, { name = name, file = file, seconds = rec.t, anchors = #rec.anchors, bytes = size })
  while #idx.list > M.KEEP do
    local old = table.remove(idx.list)
    if env.remove then pcall(env.remove, M.DIR .. old.name .. '.json') end
  end
  pcall(env.write, M.DIR .. 'index.json', idx)
  if env.log then env.log('I', string.format('replay: logged %d places in %d frame(s) of the world for %s', #rec.s / 4,
    #rec.anchors, tostring(file or name))) end
  rec = nil
end

-- -- playback -------------------------------------------------------------------------------------------------------
local function baseName(p)
  p = tostring(p or ''):gsub('\\', '/')
  return p:match('([^/]+)$') or p
end

local function loadLogs(file)
  local out = {}
  for _, dir in ipairs({ M.DIR, M.OLD_DIR }) do      -- (the old name's logs too: recordings before 1.2.0)
    local idx = env.read(dir .. 'index.json')
    for _, e in ipairs(type(idx) == 'table' and type(idx.list) == 'table' and idx.list or {}) do
      local l = env.read(dir .. e.name .. '.json')
      if type(l) == 'table' and type(l.s) == 'table' and type(l.anchors) == 'table' and #l.s >= 8 then
        l.name = e.name
        -- the recording being played first, when the game says which
        if file and l.file and baseName(l.file) == baseName(file) then table.insert(out, 1, l) else out[#out + 1] = l end
      end
    end
  end
  return out
end

-- Distance (m) from p to the logged stretch from sample i to i + 1 (one frame), or to sample i alone.
local function segDist(s, i, x, y, z)
  local k = (i - 1) * 4
  local a, ax, ay, az = s[k + 1], s[k + 2], s[k + 3], s[k + 4]
  local b, bx, by, bz = s[k + 5], s[k + 6], s[k + 7], s[k + 8]
  if not b or b ~= a then
    return math.sqrt((x - ax) ^ 2 + (y - ay) ^ 2 + (z - az) ^ 2)
  end
  local dx, dy, dz = bx - ax, by - ay, bz - az
  local L2 = dx * dx + dy * dy + dz * dz
  local t = L2 > 1e-9 and math.max(0, math.min(1, ((x - ax) * dx + (y - ay) * dy + (z - az) * dz) / L2)) or 0
  return math.sqrt((x - ax - t * dx) ^ 2 + (y - ay - t * dy) ^ 2 + (z - az - t * dz) ^ 2)
end

-- Pure: the logged moment the car at (x, y, z) is at: (log, sample index) or nil. Near the last match first.
function M.find(list, last, x, y, z)
  local best, bl, bi = M.MATCH_M, nil, nil
  if last then
    local s = last.log.s
    local n = #s / 4
    for i = math.max(1, last.i - M.WINDOW), math.min(n, last.i + M.WINDOW) do
      local d = segDist(s, i, x, y, z)
      if d < best then best, bl, bi = d, last.log, i end
    end
    if bl then return bl, bi end
  end
  for _, l in ipairs(list) do
    local s = l.s
    for i = 1, #s / 4 do
      local d = segDist(s, i, x, y, z)
      if d < best - 0.5 then best, bl, bi = d, l, i end
    end
    if bl and best < 2.0 then break end        -- (the recording being played, or an exact match: enough)
  end
  return bl, bi
end

local function setPause(on)
  if env.setPause then pcall(env.setPause, on) end
end
local function paused()
  return env.isPaused and env.isPaused() or false
end

-- BeamNG.Earth's own reactions to the replayed car, off during a playback: its rebase (it would move the replayed car
-- and the world to a new anchor of its own), drop hold and edge guard (they would pause or move it).
local function patch(on)
  if on and not patched then
    patched = {}
    local function wrap(modName, fn, quiet)
      local m = env.mod(modName)
      if m and type(m[fn]) == 'function' then
        local orig = m[fn]
        patched[#patched + 1] = { m = m, fn = fn, orig = orig }
        m[fn] = function(...) return quiet end
      end
    end
    wrap('beamngEarth/rebase', 'decide', nil)
    wrap('beamngEarth/drophold', 'observe', nil)
    wrap('beamngEarth/edgeguard', 'update', nil)
    -- (BeamMP: no moving onto the other players' origin while the recording's world is shown)
    local ms = M.inBeamMP() and env.mod('beamngEarth/mpsession') or nil
    if ms and ms.SHARE_GEN == true then
      patched[#patched + 1] = { m = ms, fn = 'SHARE_GEN', orig = true }
      ms.SHARE_GEN = false
    end
    -- BeamNG.Earth's messages, read as its core gets them (net.update): whether our switch's block is the provisional
    -- one and when the graded one came. (A teleport commits as its anchor_ready arrives, so its pending request never
    -- shows "ready"; and since 1.6.2 a graded block that comes first is kept and put in right after the commit.)
    local net = env.mod('beamngEarth/net')
    if net and type(net.update) == 'function' then
      local orig = net.update
      patched[#patched + 1] = { m = net, fn = 'update', orig = orig }
      net.update = function(...)
        local out = orig(...)
        if type(out) == 'table' then
          for _, msg in ipairs(out) do pcall(M.observe, msg) end
        end
        return out
      end
    end
  elseif not on and patched then
    for _, p in ipairs(patched) do p.m[p.fn] = p.orig end
    patched = nil
  end
end

-- A message BeamNG.Earth's core got (through the net.update wrapper during a playback).
function M.observe(msg)
  if type(msg) ~= 'table' or not sw then return end
  if msg.type == 'anchor_ready' and msg.requestId == sw.id then
    sw.anchorId = msg.anchorId
    if msg.provisional then sw.provisional = true end
  elseif msg.type == 'terrain_refresh' and sw.anchorId ~= nil and msg.anchorId == sw.anchorId then
    sw.graded = true
  end
end

local function groundReady(st, x, y)
  if not st or not st.block or st.terrainPending then return false end
  local lat = env.mod('beamngEarth/lattice')
  if not lat or not lat.groundBox then return true end
  local x0, y0, x1, y1 = lat.groundBox(st.block.cx, st.block.cy)
  local m = M.READY_MARGIN_M
  return x >= x0 + m and x <= x1 - m and y >= y0 + m and y <= y1 - m
end

-- In a BeamMP session (BeamNG.Earth 1.6)? Each player there has their own world origin (BeamNG.Earth's mpanchor.lua:
-- "every player rebases on their own schedule"; the others' cars are converted between origins), so a replay moves
-- ours as it does alone (the user, 2026-10-25: "replays are broken, tested it on an empty multiplayer server": 1.6.0's
-- notion that the origin was shared kept the world where it was, the replayed car out in the void). Only BeamNG.Earth's
-- moving onto the others' origin (mpsession's converge, when its shared generation is on) waits while one plays.
function M.inBeamMP()
  local mp = env.mod('beamngEarth/beammp')
  if not mp or type(mp.inSession) ~= 'function' then return false end
  local ok, on = pcall(mp.inSession)
  return ok and on and true or false
end

-- Move BeamNG.Earth to anchor (lat, lon) with its ground centred near (x, y) of that frame (a teleport of the world,
-- not of the car: BeamNG.Earth's own placing of the car is called off when it commits). Declared a teleport
-- (purpose, BeamNG.Earth 1.6.3: its quick first block and the old place's work paused, also under 20 km away).
local function requestSwitch(st, lat, lon, x, y)
  local net = env.mod('beamngEarth/net')
  if not net or not net.send or (net.isConnected and not net.isConnected()) then
    stats.note = 'BeamNG.Earth server not connected'
    return false
  end
  local cx, cy = 0, 0
  local follow = env.mod('beamngEarth/follow')
  if follow and follow.target then
    local ok, a, b = pcall(follow.target, x, y, 0, 0)
    if ok and a then cx, cy = a, b end
  end
  reqN = reqN + 1
  local id = M.REQ_BASE + reqN
  st.pending = { requestId = id, purpose = 'teleport', lat = lat, lon = lon, sentAt = st.clock }
  net.send({ type = 'prepare_anchor', requestId = id, lat = lat, lon = lon, cx = cx, cy = cy, purpose = 'teleport' })
  -- (the block commits counted from the ask: BeamNG.Earth 1.6.2 keeps a graded block that comes before the teleport's
  -- commit and puts it in right after it, possibly before this sees the commit)
  sw = { lat = lat, lon = lon, id = id, at = env.clock(), committed = false, pausedByUs = false,
         follows = st.followCount or 0 }
  if not paused() then setPause(true); sw.pausedByUs = true end
  stats.switches = stats.switches + 1
  stats.note = nil
  if env.log then env.log('I', string.format('replay: the world to the recording\'s frame at %.5f, %.5f', lat, lon)) end
  return true
end

local function endSwitch()
  if sw and sw.pausedByUs and paused() then setPause(false) end
  sw = nil
  stats.grading = nil
end

local function playbackStep(st, everyFrame)
  -- BeamNG.Earth sets the player's car down after its level start and its teleports (spawn.safeTeleport): never the
  -- replayed car
  if st.placeFrames or st.floorZ then st.placeFrames, st.floorZ, st.floorUntil = nil, nil, nil end
  if sw then
    local p = st.pending
    if p and p.requestId == sw.id and p.ready and p.msg and p.msg.provisional then
      sw.provisional = true       -- (BeamNG.Earth 1.6: the graded block follows: terrain_refresh)
    end
    local lat, lon = anchorOf(st)
    if same(lat, lon, sw.lat, sw.lon) then
      if not sw.committed then
        sw.committed = true
      end
      -- BeamNG.Earth's teleport sets the car down at the anchor: not the replayed car
      st.placeFrames, st.floorZ, st.floorUntil = nil, nil, nil
      local pl = st.player
      local graded = not sw.provisional or sw.graded or (st.followCount or 0) > (sw.follows or 0)
      stats.grading = sw.provisional and not graded or nil
      if pl and graded and groundReady(st, pl.x, pl.y) then endSwitch() end
    elseif st.pending == nil or (st.pending.requestId ~= sw.id) then
      -- our request was answered with an error, or replaced: give up this one (asked again at the next check)
      if not sw.committed then endSwitch() end
    end
    if sw and env.clock() - sw.at > (sw.provisional and M.WAIT_GRADED_S or M.WAIT_MAX_S) then
      if env.log then env.log('W', 'replay: the ground did not come in time; playing on') end
      gaveUp = { lat = sw.lat, lon = sw.lon, ['until'] = env.clock() + M.RETRY_S }
      endSwitch()
    end
    if sw then return end
  end
  if everyFrame then return end
  local pl = st.player
  local tol = M.MATCH_M
  -- (no car: where the camera is, a little off it; BeamNG.Earth 1.6 makes the camera its player then: camera = true)
  if (not pl or pl.camera) and st.cam and st.cam.x then
    pl, tol = st.cam, M.CAM_MATCH_M
  elseif pl and pl.camera then
    tol = M.CAM_MATCH_M
  end
  if not pl then return end
  if not match and env.clock() < lostUntil then return end
  local keep = M.MATCH_M
  M.MATCH_M = tol
  local l, i = M.find(logs, match, pl.x, pl.y, pl.z)
  M.MATCH_M = keep
  if not l then
    if match then stats.lost = stats.lost + 1 end
    match = nil
    lostUntil = env.clock() + M.LOST_S
    stats.note = #logs == 0 and 'no log of this recording (recorded before this version, or elsewhere)' or
      'this moment is not in the logs'
    return
  end
  match = { log = l, i = i }
  stats.note = nil
  local a = l.anchors[l.s[(i - 1) * 4 + 1]]
  if M.terrainStep(st, l, a, pl) then return end
  local lat, lon = anchorOf(st)
  if a and not same(lat, lon, a[1], a[2]) then
    if gaveUp and same(gaveUp.lat, gaveUp.lon, a[1], a[2]) and env.clock() < gaveUp['until'] then return end
    requestSwitch(st, a[1], a[2], pl.x, pl.y)
  end
end

-- The playback's ground: the recorded one when the ground now is not it. True while it is being made ready (the
-- playback paused); then the world is moved / rebuilt around the car with it (requestSwitch, even to the same frame).
function M.terrainStep(st, l, a, pl)
  if terr and terr.log == l.name and terr.phase == 'done' then return false end
  if not terr or terr.log ~= l.name then
    local want = l.terrain
    local have = env.seal and env.seal() or nil
    terr = { log = l.name, phase = 'done', at = env.clock(), applied = terr and terr.applied or false }
    if not want then
      stats.terrain = 'recorded before replays kept their ground: the ground is today\'s'
      return false
    end
    if want.seal and want.seal == have then
      stats.terrain = 'the ground it was recorded on (' .. tostring(want.seal) .. ')'
      return false
    end
    if not (env.applyTerrain and env.applyTerrain(want, l.name)) then
      stats.terrain = 'the recorded ground (' .. tostring(want.seal) .. ') needs the Offroad Companion; the ground is today\'s'
      return false
    end
    terr.phase, terr.applied = 'waiting', true
    if not paused() then setPause(true); terr.pausedByUs = true end
    stats.terrain = 'getting the recorded ground (' .. tostring(want.seal) .. ')'
    if env.log then env.log('I', string.format('replay: ground %s recorded, %s now: the recorded one', tostring(want.seal),
      tostring(have))) end
    return true
  end
  -- waiting for the companion and the server to have it
  local ready = env.terrainReady and env.terrainReady()
  if not ready and env.clock() - terr.at < M.TERRAIN_WAIT_S then return true end
  terr.phase = 'done'
  local have = env.seal and env.seal() or nil
  stats.terrain = (have and l.terrain.seal == have) and ('the ground it was recorded on (' .. tostring(have) .. ')')
    or ('the recorded ground ' .. tostring(l.terrain.seal) .. ' could not be had exactly (now ' .. tostring(have) .. ')')
  local e = env.earth and env.earth() or nil
  if l.terrain.earth and e and l.terrain.earth ~= e then
    -- (the course's ground is the recorded one, but BeamNG.Earth's own under it is this version's)
    stats.terrain = 'the track as recorded, on BeamNG.Earth ' .. tostring(e) .. '\'s ground (recorded on '
      .. tostring(l.terrain.earth) .. ': its roads and levelling may differ a little)'
  end
  if a and requestSwitch(st, a[1], a[2], pl.x, pl.y) then
    if terr.pausedByUs then sw.pausedByUs = true end      -- (our pause: let go once the ground is in)
  elseif terr.pausedByUs then
    setPause(false)
  end
  terr.pausedByUs = false
  return true
end

-- After a playback that used its recorded ground: the player's own settings back, and the ground around the car built
-- again with them (BeamNG.Earth's resync: the same frame, a new block; nothing moves).
local function restoreStep()
  if not restoreAt or env.clock() < restoreAt then return end
  restoreAt = nil
  local st = env.state()
  local lat, lon = anchorOf(st)
  local net = env.mod('beamngEarth/net')
  if not lat or not net or not net.send or (net.isConnected and not net.isConnected()) or st.pending then return end
  local pl = st.player
  local cx, cy = 0, 0
  local follow = env.mod('beamngEarth/follow')
  if pl and follow and follow.target then
    local ok, x, y = pcall(follow.target, pl.x, pl.y, 0, 0)
    if ok and x then cx, cy = x, y end
  end
  reqN = reqN + 1
  local id = M.REQ_BASE + reqN
  st.pending = { requestId = id, purpose = 'resync', lat = lat, lon = lon, sentAt = st.clock }
  net.send({ type = 'prepare_anchor', requestId = id, lat = lat, lon = lon, cx = cx, cy = cy, purpose = 'teleport' })
  if env.log then env.log('I', 'replay: the ground around the car built again with your own settings') end
end

-- -- the game's hooks -------------------------------------------------------------------------------------------------
function M.onState(s)
  if not env then return end
  local new = M.parseState(s)
  local file = type(s) == 'table' and (s.loadedFile or s.file or s.filename) or nil
  if file then stats.lastFile = file end
  if new == mode then return end
  if env.log then
    local keys = {}
    if type(s) == 'table' then for k in pairs(s) do keys[#keys + 1] = tostring(k) end end
    table.sort(keys)
    env.log('I', string.format('replay: %s -> %s (%s; fields %s)', mode, new, tostring(file), table.concat(keys, ',')))
  end
  if mode == 'recording' then saveRecording(file or (rec and rec.file) or stats.lastFile) end
  if mode == 'playback' then
    endSwitch()
    patch(false)
    logs, match = nil, nil
    M.endTerrain()
  end
  mode = new
  if not M.enabled then return end
  if mode == 'recording' then startRecording(file) end
  if mode == 'playback' then
    logs = loadLogs(file)
    match, checkAt = nil, 0
    terr, stats.terrain = nil, nil
    diag = { from = env.clock(), at = 0 }
    patch(true)
    if env.log then env.log('I', string.format('replay: %d recording log(s) to match', #logs)) end
  end
end

function M.onHook(s)
  hookSeen = true
  M.onState(s)
end

function M.update(dtReal, dtSim)
  if not env then return end
  if not hookSeen and env.pollState and env.clock() >= pollAt then     -- (no hook from the game: its state asked)
    pollAt = env.clock() + M.POLL_S
    local ok, s = pcall(env.pollState)
    if ok and s ~= nil then M.onState(s) end
  end
  if split then M.splitStep() end
  if restoreAt and mode ~= 'playback' then restoreStep() end
  if mode == 'idle' then return end
  local st = env.state()
  if mode == 'recording' and rec then
    rec.t = rec.t + math.max(0, dtSim or dtReal or 0)
    if env.clock() >= sizeAt then
      sizeAt = env.clock() + M.SIZE_CHECK_S
      M.checkSize()
      if not rec then return end            -- (split: this recording saved, the next one starts)
    end
    if rec.t >= rec.next then
      rec.next = math.max(rec.next + M.SAMPLE_S, rec.t - M.SAMPLE_S)
      sample(st)
    end
  elseif mode == 'playback' and logs and st then
    local now = env.clock()
    if diag and now >= diag.at and now - diag.from <= M.DIAG_FOR_S then
      diag.at = now + M.DIAG_S
      if env.log then
        local a = st.anchor
        local pl, c = st.player, st.cam
        env.log('I', string.format('replay: car %s, camera %s, world at %s, pending %s, flat %s, %s',
          pl and string.format('%.0f %.0f %.0f', pl.x, pl.y, pl.z) or 'none',
          c and c.x and string.format('%.0f %.0f %.0f', c.x, c.y, c.z) or 'none',
          a and string.format('%.5f %.5f', a.lat, a.lon) or 'none',
          st.pending and tostring(st.pending.purpose) or 'no', tostring(st.flat),
          env.diag and tostring(env.diag()) or ''))
      end
    end
    local due = now >= checkAt
    if due then checkAt = now + M.CHECK_S end
    playbackStep(st, not due)
  end
end

-- The recording near the size BeamNG can read back: split it (stopped and saved, started again), or said when the game
-- has no way to.
function M.checkSize()
  if not rec or split then return end
  local size = fileSize(rec.file)
  local est = size or rate() * rec.t
  rec.bytes = est
  if est < M.SPLIT_BYTES then return end
  if env.toggleRecording and not rec.noSplit and (not env.canToggle or env.canToggle()) then
    split = { phase = 'stopping', at = env.clock() }
    stats.splits = (stats.splits or 0) + 1
    if env.log then env.log('I', string.format('replay: the recording is near 2 GB (%.2f GB%s): split', est / 1e9,
      size and '' or ', estimated')) end
    if env.message then env.message('Replay: recording split in two (BeamNG cannot play back a replay over 2 GB)') end
    pcall(env.toggleRecording)
  else
    if env.message and not rec.warned then
      env.message('Replay: this recording is near 2 GB, which BeamNG cannot play back. Stop it (Alt+R) and start a new one.')
    end
    rec.warned = true
  end
end

function M.splitStep()
  local now = env.clock()
  if split.phase == 'stopping' then
    if mode == 'recording' and now - split.at > M.RESTART_S * 3 then
      -- the game did not say it stopped: never toggled again blind (that could stop the recording for good)
      if env.log then env.log('W', 'replay: the split did not stop the recording; left as it is') end
      if env.message then env.message('Replay: this recording is near 2 GB, which BeamNG cannot play back. Stop it (Alt+R) and start a new one.') end
      if rec then rec.warned, rec.noSplit = true, true end
      split = nil
    elseif mode ~= 'recording' and now - split.at >= M.RESTART_S then
      split = { phase = 'starting', at = now }
      pcall(env.toggleRecording)
    end
  elseif split.phase == 'starting' then
    if mode == 'recording' or now - split.at > 5 then
      if mode ~= 'recording' and env.log then env.log('W', 'replay: the new recording did not start') end
      split = nil
    end
  end
end

-- The player's own ground back after a playback that used its recorded one.
function M.endTerrain()
  if terr and terr.pausedByUs and paused() then setPause(false) end
  if terr and terr.applied and env.restoreTerrain then
    local ok, done = pcall(env.restoreTerrain)
    if ok and done then restoreAt = env.clock() + M.RESTORE_S end
  end
  terr = nil
end

-- Off: a playback under way is left alone from now on (BeamNG.Earth's own behaviour back).
function M.setEnabled(on)
  M.enabled = on and true or false
  if not M.enabled then
    endSwitch()
    patch(false)
    logs, match = nil, nil
    M.endTerrain()
    if mode == 'recording' then rec = nil end
  end
end

function M.status()
  return { mode = mode, enabled = M.enabled, recording = rec and (#rec.s / 4) or nil,
           recSeconds = rec and math.floor(rec.t) or nil, recBytes = rec and rec.bytes or nil, splits = stats.splits,
           logs = logs and #logs or nil, matched = match ~= nil, switching = sw ~= nil,
           switches = stats.switches, note = stats.note, grading = stats.grading, terrain = mode == 'playback' and stats.terrain or nil,
           recTerrain = rec and rec.terrain and rec.terrain.seal or nil }
end

function M._env() return env end      -- (tests)

function M._reset()
  mode, rec, logs, match, sw, checkAt = 'idle', nil, nil, nil, nil, 0
  lostUntil, hookSeen, pollAt = 0, false, 0
  split, sizeAt = nil, 0
  terr, restoreAt = nil, nil
  patch(false)
  stats = { switches = 0, lost = 0 }
end

return M
