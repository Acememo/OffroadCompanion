-- The roads around the car, from the game's own road map (BeamNG.Earth builds it for the AI and the GPS: map.getMap(),
-- nodes { pos, radius (half the road's width), links }, the ~1 km around the player), so spectators never stand on a
-- road (the user, 2026-10-25, a screenshot: a start line in a town, its fence across a side street, people in it).
-- The crowds are made within crowds.SPAWN_M of the car, inside the map's reach: each is checked as it is made.
local M = {}

M.CELL_M = 24
M.MARGIN_M = 0.4            -- clear of a road's edge by this much
M.REFRESH_S = 2.0           -- the road map looked at again at most this often

-- A model's footprint: points (x along its width, y back from its front, m) that must all be off the roads.
M.FOOT = {
  fence = { { -2.3, 0 }, { -1.15, 0 }, { 0, 0 }, { 1.15, 0 }, { 2.3, 0 } },
  crowd = { { -1.1, 0.2 }, { 0, 0.2 }, { 1.1, 0.2 }, { 0, 0.9 } },
  canopy = { { -1.4, -1.4 }, { 1.4, -1.4 }, { 1.4, 1.4 }, { -1.4, 1.4 }, { 0, 0 } },
  lantern = { { 0, 0 } },
  pickup = { { 0, -2.6 }, { 0, -1.2 }, { 0, 0.2 }, { 0, 1.5 }, { 0, 2.7 }, { -0.9, 0 }, { 0.9, 0 } },
  suv = { { 0, -2.6 }, { 0, -1.2 }, { 0, 0.2 }, { 0, 1.5 }, { 0, 2.7 }, { -0.9, 0 }, { 0.9, 0 } },
  light_tower = { { 0, -1.1 }, { 0, 1.1 }, { 0, 2.2 } },
  lamps = { { 0, 0 } },
  chair = { { 0, 0 } },
}
M.FOOT_DEFAULT = { { 0, 0 } }

local index = nil           -- { cells = { key -> { seg ... } } } of the map in use
local mapRef, mapN, checkedAt = nil, -1, -math.huge

-- Pure: an index of the roads of node table `nodes` (map.getMap().nodes: id -> { pos = {x, y}, radius, links }):
-- every link once, as a segment with its two half widths, filed in the grid cells it passes.
function M.build(nodes)
  local cells, n = {}, 0
  local G = M.CELL_M
  local function add(cx, cy, s)
    local k = cx * 1000003 + cy
    local c = cells[k]
    if not c then c = {}; cells[k] = c end
    c[#c + 1] = s
  end
  for a, A in pairs(nodes or {}) do
    if type(A) == 'table' and A.pos and type(A.links) == 'table' then
      for b in pairs(A.links) do
        local B = nodes[b]
        if B and B.pos and tostring(a) < tostring(b) then
          local s = { ax = A.pos.x, ay = A.pos.y, bx = B.pos.x, by = B.pos.y,
                      ra = tonumber(A.radius) or 3, rb = tonumber(B.radius) or 3 }
          n = n + 1
          local L = math.sqrt((s.bx - s.ax) ^ 2 + (s.by - s.ay) ^ 2)
          local r = math.max(s.ra, s.rb) + M.MARGIN_M
          local k = math.max(1, math.ceil(L / (G / 2)))
          local seen = {}
          for j = 0, k do
            local t = j / k
            local x, y = s.ax + t * (s.bx - s.ax), s.ay + t * (s.by - s.ay)
            for cx = math.floor((x - r) / G), math.floor((x + r) / G) do
              for cy = math.floor((y - r) / G), math.floor((y + r) / G) do
                local key = cx * 1000003 + cy
                if not seen[key] then seen[key] = true; add(cx, cy, s) end
              end
            end
          end
        end
      end
    end
  end
  return { cells = cells, n = n }
end

-- OpenStreetMap's ways (the companion's street tiles, streetmap.lua: tracks and dirt roads too, which the game's road
-- map leaves out; the user, 2026-10-28: spectators "block the road and confuses the drivers as to where the track is")
-- as half widths a car drives on, by class (m)
M.OSM_HALF = { motorway = 7.0, trunk = 6.0, primary = 5.0, secondary = 4.5, tertiary = 4.0, unclassified = 3.5,
               residential = 3.5, living_street = 3.0, road = 3.0, service = 2.5, track = 2.0 }

-- Pure: an index (as build's) of ways { {c, x = {...}, y = {...}} } with OSM_HALF's half widths.
function M.fromWays(ways)
  local nodes, n = {}, 0
  for _, w in ipairs(ways or {}) do
    local r = M.OSM_HALF[w.c] or 3.0
    local prev = nil
    for i = 1, #(w.x or {}) do
      n = n + 1
      nodes[n] = { pos = { x = w.x[i], y = w.y[i] }, radius = r, links = {} }
      if prev then nodes[prev].links[n] = true; nodes[n].links[prev] = true end
      prev = n
    end
  end
  return M.build(nodes)
end

-- Pure: one index of several (the game's road map, OpenStreetMap's ways): nil parts left out.
function M.combine(...)
  local parts, v = {}, ''
  for i = 1, select('#', ...) do
    local p = select(i, ...)
    if p then parts[#parts + 1] = p; v = v .. tostring(p.version or 0) .. ':' end
  end
  if #parts == 0 then return nil end
  return { parts = parts, version = v }
end

-- Pure: is (x, y) on a road of index idx (within its half width + MARGIN_M)?
function M.onRoad(idx, x, y)
  if not idx then return false end
  if idx.parts then
    for _, p in ipairs(idx.parts) do if M.onRoad(p, x, y) then return true end end
    return false
  end
  local c = idx.cells[math.floor(x / M.CELL_M) * 1000003 + math.floor(y / M.CELL_M)]
  if not c then return false end
  for _, s in ipairs(c) do
    local dx, dy = s.bx - s.ax, s.by - s.ay
    local L2 = dx * dx + dy * dy
    local t = L2 > 0 and math.max(0, math.min(1, ((x - s.ax) * dx + (y - s.ay) * dy) / L2)) or 0
    local d = math.sqrt((s.ax + t * dx - x) ^ 2 + (s.ay + t * dy - y) ^ 2)
    if d < s.ra + t * (s.rb - s.ra) + M.MARGIN_M then return true end
  end
  return false
end

-- Pure: does a `model` standing at (x, y) turned by yaw (its front -y turned: (sin yaw, -cos yaw)) touch a road?
function M.blocked(idx, model, x, y, yaw)
  if not idx then return false end
  local m = tostring(model or '')
  local foot = M.FOOT_DEFAULT
  for k, f in pairs(M.FOOT) do if m:sub(1, #k) == k then foot = f; break end end
  local c, s = math.cos(yaw or 0), math.sin(yaw or 0)
  for _, p in ipairs(foot) do
    -- (model x, y) turned by yaw: x' = c x - s y, y' = s x + c y
    if M.onRoad(idx, x + c * p[1] - s * p[2], y + s * p[1] + c * p[2]) then return true end
  end
  return false
end

-- The index of the game's road map now (built again when the map changed); nil when there is none.
function M.current(now)
  now = now or os.clock()
  if now - checkedAt < M.REFRESH_S then return index end
  checkedAt = now
  local mp = rawget(_G, 'map')
  local ok, m = pcall(function() return mp and mp.getMap and mp.getMap() end)
  if not ok or type(m) ~= 'table' or type(m.nodes) ~= 'table' then index = nil; return nil end
  local n = 0
  for _ in pairs(m.nodes) do n = n + 1 end
  if m.nodes ~= mapRef or n ~= mapN or not index then
    mapRef, mapN = m.nodes, n
    index = n > 0 and M.build(m.nodes) or nil
    if index then index.version = (M.version or 0) + 1; M.version = index.version end
  end
  return index
end

function M.reset() index, mapRef, mapN, checkedAt = nil, nil, -1, -math.huge end

return M
