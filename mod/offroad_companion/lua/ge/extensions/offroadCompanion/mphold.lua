-- The car kept still while BeamNG.Earth holds it in a BeamMP session (the user, 2026-10-25: "When the red banner that
-- the car is frozen and waiting for beamng.earth server, tested on beamMP, the car does not freeze and it starts lifting
-- up like a balloon and as soon as the terrain loads the car comes falling down").
--
-- Alone, BeamNG.Earth pauses the game while the ground under the car loads. In a BeamMP session it cannot (that stops
-- every player's cars on this screen), so since 1.6.2 it holds only our car: its gravity off and its motion stopped once
-- (beamngEarth/simhold.lua). But a car standing on the ground has its springs and tyres pressed down by its weight:
-- with gravity gone they push it up, and nothing stops it, so it floats off and falls when the ground comes. Here its
-- motion is stopped every frame while the hold lasts (the same call BeamNG.Earth makes once): the springs can only
-- ease out a few centimetres, and it stays where it was.
local M = {}

M.held = false              -- (holding now: for the status / tests)
M.frames = 0                -- frames held since the hold began

local function simhold()
  local sh = package.loaded['beamngEarth/simhold']
  if type(sh) == 'table' and type(sh.carHeld) == 'function' then return sh end
  return nil
end

-- Every frame: while BeamNG.Earth holds our car (BeamMP), its motion stopped.
function M.tick()
  local sh = simhold()
  local ok, held = false, false
  if sh then ok, held = pcall(sh.carHeld) end
  if not (ok and held) then
    M.held, M.frames = false, 0
    return false
  end
  local veh = rawget(_G, 'getPlayerVehicle') and getPlayerVehicle(0)
  if not (veh and veh.getRefNodeId and veh.applyClusterVelocityScaleAdd) then return false end
  pcall(function() veh:applyClusterVelocityScaleAdd(veh:getRefNodeId(), 0, 0, 0, 0) end)
  M.held, M.frames = true, M.frames + 1
  return true
end

return M
