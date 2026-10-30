-- luajit test_replay.lua (from mod/tests): replays in BeamNG.Earth's world (replaysync.lua) with a fake BeamNG.Earth.
package.path = '../offroad_companion/lua/ge/extensions/?.lua;' .. package.path
local pass, fail = 0, 0
local function check(cond, name) if cond then pass = pass + 1 else fail = fail + 1; print('FAIL: ' .. name) end end

local rs = require('offroadCompanion/replaysync')

-- the fake: BeamNG.Earth's state (anchor, player, block, pending), its modules, files, the game's pause
local clock = 0
local files = {}
local pausedFlag = false
local sent = {}
local st = { anchor = { lat = 31.0, lon = -115.0 }, player = { x = 0, y = 0, z = 10 }, block = { cx = 0, cy = 0 },
             clock = 0 }
local decideCalls = 0
local mods = {
  ['beamngEarth/rebase'] = { decide = function() decideCalls = decideCalls + 1; return 'prefetch' end },
  ['beamngEarth/drophold'] = { observe = function() return 'start' end },
  ['beamngEarth/edgeguard'] = { update = function() return 'hold' end },
  ['beamngEarth/net'] = { send = function(m) sent[#sent + 1] = m end, isConnected = function() return true end },
  ['beamngEarth/follow'] = { target = function(x, y) return math.floor(x / 128 + 0.5) * 128, math.floor(y / 128 + 0.5) * 128 end },
  ['beamngEarth/lattice'] = { groundBox = function(cx, cy) return cx - 512, cy - 512, cx + 510, cy + 510 end },
}
local logs = {}
rs.setEnv({
  state = function() return st end,
  mod = function(n) return mods[n] end,
  read = function(p) return files[p] end,
  write = function(p, t) files[p] = t end,
  remove = function(p) files[p] = nil end,
  clock = function() return clock end,
  time = function() return 1000 end,
  setPause = function(on) pausedFlag = on end,
  isPaused = function() return pausedFlag end,
  log = function(l, t) logs[#logs + 1] = t end,
})
local origDecide = mods['beamngEarth/rebase'].decide

local function frame(dt)
  clock = clock + dt
  st.clock = clock
  rs.update(dt, dt)
end

-- the server answers our prepare_anchor: BeamNG.Earth commits a teleport (anchor, block at cx/cy, placeFrames)
local function serverAnswers()
  local m = sent[#sent]
  if st.pending and m and st.pending.requestId == m.requestId then
    st.pending = nil
    st.anchor = { lat = m.lat, lon = m.lon }
    st.block = { cx = m.cx, cy = m.cy }
    st.placeFrames = 2
  end
end

check(rs.parseState({ state = 'recording' }) == 'recording' and rs.parseState('playback') == 'playback'
      and rs.parseState({ state = 'inactive' }) == 'idle' and rs.parseState(nil) == 'idle', 'replay states read')

-- 1. recording: drive east 12 km at 50 m/s; BeamNG.Earth rebases at x = 9000 (the car and the world shift back 9 km)
rs.onHook({ state = 'recording' })
local A1 = { lat = 31.0, lon = -115.0 }
local A2 = { lat = 31.0, lon = -114.906 }
local x, travelled = 0, 0
for k = 1, 240 * 10 do             -- 240 s at 10 frames a second
  x = x + 5
  travelled = travelled + 5
  if st.anchor == A1 or st.anchor.lat == A1.lat and st.anchor.lon == A1.lon then
    if x >= 9000 then
      st.rebasing = true           -- (one frame between the car's move and the world's)
      x = x - 9000
      st.player.x = x
      frame(0.1)
      st.rebasing = nil
      st.anchor = { lat = A2.lat, lon = A2.lon }
    end
  end
  st.player.x, st.player.y, st.player.z = x, travelled * 0.001, 10 + (k % 50) * 0.1
  frame(0.1)
end
rs.onHook({ state = 'inactive', loadedFile = 'replays/run1.rpl' })
local idx = files[rs.DIR .. 'index.json']
check(idx and #idx.list == 1, 'the recording logged')
local log1 = idx and files[rs.DIR .. idx.list[1].name .. '.json']
check(log1 and #log1.anchors == 2 and log1.file == 'replays/run1.rpl', 'its two frames of the world, and its file')
check(log1 and #log1.s / 4 > 900, 'a place every quarter second: ' .. (log1 and #log1.s / 4 or 0))

-- 2. later the world is elsewhere (the car drove on); a playback starts at its beginning
st.anchor = { lat = 31.2, lon = -114.5 }
st.player = { x = 1500, y = 0, z = 10 }
rs.onHook({ state = 'playback', loadedFile = 'replays/run1.rpl' })
check(mods['beamngEarth/rebase'].decide() == nil and mods['beamngEarth/drophold'].observe() == nil and
      mods['beamngEarth/edgeguard'].update() == nil, 'BeamNG.Earth leaves the replayed car alone')
-- the replayed car at 2 km into the recording (frame A1, x 2000)
st.player = { x = 2000, y = 2.0, z = 10 + (400 % 50) * 0.1 }
frame(0.25)
local m = sent[#sent]
check(m and m.type == 'prepare_anchor' and m.lat == A1.lat and m.lon == A1.lon, 'the world asked to the recording\'s frame')
check(m and m.cx == 2048 and m.cy == 0, 'its ground centred at the car: ' .. tostring(m and m.cx))
check(pausedFlag, 'paused while it loads')
check(st.pending and st.pending.purpose == 'teleport', 'as BeamNG.Earth\'s own teleport request')
serverAnswers()
frame(0.02)
check(st.placeFrames == nil, 'BeamNG.Earth does not set the car down at the anchor')
check(not pausedFlag, 'ground under the car: playing on')
local nSent = #sent
for k = 1, 20 do st.player.x = 2000 + k * 5; frame(0.25) end
check(#sent == nSent, 'same frame: nothing more asked')

-- 3. the recording's rebase comes up: the replayed car jumps to x - 9000 (frame A2)
st.player.x, st.player.y = 8990, 8.99
frame(0.25)
st.player.x, st.player.y = 5, 9.005   -- after the jump
st.player.z = 10 + (1800 % 50) * 0.1
frame(0.25)
m = sent[#sent]
check(#sent == nSent + 1 and m.lat == A2.lat and m.lon == A2.lon, 'the playback rebases where the recording did')
serverAnswers()
frame(0.25)
check(not pausedFlag, 'and plays on')

-- 4. seeking back to the start: found again (all over the logs), the world back to A1
st.player = { x = 100, y = 0.1, z = 10 + (20 % 50) * 0.1 }
frame(0.25)
frame(1.1)
m = sent[#sent]
check(m.lat == A1.lat and m.lon == A1.lon, 'a seek back: the first frame again')
serverAnswers()
frame(0.25)

-- 5. a place in no log (a replay recorded before): nothing asked, said so
nSent = #sent
st.player = { x = 50000, y = 40000, z = 900 }
frame(1.2)
frame(1.2)
check(#sent == nSent and rs.status().note ~= nil, 'no log: left as it is, and said: ' .. tostring(rs.status().note))

-- 6. a switch the server cannot answer: not paused for ever
st.player = { x = 2000, y = 2.0, z = 10 + (400 % 50) * 0.1 }
st.anchor = { lat = 0, lon = 0 }
frame(1.2)
check(pausedFlag, 'waiting for the ground')
for k = 1, 30 do frame(1.0) end
check(not pausedFlag, 'let go after ' .. rs.WAIT_MAX_S .. ' s')

-- 7. the end of the playback: BeamNG.Earth's own behaviour back
rs.onHook({ state = 'inactive' })
check(mods['beamngEarth/rebase'].decide == origDecide and mods['beamngEarth/drophold'].observe() == 'start',
      'BeamNG.Earth\'s rebase, drop hold and edge guard back')
check(not pausedFlag, 'not left paused')

-- 8. the player's own pause is theirs
rs.onHook({ state = 'playback' })
pausedFlag = true
st.anchor = { lat = 1, lon = 1 }
st.player = { x = 2000, y = 2.0, z = 10 + (400 % 50) * 0.1 }
frame(1.2)
serverAnswers()
frame(0.1)
check(pausedFlag, 'paused by the player before: still paused')
rs.onHook({ state = 'inactive' })

-- 9. turned off: a playback is left alone
rs.setEnabled(false)
rs.onHook({ state = 'playback' })
nSent = #sent
st.anchor = { lat = 5, lon = 5 }
frame(1.2)
check(#sent == nSent and mods['beamngEarth/rebase'].decide == origDecide, 'off: nothing done')
rs.onHook({ state = 'inactive' })
rs.setEnabled(true)

-- 10. the game's state asked when it sends no hook
rs._reset()
local polled = 'recording'
rs.setEnv({
  state = function() return st end, mod = function(n) return mods[n] end, read = function(p) return files[p] end,
  write = function(p, t) files[p] = t end, clock = function() return clock end, time = function() return 2000 end,
  pollState = function() return polled end,
})
frame(1.1)
check(rs.status().mode == 'recording', 'polled: recording')

-- 11. a long recording split before 2 GB: stopped (saved) and started again; the game's own size when it says it
rs._reset()
local recording, toggles, msgs, sizes, nfile = false, 0, {}, {}, 1
local function gameState() return recording and 'recording' or 'inactive' end
rs.setEnv({
  state = function() return st end, mod = function(n) return mods[n] end, read = function(p) return files[p] end,
  write = function(p, t) files[p] = t end, clock = function() return clock end, time = function() return 3000 end,
  canToggle = function() return true end,
  toggleRecording = function()
    toggles = toggles + 1; recording = not recording
    local f = 'replays/long' .. nfile .. '.rpl'
    if recording then nfile = nfile + 1; f = 'replays/long' .. nfile .. '.rpl'; sizes[f] = 1000 end
    rs.onHook({ state = gameState(), loadedFile = f })
  end,
  fileSize = function(p) return sizes[p] end,
  message = function(t) msgs[#msgs + 1] = t end,
})
st.anchor = { lat = 31.0, lon = -115.0 }; st.player = { x = 0, y = 0, z = 10 }; st.rebasing = nil; st.placeFrames = nil
recording = true
rs.onHook({ state = 'recording', loadedFile = 'replays/long1.rpl' })
sizes['replays/long1.rpl'] = 1.0e9
for k = 1, 400 do st.player.x = k; frame(0.1) end
check(toggles == 0, 'under the limit: not split')
sizes['replays/long1.rpl'] = 1.9e9
for k = 1, 60 do st.player.x = 400 + k; frame(0.1) end
check(toggles == 2 and recording, 'near 2 GB: stopped and started again (' .. toggles .. ' toggles)')
check(#msgs == 1, 'and said so')
check(rs.status().mode == 'recording', 'a new recording logged')
-- without the game's size: estimated from the time recorded (the rate learnt from the last one)
local idx2 = files[rs.DIR .. 'index.json']
check(idx2 and idx2.rate and idx2.rate > 1e7, 'the rate learnt from the split recording: ' .. tostring(idx2 and idx2.rate))
-- a game that does not say it stopped: never toggled blind a second time
rs._reset()
toggles = 0
rs.setEnv({
  state = function() return st end, mod = function(n) return mods[n] end, read = function(p) return files[p] end,
  write = function(p, t) files[p] = t end, clock = function() return clock end, time = function() return 4000 end,
  canToggle = function() return true end, toggleRecording = function() toggles = toggles + 1 end,
  fileSize = function() return 1.95e9 end, message = function(t) msgs[#msgs + 1] = t end,
})
rs.onHook({ state = 'recording', loadedFile = 'replays/x.rpl' })
for k = 1, 200 do frame(0.1) end
check(toggles == 1 and rs.status().mode == 'recording', 'no word from the game: one toggle only, the player told')

-- a playback after a restart: BeamNG.Earth's own setting down of the car called off; no car, the camera matched
rs._reset()
local logged = {}
sent = {}
rs.setEnv({
  state = function() return st end, mod = function(n) return mods[n] end, read = function(p) return files[p] end,
  write = function(p, t) files[p] = t end, clock = function() return clock end, time = function() return 5000 end,
  setPause = function(on) pausedFlag = on end, isPaused = function() return pausedFlag end,
  log = function(l, t) logged[#logged + 1] = t end, diag = function() return 'vehicles 0' end,
})
pausedFlag = false
files[rs.DIR .. 'index.json'] = { list = { { name = 'L1' } } }
files[rs.DIR .. 'L1.json'] = { anchors = { { 10, 20 } }, s = { 1, 0, 0, 5, 1, 100, 0, 5, 1, 200, 0, 5 } }
st.anchor = { lat = 1, lon = 2 }
st.pending = nil
st.player = nil
st.cam = { x = 110, y = 12, z = 9 }       -- (the orbit camera, behind and over where the car is)
st.placeFrames, st.floorZ = 2, 3.0
rs.onHook({ state = 'playback' })
frame(0.25)
check(st.placeFrames == nil and st.floorZ == nil, 'BeamNG.Earth does not set a car down during the playback')
local m2 = sent[#sent]
check(m2 and m2.lat == 10 and m2.lon == 20, 'no car: the world moved by where the camera is')
local said = false
for _, t in ipairs(logged) do if t:find('vehicles 0', 1, true) then said = true end end
check(said, 'what the game has logged in the first seconds')
rs.onHook({ state = 'inactive' })
pausedFlag = false

-- 13. the ground: recorded with the recording (and kept by the companion), the recorded one back for its playback
rs._reset()
sent = {}
local ground = { trackId = 'f:baja', scale = 1.0, paint = true, clear = true, ruts = 'auto', rough = 'on', seal = 'T1-aaaaaa',
                 tv = 1 }
local applied, snapshots, restored, ready = nil, {}, 0, false
local function terrainEnv(extra)
  local e = {
    state = function() return st end, mod = function(n) return mods[n] end, read = function(p) return files[p] end,
    write = function(p, t) files[p] = t end, remove = function(p) files[p] = nil end, clock = function() return clock end,
    time = function() return 5000 end, setPause = function(on) pausedFlag = on end,
    isPaused = function() return pausedFlag end,
    terrain = function() return applied and nil or ground end,
    seal = function() return applied and applied.seal or ground.seal end,
    snapshot = function(name) snapshots[#snapshots + 1] = name; return true end,
    applyTerrain = function(t, pin) applied = { seal = t.seal, pin = pin, rough = t.rough }; ready = false; return true end,
    terrainReady = function() return ready end,
    restoreTerrain = function() if not applied then return false end; applied = nil; restored = restored + 1; return true end,
  }
  for k, v in pairs(extra or {}) do e[k] = v end
  return e
end
rs.setEnv(terrainEnv())
files = {}
pausedFlag = false
st = { anchor = { lat = 31.0, lon = -115.0 }, player = { x = 0, y = 0, z = 10 }, block = { cx = 0, cy = 0 }, clock = clock }
rs.onHook({ state = 'recording' })
for k = 1, 200 do st.player.x = k * 5; frame(0.1) end
rs.onHook({ state = 'inactive', loadedFile = 'replays/g.rpl' })
idx = files[rs.DIR .. 'index.json']
local gl = files[rs.DIR .. idx.list[1].name .. '.json']
check(gl.terrain and gl.terrain.seal == 'T1-aaaaaa' and gl.terrain.rough == 'on', 'the recording notes its ground')
check(#snapshots == 1 and snapshots[1] == idx.list[1].name and gl.terrain.kept, 'and the companion keeps it')

-- a. played back on the same ground: nothing to do
rs.onHook({ state = 'playback', loadedFile = 'replays/g.rpl' })
st.player = { x = 500, y = 0, z = 10 }
frame(0.25)
check(applied == nil and not pausedFlag, 'same ground: played as it is')
check(rs.status().terrain:find('recorded on', 1, true) ~= nil, 'and said: ' .. tostring(rs.status().terrain))
rs.onHook({ state = 'inactive' })

-- b. the player changed to Auto since: the recorded ground is asked for, the playback waits, then the world is rebuilt
ground = { trackId = 'f:baja', scale = 1.0, paint = true, clear = true, ruts = 'auto', rough = 'auto', seal = 'T1-bbbbbb',
           tv = 1 }
sent = {}
rs.onHook({ state = 'playback', loadedFile = 'replays/g.rpl' })
st.player = { x = 500, y = 0, z = 10 }
frame(0.25)
check(applied and applied.seal == 'T1-aaaaaa' and applied.pin == idx.list[1].name and applied.rough == 'on',
      'the recorded ground asked for, pinned to its snapshot')
check(pausedFlag and #sent == 0, 'paused while it is planned, the world not moved yet')
for k = 1, 4 do frame(0.25) end
check(#sent == 0, 'still waiting')
ready = true
frame(0.25)
local mm = sent[#sent]
check(mm and mm.type == 'prepare_anchor' and mm.lat == 31.0 and mm.lon == -115.0,
      'then the world built again around the car, in the same frame')
serverAnswers()
frame(0.25)
check(not pausedFlag, 'and the playback goes on on the recorded ground')
check(rs.status().terrain:find('recorded on', 1, true) ~= nil, 'said: ' .. tostring(rs.status().terrain))
local nS = #sent
for k = 1, 10 do st.player.x = 500 + k * 5; frame(0.25) end
check(#sent == nS and applied ~= nil, 'once: not asked again')

-- c. the end: the player's own ground back, built again around the car a little later (a resync: nothing moves)
rs.onHook({ state = 'inactive' })
check(restored == 1 and applied == nil, 'the player\'s own settings back')
st.pending = nil
st.player = { x = 30, y = 40, z = 10 }
for k = 1, 30 do frame(0.25) end
mm = sent[#sent]
check(#sent == nS + 1 and mm.type == 'prepare_anchor' and st.pending and st.pending.purpose == 'resync'
      and mm.lat == 31.0, 'the ground built again with them: ' .. tostring(st.pending and st.pending.purpose))

-- d. the companion never answers: not paused for ever, played on today's ground
st.pending = nil
rs.onHook({ state = 'playback', loadedFile = 'replays/g.rpl' })
ready = false
st.player = { x = 500, y = 0, z = 10 }
frame(0.25)
for k = 1, 100 do frame(0.25) end
check(not pausedFlag or #sent > 0, 'let go after ' .. rs.TERRAIN_WAIT_S .. ' s')
serverAnswers()
frame(0.25)
check(not pausedFlag, 'and plays on')
rs.onHook({ state = 'inactive' })

-- e. a recording made before replays kept their ground
files[rs.DIR .. idx.list[1].name .. '.json'].terrain = nil
applied = nil
rs.onHook({ state = 'playback', loadedFile = 'replays/g.rpl' })
st.player = { x = 500, y = 0, z = 10 }
frame(0.25)
check(applied == nil and rs.status().terrain:find('before', 1, true) ~= nil, 'an old recording: said so')
rs.onHook({ state = 'inactive' })

-- 14. BeamNG.Earth 1.6: a jump gets a provisional block first (no road levelling, no track relief), the graded one
-- later (terrain_refresh); the playback waits for that one. BeamNG.Earth's core reads its messages through net.update
-- (seen here as it reads them) and commits a teleport as its anchor_ready arrives (no "ready" pending in between).
local netq = {}
mods['beamngEarth/net'].update = function() local out = netq; netq = {}; return out end
local function coreReads() return mods['beamngEarth/net'].update(0.02) end      -- (BeamNG.Earth's core, each frame)
local function jump(refreshFirst)
  rs._reset()
  rs.setEnv(terrainEnv({ seal = function() return 'T1-aaaaaa' end }))
  ground.seal = 'T1-aaaaaa'
  applied = nil
  sent = {}
  pausedFlag = false
  files[rs.DIR .. idx.list[1].name .. '.json'].terrain = { seal = 'T1-aaaaaa' }
  st = { anchor = { lat = 40.0, lon = -100.0 }, player = { x = 500, y = 0, z = 10 }, block = { cx = 0, cy = 0 },
         clock = clock, followCount = 7 }
  rs.onHook({ state = 'playback', loadedFile = 'replays/g.rpl' })
  frame(0.25)
  local pm = sent[#sent]
  check(pm and pm.type == 'prepare_anchor' and pausedFlag, 'a jump to the recording\'s frame, paused')
  netq = { { type = 'anchor_ready', requestId = pm.requestId, anchorId = 42, provisional = true } }
  if refreshFirst then netq[2] = { type = 'terrain_refresh', anchorId = 42, cx = pm.cx, cy = pm.cy } end
  coreReads()
  st.pending, st.anchor, st.block = nil, { lat = pm.lat, lon = pm.lon }, { cx = pm.cx, cy = pm.cy }    -- (committed)
  if refreshFirst then st.followCount = 8 end      -- (1.6.2: the kept graded block put in right after the commit)
  return pm
end
local pm = jump(false)
for k = 1, 8 do coreReads(); frame(0.25) end
check(pausedFlag and rs.status().grading, 'the provisional ground under the car: still waiting for the graded one')
netq = { { type = 'terrain_refresh', anchorId = 42, cx = pm.cx, cy = pm.cy } }
coreReads()
st.followCount = 8
frame(0.25)
check(not pausedFlag and not rs.status().grading, 'the graded ground in: playing on')
rs.onHook({ state = 'inactive' })
check(mods['beamngEarth/net'].update ~= nil and coreReads() ~= nil, 'BeamNG.Earth\'s net.update back as it was')
jump(true)
frame(0.25)
check(not pausedFlag, 'the graded block before the commit (1.6.2): playing on, not waiting for another')
rs.onHook({ state = 'inactive' })
-- an ordinary switch (no provisional block): no wait for a graded one
pm = jump(false)
rs._reset()
rs.setEnv(terrainEnv({ seal = function() return 'T1-aaaaaa' end }))
sent, pausedFlag = {}, false
st = { anchor = { lat = 40.0, lon = -100.0 }, player = { x = 500, y = 0, z = 10 }, block = { cx = 0, cy = 0 },
       clock = clock, followCount = 7 }
rs.onHook({ state = 'playback', loadedFile = 'replays/g.rpl' })
frame(0.25)
pm = sent[#sent]
netq = { { type = 'anchor_ready', requestId = pm.requestId, anchorId = 43, provisional = false } }
coreReads()
st.pending, st.anchor, st.block = nil, { lat = pm.lat, lon = pm.lon }, { cx = pm.cx, cy = pm.cy }
frame(0.25)
check(not pausedFlag, 'not provisional: playing on at once')
rs.onHook({ state = 'inactive' })
mods['beamngEarth/net'].update = nil

-- 15. no car (BeamNG.Earth 1.6 makes the camera its player: camera = true): matched with the camera's leeway, and a
-- recording without a car logs nothing
rs._reset()
rs.setEnv(terrainEnv())
sent = {}
st = { anchor = { lat = 40.0, lon = -100.0 }, player = { x = 515, y = 12, z = 10, camera = true }, block = { cx = 0, cy = 0 },
       clock = clock, cam = { x = 515, y = 12, z = 10 } }
rs.onHook({ state = 'playback', loadedFile = 'replays/g.rpl' })
frame(0.25)
check(sent[#sent] and sent[#sent].type == 'prepare_anchor', 'the camera 15 m off the recorded car: matched')
rs.onHook({ state = 'inactive' })
local before = 0
for _ in pairs(files) do before = before + 1 end
rs.onHook({ state = 'recording' })
for k = 1, 50 do st.player.x = 500 + k; frame(0.1) end
rs.onHook({ state = 'inactive', loadedFile = 'replays/nocar.rpl' })
local after = 0
for _ in pairs(files) do after = after + 1 end
check(after == before, 'no car recorded: no log')

-- 16. a BeamMP session (BeamNG.Earth 1.6): every player has their own world origin (mpanchor.lua converts the others'
-- cars), so a playback moves ours to the recording as it does alone (the user, 2026-10-25: "replays are broken, tested
-- it on an empty multiplayer server": the car was out in the void); BeamNG.Earth's moving onto the other players'
-- origin (mpsession's converge, with its shared generation on) waits until the replay ends
rs._reset()
local inMP = true
mods['beamngEarth/beammp'] = { inSession = function() return inMP end }
mods['beamngEarth/mpsession'] = { SHARE_GEN = true }
rs.setEnv(terrainEnv())
sent = {}
st = { anchor = { lat = 40.0, lon = -100.0 }, player = { x = 500, y = 0, z = 10 }, block = { cx = 0, cy = 0 }, clock = clock }
rs.onHook({ state = 'playback', loadedFile = 'replays/g.rpl' })
frame(0.25)
frame(1.2)
check(sent[#sent] and sent[#sent].type == 'prepare_anchor', 'BeamMP: the world moved to the recording\'s place')
check(mods['beamngEarth/rebase'].decide ~= origDecide, 'BeamMP: BeamNG.Earth\'s own rebases held, as alone')
check(mods['beamngEarth/mpsession'].SHARE_GEN == false, 'BeamMP: no moving onto the others\' origin meanwhile')
check(not (rs.status().note or ''):find('BeamMP', 1, true), 'no "shared world" note: ' .. tostring(rs.status().note))
rs.onHook({ state = 'inactive' })
check(mods['beamngEarth/rebase'].decide == origDecide and mods['beamngEarth/mpsession'].SHARE_GEN == true,
  'the replay over: BeamNG.Earth\'s rebases and its shared generation as they were')
-- shared generation off (as BeamNG.Earth 1.6.2 ships it): left off, not switched on afterwards
mods['beamngEarth/mpsession'].SHARE_GEN = false
rs._reset()
rs.setEnv(terrainEnv())
rs.onHook({ state = 'playback', loadedFile = 'replays/g.rpl' })
frame(0.25)
rs.onHook({ state = 'inactive' })
check(mods['beamngEarth/mpsession'].SHARE_GEN == false, 'off stays off')
mods['beamngEarth/beammp'], mods['beamngEarth/mpsession'] = nil, nil

-- 17. recorded on another BeamNG.Earth: the recorded track's ground asked for, and said that Earth's own differs
rs._reset()
rs.setEnv(terrainEnv({ earth = function() return '1.6.0-beta' end }))
ground.seal = 'T1-ffffff'
applied, ready = nil, false
sent = {}
pausedFlag = false
files[rs.DIR .. idx.list[1].name .. '.json'].terrain = { seal = 'T1-aaaaaa', earth = '1.5.5-beta', rough = 'on' }
st = { anchor = { lat = 31.0, lon = -115.0 }, player = { x = 500, y = 0, z = 10 }, block = { cx = 0, cy = 0 }, clock = clock }
rs.onHook({ state = 'playback', loadedFile = 'replays/g.rpl' })
frame(0.25)
check(applied and applied.seal == 'T1-aaaaaa', 'another Earth: the recorded track\'s ground asked for')
ready = true
frame(0.25)
check(rs.status().terrain and rs.status().terrain:find('1.5.5-beta', 1, true), 'and said: ' .. tostring(rs.status().terrain))
rs.onHook({ state = 'inactive' })

-- the pure match
local L = { s = { 1, 0, 0, 0, 1, 10, 0, 0, 2, 0, 0, 0, 2, 10, 0, 0 }, anchors = { { 1, 1 }, { 2, 2 } } }
local l, i = rs.find({ L }, nil, 5, 1, 0)
check(l == L and i == 1, 'between two places of one frame')
l, i = rs.find({ L }, nil, 5, 20, 0)
check(l == nil, 'too far from any')

print(string.format('%d passed, %d failed', pass, fail))
os.exit(fail == 0 and 0 or 1)
