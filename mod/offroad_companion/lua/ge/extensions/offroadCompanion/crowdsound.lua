-- The crowds' sound: cheering and clapping from where each crowd stands, looping while the car is near (the user,
-- 2026-10-25: "could you add this sound where spectators appear? also for immersion", then "the spectator sound should
-- loop"; a seamless loop of a crowd cheering and clapping, started at three points of it: tools/make_crowd_sounds.py).
--
-- A crowd within HEAR_M of the car (crowds.lua's: the middle of its people) plays its loop, placed in the world: louder
-- near it, to one side as you pass. It fades in over the last FADE_M coming in and out the same going away, and stops
-- past OFF_M. Only the nearest few play (MAX_LOOPS; a gate's counts two); a bigger crowd is louder; the start, the
-- finish and the checkpoints play two of the loops at once. Which loop a crowd uses is a hash of its place (the same
-- crowd sounds the same). Settings: Crowd sound On / Off.
-- If the game will not place a sound in the world, it plays an ordinary one, started again as each pass ends, quieter
-- the farther the crowd is.
local markers = require('offroadCompanion/markers')

local M = {}

M.enabled = true
M.DIR = '/art/offroadcompanion/sound/'
M.FILES = { 'crowd_1.ogg', 'crowd_2.ogg', 'crowd_3.ogg' }
M.LOOP_S = 21.888           -- each loop's length (tools/make_crowd_sounds.py prints it)
M.HEAR_M = 250              -- a crowd's sound on within this of the car ...
M.OFF_M = 300               -- ... and off past this
M.FADE_M = 90               -- full volume from HEAR_M - FADE_M in (no sudden start)
M.FADE_S = 0.8              -- volume changes eased over about this long
M.MAX_LOOPS = 4             -- at most this many loops at once (the nearest crowds)
M.VOLUME = 1.0
M.HEIGHT_M = 1.6            -- the sound from this high over the ground (their heads)
M.TEST_S = 8.0
M.PROFILE_3D = 'AudioDefaultLoop3D'
M.PROFILE_2D = 'AudioGui'

local active = {}           -- loop key -> { id, file, x, y, z, base (its full volume), vol, target, dying, ends (2D),
                            --              expires (the test's), crowd }
M.method = nil              -- '3D' | '2D' once something played
M.lastError = nil
M.count = 0

local function audio() local E = rawget(_G, 'Engine'); return E and E.Audio end

-- Pure: how loud a crowd of n people is, 0..1.
function M.volumeFor(n, gate)
  local v = 0.45 + (n or 0) / 30
  if gate then v = v + 0.1 end
  return math.max(0.5, math.min(1.0, v)) * M.VOLUME
end

-- Pure: which loop(s) a crowd plays (a gate's: two), from hash (0..1) of its place.
function M.clipsFor(c, hash)
  local k = 1 + math.floor(hash * #M.FILES) % #M.FILES
  local out = { M.FILES[k] }
  if c.gate then out[2] = M.FILES[1 + k % #M.FILES] end
  return out
end

-- Pure: how much of its full volume a crowd d m away plays at (0 at HEAR_M, 1 from HEAR_M - FADE_M in).
function M.ramp(d)
  return math.max(0, math.min(1, (M.HEAR_M - d) / M.FADE_M))
end

-- Pure: an ordinary (not placed) sound's volume, the car d m from the crowd.
function M.volume2d(vol, d)
  return vol * math.max(0, math.min(1, 1 - (d - 30) / (M.HEAR_M - 30)))
end

-- Pure: the crowds that should be playing: { {c, d} } nearest first, within HEAR_M (OFF_M for one playing already:
-- playing[key]), at most MAX_LOOPS loops (a gate's two).
function M.wanted(crowds, car, playing)
  local near = {}
  for _, c in ipairs(crowds or {}) do
    local d = math.sqrt((c.x - car.x) ^ 2 + (c.y - car.y) ^ 2)
    if d < M.HEAR_M or (playing and playing[c.key] and d < M.OFF_M) then near[#near + 1] = { c = c, d = d } end
  end
  table.sort(near, function(p, q) return p.d < q.d end)
  local out, slots = {}, 0
  for _, v in ipairs(near) do
    local n = v.c.gate and 2 or 1
    if slots + n > M.MAX_LOOPS then break end
    slots = slots + n
    out[#out + 1] = v
  end
  return out
end

-- One loop from (x, y, z): placed in the world when the game makes one (returns its id), else nil (an ordinary
-- sound is played once at vol2d: started again by update when it ends).
local function start(file, x, y, z, vol, vol2d)
  local A = audio()
  if not A then error('no Engine.Audio') end
  local path = M.DIR .. file
  if M.method ~= '2D' and A.createSource then
    local ok, id = pcall(function()
      local sid = A.createSource(M.PROFILE_3D, path)
      if type(sid) ~= 'number' or sid < 0 then error('createSource gave ' .. tostring(sid)) end
      local src = scenetree.findObjectById(sid)
      if not src then error('no sound object ' .. tostring(sid)) end
      local placed = false
      if rawget(_G, 'MatrixF') and src.setTransform then
        placed = pcall(function()
          local m = MatrixF(true)
          m:setPosition(vec3(x, y, z))
          src:setTransform(m)
        end)
      end
      if not placed and src.setPosition then placed = pcall(function() src:setPosition(vec3(x, y, z)) end) end
      if not placed then pcall(A.deleteSource, sid); error('could not place the sound') end
      if src.setVolume then pcall(function() src:setVolume(vol) end) end
      src:play(-1)
      return sid
    end)
    if ok then M.method = '3D'; return id end
    M.lastError = tostring(id)
    if M.method == '3D' then error(M.lastError) end    -- (it worked before: a passing failure, not the game)
  end
  local ok, err = pcall(A.playOnce, M.PROFILE_2D, path, { volume = vol2d })
  if not ok then ok, err = pcall(A.playOnce, M.PROFILE_2D, path) end
  if not ok then error(tostring(err)) end
  M.method = '2D'
  return nil
end

local function stop(key)
  local e = active[key]
  active[key] = nil
  if not e or not e.id then return end
  local A = audio()
  local src = scenetree and scenetree.findObjectById(e.id)
  if src and src.stop then pcall(function() src:stop(-1) end) end
  if A and A.deleteSource then pcall(A.deleteSource, e.id) end
end

function M.stopAll()
  for key in pairs(active) do stop(key) end
  active = {}
end

function M.setEnabled(v)
  M.enabled = v and true or false
  if not M.enabled then M.stopAll() end
  return M.enabled
end

local function begin(key, file, x, y, z, base, d, crowd, expires)
  local ok, id = pcall(start, file, x, y, z, 0, M.volume2d(base, d))
  if not ok then M.lastError = tostring(id); return end
  M.count = M.count + 1
  active[key] = { id = id, file = file, x = x, y = y, z = z, base = base, vol = 0, target = 0, crowd = crowd,
                  ends = not id and (os.clock() + M.LOOP_S) or nil, expires = expires }
end

-- Every second or so: the nearest crowds' loops on, the far ones' faded out (crowds: crowds.cheers()).
function M.update(crowds, car, hash, course)
  local now = os.clock()
  if course ~= M.course then M.course = course; M.stopAll() end      -- (another course: its own crowds)
  if not M.enabled or not car then M.stopAll(); return end
  local playing = {}
  for _, e in pairs(active) do if e.crowd and not e.dying then playing[e.crowd] = true end end
  local want = {}
  for _, v in ipairs(M.wanted(crowds, car, playing)) do want[v.c.key] = v end
  -- the ones not wanted any more fade out (tick stops them once silent); the test's after its time
  for key, e in pairs(active) do
    if (e.crowd and not want[e.crowd]) or (e.expires and now >= e.expires) then e.dying, e.target = true, 0 end
  end
  -- the wanted ones: started (silent, tick fades them in), their full volume
  for ck, v in pairs(want) do
    local c = v.c
    local base = M.volumeFor(c.n, c.gate)
    local h = hash and hash(math.floor(c.x), math.floor(c.y), 41) or 0
    for i, f in ipairs(M.clipsFor(c, h)) do
      local key = ck .. '#' .. i
      local e = active[key]
      if e and e.dying and e.id then e.dying = nil end           -- (coming back before it went quiet)
      if not e then
        local gz = markers.groundZ(c.x, c.y, car.z or 0) or car.z or 0
        begin(key, f, c.x, c.y, gz + M.HEIGHT_M, base, v.d, ck)
      end
    end
  end
  -- keep them going: a loop the game stopped started again; an ordinary sound played again as its pass ends
  local A = audio()
  for key, e in pairs(active) do
    if e.id then
      local src = scenetree and scenetree.findObjectById(e.id)
      if not src then
        active[key] = nil
      elseif src.isPlaying and not e.dying then
        local ok, on = pcall(function() return src:isPlaying() end)
        if ok and on == false then pcall(function() src:play(-1) end) end
      end
    elseif e.ends and now >= e.ends - 0.3 then
      if e.dying then
        active[key] = nil
      elseif A then
        local d = math.sqrt((e.x - car.x) ^ 2 + (e.y - car.y) ^ 2)
        local v = e.expires and e.base or M.volume2d(e.base, d)
        if v > 0.02 then
          local ok = pcall(A.playOnce, M.PROFILE_2D, M.DIR .. e.file, { volume = v })
          if not ok then pcall(A.playOnce, M.PROFILE_2D, M.DIR .. e.file) end
        end
        e.ends = now + M.LOOP_S
      end
    end
  end
end

-- Every frame: each loop's volume eased toward its crowd's distance (and silent ones stopped).
function M.tick(dt, car)
  if not next(active) or not car then return end
  local step = (dt or 0) / M.FADE_S
  for key, e in pairs(active) do
    if e.id then
      local d = math.sqrt((e.x - car.x) ^ 2 + (e.y - car.y) ^ 2)
      local target = 0
      if not e.dying then target = e.expires and e.base or e.base * M.ramp(d) end
      local v = e.vol
      if v < target then v = math.min(target, v + step) elseif v > target then v = math.max(target, v - step) end
      if e.dying and v <= 0.005 then
        stop(key)
      elseif math.abs(v - e.vol) > 0.004 then
        e.vol = v
        local src = scenetree and scenetree.findObjectById(e.id)
        if src and src.setVolume then pcall(function() src:setVolume(v) end) end
      end
    end
  end
end

-- (Settings' "Test crowd sound") a crowd's loop 25 m ahead of the car for TEST_S.
function M.test(car, headingDeg)
  if not car then return false, 'no car' end
  local a = math.rad(headingDeg or 0)
  local x, y = car.x + 25 * math.sin(a), car.y + 25 * math.cos(a)
  local gz = markers.groundZ(x, y, car.z or 0) or car.z or 0
  stop('test')
  local before = M.count
  begin('test', M.FILES[1], x, y, gz + M.HEIGHT_M, M.VOLUME, 25, nil, os.clock() + M.TEST_S)
  if M.count == before then return false, M.lastError end
  return true
end

function M.status()
  local n = 0
  for _, e in pairs(active) do if not e.dying then n = n + 1 end end
  return { on = M.enabled, method = M.method, playing = n, played = M.count, error = M.lastError }
end

function M._active() return active end

return M
