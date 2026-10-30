-- Small fixes to BeamNG.Earth's own code, applied while it runs (its files are not changed), each guarded so it does
-- nothing once BeamNG.Earth fixes the thing itself.
--
-- The big map in a BeamMP session with no other player known (the user, 2026-10-25: the console full of
-- "EarthMap.vue:179 Uncaught (in promise) TypeError: (state.value.others || []).map is not a function" and Vue's
-- "Unhandled error during execution of render function", every second): beamngEarth_settings.uiMapState() hands the
-- map the other players as a Lua list, and an empty one reaches the page as {} (the game's JSON writes an empty table
-- as an object), which is not an array, so the map's render fails. An empty list is handed on as nil here (the page's
-- "|| []" then gives it one); a list with players in it is left as it is.
local M = {}

M.applied = {}

-- Pure: a map state with an empty "others" list made nil.
function M.fixMapState(st)
  if type(st) == 'table' and type(st.others) == 'table' and next(st.others) == nil then st.others = nil end
  return st
end

local function mapState()
  local s = rawget(_G, 'beamngEarth_settings')
  if type(s) ~= 'table' or type(s.uiMapState) ~= 'function' or s._offroadMapFix then return false end
  local orig = s.uiMapState
  s.uiMapState = function(...) return M.fixMapState(orig(...)) end
  s._offroadMapFix = true
  M.applied.mapState = true
  if log then log('I', 'offroadCompanion', 'BeamNG.Earth: its map\'s empty player list handed on as none') end
  return true
end

-- The high-voltage lines' lattice towers (BeamNG.Earth 1.7: trees.lua's group "pylon", items of its Forest that collide
-- near the car) made render-only (the user, 2026-10-28: "can we make the powerline towers non collidable?"): a 36 m
-- steel tower stands where a mapped line crosses open country, often right on or beside a course, and stopped a race
-- dead. The group joins trees.lua's own NO_COLLIDE (its bushes, lamp glows, ...): the towers near the car are made again
-- as the non-colliding kind. The substations' parts stay solid (behind their fences).
M.NO_COLLIDE = { 'pylon' }
local function towers()
  local tr = package.loaded['beamngEarth/trees']
  if type(tr) ~= 'table' or type(tr.NO_COLLIDE) ~= 'table' then return false end
  local added = false
  for _, g in ipairs(M.NO_COLLIDE) do
    if not tr.NO_COLLIDE[g] then tr.NO_COLLIDE[g] = true; added = true end
  end
  if added then
    M.applied.towers = true
    if log then log('I', 'offroadCompanion', 'BeamNG.Earth: power line towers made non-colliding') end
  end
  return true
end

-- Every so often (BeamNG.Earth's extensions load after ours, and again after a level change): the fixes in place.
function M.apply()
  pcall(mapState)
  pcall(towers)
end

return M
