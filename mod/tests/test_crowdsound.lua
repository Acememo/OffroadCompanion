-- luajit test_crowdsound.lua (from mod/tests): the crowds near the car heard, a loop from where each stands.
package.path = '../offroad_companion/lua/ge/extensions/?.lua;' .. package.path
local pass, fail = 0, 0
local function check(cond, name) if cond then pass = pass + 1 else fail = fail + 1; print('FAIL: ' .. name) end end

function vec3(x, y, z) return { x = x, y = y, z = z } end
function log() end
function MatrixF()
  local m = {}
  function m:setPosition(p) self.pos = p end
  return m
end
local sources, nextId, deletedSrc = {}, 100, 0
scenetree = { findObjectById = function(id) return sources[id] end, MissionGroup = { addObject = function() end } }
local twoD = {}
local placeWorks = true
Engine = { Audio = {
  createSource = function(profile, file)
    nextId = nextId + 1
    local s = { id = nextId, profile = profile, file = file }
    function s:setTransform(m) if not placeWorks then error('no setTransform') end self.pos = m.pos end
    function s:setVolume(v) self.vol = v end
    function s:play() self.playing = true end
    function s:stop() self.playing = false end
    sources[nextId] = s
    return nextId
  end,
  deleteSource = function(id) sources[id] = nil; deletedSrc = deletedSrc + 1 end,
  playOnce = function(profile, file, opts) twoD[#twoD + 1] = { profile = profile, file = file, opts = opts } end,
} }
castRayStatic = function(from) return from.z - 10 end      -- (the ground at z 10)

local cs = require('offroadCompanion/crowdsound')
local function hash(a, b) return ((a * 7 + b * 13) % 100) / 100 end

-- 1. pure: which crowds are heard
local crowds = { { key = 'start:0', x = 0, y = 0, n = 30, gate = true }, { key = 'jump:250', x = 0, y = 2500, n = 6 } }
check(#cs.wanted(crowds, { x = 0, y = -500 }) == 0, 'far away: silence')
local w = cs.wanted(crowds, { x = 0, y = -200 })
check(#w == 1 and w[1].c.key == 'start:0', 'within HEAR_M: the start heard')
check(#cs.wanted(crowds, { x = 0, y = -280 }) == 0, 'past HEAR_M: not started ...')
check(#cs.wanted(crowds, { x = 0, y = -280 }, { ['start:0'] = true }) == 1, '... but one playing keeps on to OFF_M')
check(#cs.wanted(crowds, { x = 0, y = -320 }, { ['start:0'] = true }) == 0, 'past OFF_M: off')
local many = {}
for i = 1, 8 do many[i] = { key = 'k' .. i, x = i * 10, y = 0, n = 5 } end
local w8 = cs.wanted(many, { x = 0, y = 0 })
check(#w8 == cs.MAX_LOOPS and w8[1].c.key == 'k1' and w8[#w8].c.key == 'k' .. cs.MAX_LOOPS, 'the nearest MAX_LOOPS')
many[1].gate = true
check(#cs.wanted(many, { x = 0, y = 0 }) == cs.MAX_LOOPS - 1, 'a gate\'s counts two')
check(cs.ramp(cs.HEAR_M) == 0 and cs.ramp(cs.HEAR_M - cs.FADE_M) == 1 and cs.ramp(10) == 1, 'fades in over FADE_M')
check(cs.volumeFor(4) < cs.volumeFor(25) and cs.volumeFor(200) <= 1 and cs.volumeFor(0) >= 0.5, 'bigger crowds louder')
check(#cs.clipsFor({ gate = true }, 0.4) == 2 and #cs.clipsFor({}, 0.4) == 1, 'a gate: two loops at once')
local c1, c2 = cs.clipsFor({ gate = true }, 0.4), cs.clipsFor({}, 0.99)
check(c1[1] ~= c1[2] and c2[1] == cs.FILES[3], 'different loops')
check(cs.volume2d(1, 20) == 1 and cs.volume2d(1, 200) < 0.3 and cs.volume2d(1, cs.HEAR_M) == 0, 'an ordinary sound: quieter far away')

-- 2. playing: loops placed in the world at the crowd, eased in, kept on, faded out and let go
local car = { x = 0, y = -200, z = 10 }
cs.update(crowds, car, hash, 'course1')
local n3d, at = 0, nil
for _, s in pairs(sources) do n3d = n3d + 1; at = s end
check(n3d == 2 and at.profile == 'AudioDefaultLoop3D' and at.playing, 'the start: two loops placed in the world: ' .. n3d)
check(at.pos and math.abs(at.pos.z - (10 + cs.HEIGHT_M)) < 1e-6 and at.pos.x == 0 and at.pos.y == 0, 'at the crowd')
check(at.file:find('^/art/offroadcompanion/sound/crowd_%d%.ogg$') ~= nil, 'one of the loops: ' .. at.file)
check(at.vol == 0, 'starts silent')
for _ = 1, 30 do cs.tick(0.1, car) end
local v1 = at.vol
check(v1 > 0 and v1 < cs.volumeFor(30, true), 'eased in, part way at 200 m: ' .. tostring(v1))
car = { x = 0, y = -40, z = 10 }
for _ = 1, 30 do cs.tick(0.1, car) end
check(math.abs(at.vol - cs.volumeFor(30, true)) < 1e-6, 'near: full volume')
check(cs.status().method == '3D' and cs.status().playing == 2, 'status: 3D, two playing')
-- the game stopped one: started again
at.playing = false
function at:isPlaying() return self.playing end
cs.update(crowds, car, hash, 'course1')
check(at.playing == true, 'a loop that stopped: started again')
check(n3d == 2 and next(sources) ~= nil and deletedSrc == 0, 'still the same two: nothing new, nothing let go')
local total = 0
for _ in pairs(sources) do total = total + 1 end
check(total == 2, 'no more sources: ' .. total)
-- going away: faded out, then let go
car = { x = 0, y = -600, z = 10 }
cs.update(crowds, car, hash, 'course1')
for _ = 1, 30 do cs.tick(0.1, car) end
check(next(sources) == nil and deletedSrc == 2 and cs.status().playing == 0, 'gone away: faded out and let go')
-- a new course: its own crowds
car = { x = 0, y = -60, z = 10 }
cs.update(crowds, car, hash, 'course1')
cs.update(crowds, car, hash, 'course2')
local after = 0
for _ in pairs(sources) do after = after + 1 end
check(after == 2 and deletedSrc == 4, 'another course: started afresh')
cs.stopAll()
check(next(sources) == nil, 'stopped')
-- Off: silence
cs.setEnabled(false)
cs.update(crowds, { x = 0, y = 2450, z = 10 }, hash, 'course2')
check(next(sources) == nil, 'Crowd sound Off: nothing')
cs.setEnabled(true)

-- 3. a game that will not place a sound: an ordinary one, played again as each pass ends, quieter the farther
package.loaded['offroadCompanion/crowdsound'] = nil
local cs2 = require('offroadCompanion/crowdsound')
placeWorks = false
cs2.update(crowds, { x = 0, y = 2400, z = 10 }, hash, 'c')
check(#twoD == 1 and twoD[1].profile == 'AudioGui' and twoD[1].opts.volume < cs2.volumeFor(6), 'ordinary sound: ' .. #twoD)
check(next(sources) == nil, 'the unplaced source let go')
check(cs2.status().method == '2D' and cs2.status().playing == 1, 'status: 2D, one playing')
cs2.update(crowds, { x = 0, y = 2420, z = 10 }, hash, 'c')
check(#twoD == 1, 'not again while its pass plays')
local clock0 = os.clock
os.clock = function() return clock0() + cs2.LOOP_S end
cs2.update(crowds, { x = 0, y = 2450, z = 10 }, hash, 'c')
check(#twoD == 2 and twoD[2].opts.volume > twoD[1].opts.volume, 'again as it ends, louder nearer')
os.clock = function() return clock0() + 3 * cs2.LOOP_S end
cs2.update(crowds, { x = 0, y = 0, z = 10 }, hash, 'c')          -- (far from the jump now: near the start)
os.clock = function() return clock0() + 5 * cs2.LOOP_S end
cs2.update(crowds, { x = 0, y = 0, z = 10 }, hash, 'c')
os.clock = clock0
check(cs2._active()['jump:250#1'] == nil, 'the jump\'s loop over once far from it')
cs2.stopAll()
-- the test button: a loop ahead, for a few seconds
local n0 = #twoD
local ok = cs2.test({ x = 0, y = 0, z = 10 }, 90)
check(ok and #twoD == n0 + 1, 'Test crowd sound plays one')
-- no audio at all: an error, not a crash
Engine = nil
cs2.stopAll()
local ok2 = cs2.test({ x = 0, y = 0, z = 10 }, 0)
check(not ok2 and cs2.status().error ~= nil, 'no audio: reported')

print(string.format('%d passed, %d failed', pass, fail))
os.exit(fail == 0 and 0 or 1)
