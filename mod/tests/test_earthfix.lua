-- luajit test_earthfix.lua (from mod/tests): small fixes to BeamNG.Earth's own code, applied while it runs.
package.path = '../offroad_companion/lua/ge/extensions/?.lua;' .. package.path
local pass, fail = 0, 0
local function check(cond, name) if cond then pass = pass + 1 else fail = fail + 1; print('FAIL: ' .. name) end end
function log() end

local fix = require('offroadCompanion/earthfix')

-- the map's empty player list
local st = fix.fixMapState({ others = {} })
check(st.others == nil, 'an empty list handed on as none')
check(#fix.fixMapState({ others = { { lat = 1 } } }).others == 1, 'a list with players kept')

-- the power line towers: BeamNG.Earth's trees.lua NO_COLLIDE gets "pylon"
fix.apply()
check(not fix.applied.towers, 'no BeamNG.Earth trees module: nothing done')
local trees = { NO_COLLIDE = { shrub = true, desert_shrub = true } }
package.loaded['beamngEarth/trees'] = trees
fix.apply()
check(trees.NO_COLLIDE.pylon == true and trees.NO_COLLIDE.shrub == true, 'the towers never collide; the rest as it was')
check(trees.NO_COLLIDE.gantry == nil and trees.NO_COLLIDE.sub_transformer == nil, 'the substations stay solid')
check(fix.applied.towers, 'said so')
local trees2 = { NO_COLLIDE = {} }                 -- (a Lua reload: a new module)
package.loaded['beamngEarth/trees'] = trees2
fix.apply()
check(trees2.NO_COLLIDE.pylon == true, 'again after BeamNG.Earth reloaded')
package.loaded['beamngEarth/trees'] = nil

-- closing the game in BeamMP: BeamNG.Earth's mod not switched back on then
local calls = 0
local bm = { onServerLeave = function() calls = calls + 1; return true end }
package.loaded['beamngEarth/beammp'] = bm
fix.apply()
check(bm.onServerLeave() == true and calls == 1, 'leaving a server in play: switched back on as before')
fix.exiting = true
check(bm.onServerLeave() == false and calls == 1, 'the game closing: left as it is')
fix.apply()
fix.exiting = false
check(bm.onServerLeave() == true and calls == 2, 'wrapped once')
package.loaded['beamngEarth/beammp'] = nil

print(pass .. ' passed, ' .. fail .. ' failed')
if fail > 0 then os.exit(1) end
