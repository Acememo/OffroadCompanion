-- The streets around the car for the app's map, with their names (from the companion: OpenStreetMap ways in tiles).
-- The tiles are kept in lat / lon; a selection of the ways near the car is made in the world frame and handed to the
-- app only when it changes (a new version: the car moved a third of the way to its edge, new tiles, a new anchor, a
-- much different zoom): every frame the app only gets where the car is in it (offset).
-- Pure apart from the anchor it is given (anchor:geodeticToEnu).
local M = {}

M.SEL_FACTOR = 2.2          -- the selection reaches this many times the map's radius ...
M.MIN_R, M.MAX_R = 1200, 6000
M.MAX_WAYS = 2500
M.MAX_TILES = 64

local tiles = {}            -- key -> ways {c, n, r, p = {{lat, lon}...}}
local order = {}            -- tile keys, oldest first
local framed = {}           -- key -> { anchor, ways = {{c, n, x = {}, y = {}, x0, y0, x1, y1}} }
local sel = { version = 0, anchor = nil, ox = 0, oy = 0, r = 0 }
local dirty = true

function M.addTiles(list)
  local n = 0
  for _, t in ipairs(list or {}) do
    if type(t) == 'table' and t.key and type(t.ways) == 'table' then
      if not tiles[t.key] then order[#order + 1] = t.key end
      tiles[t.key], framed[t.key] = t.ways, nil
      n = n + 1
    end
  end
  while #order > M.MAX_TILES do
    local k = table.remove(order, 1)
    tiles[k], framed[k] = nil, nil
  end
  if n > 0 then dirty = true; M._tv = (M._tv or 0) + 1 end
  return n
end

function M.haveKeys()
  local out = {}
  for k in pairs(tiles) do out[#out + 1] = k end
  return out
end

function M.tileCount() return #order end

local function frameTile(key, anchor)
  local f = framed[key]
  if f and f.anchor == anchor then return f end
  local ways = {}
  for _, w in ipairs(tiles[key] or {}) do
    local xs, ys = {}, {}
    local x0, y0, x1, y1 = math.huge, math.huge, -math.huge, -math.huge
    for i, q in ipairs(w.p or {}) do
      local x, y = anchor:geodeticToEnu(q[1], q[2], 0)
      xs[i], ys[i] = x, y
      if x < x0 then x0 = x end
      if x > x1 then x1 = x end
      if y < y0 then y0 = y end
      if y > y1 then y1 = y end
    end
    if #xs >= 2 then
      local name = (w.n ~= nil and w.n ~= '') and w.n or ((w.r ~= nil and w.r ~= '') and w.r or nil)
      ways[#ways + 1] = { c = w.c, n = name, x = xs, y = ys, x0 = x0, y0 = y0, x1 = x1, y1 = y1 }
    end
  end
  f = { anchor = anchor, ways = ways }
  framed[key] = f
  return f
end

local RANK = { motorway = 1, trunk = 2, primary = 3, secondary = 4, tertiary = 5, unclassified = 6, residential = 6,
               living_street = 7, road = 7, service = 8, pedestrian = 8, track = 9 }

-- A new selection for the app when it is due: { version, ways = {{c, n, p = {x, y, ...}}} } with x, y relative to the
-- selection's origin; nil while the last one still serves. viewR: the map's radius (m).
function M.select(anchor, cx, cy, viewR)
  if not anchor then return nil end
  local R = math.max(M.MIN_R, math.min(M.MAX_R, (viewR or 600) * M.SEL_FACTOR))
  local moved = math.sqrt((cx - sel.ox) ^ 2 + (cy - sel.oy) ^ 2)
  if not dirty and anchor == sel.anchor and moved < sel.r / 3 and R <= sel.r * 1.4 and R >= sel.r / 1.4 then
    return nil
  end
  local ox, oy = math.floor(cx / 10 + 0.5) * 10, math.floor(cy / 10 + 0.5) * 10
  local cand = {}
  for key in pairs(tiles) do
    for _, w in ipairs(frameTile(key, anchor).ways) do
      if w.x1 >= ox - R and w.x0 <= ox + R and w.y1 >= oy - R and w.y0 <= oy + R then
        cand[#cand + 1] = w
      end
    end
  end
  table.sort(cand, function(a, b) return (RANK[a.c] or 7) < (RANK[b.c] or 7) end)
  local ways = {}
  for i = 1, math.min(#cand, M.MAX_WAYS) do
    local w = cand[i]
    local p = {}
    for k = 1, #w.x do
      p[#p + 1] = math.floor((w.x[k] - ox) * 2 + 0.5) / 2
      p[#p + 1] = math.floor((w.y[k] - oy) * 2 + 0.5) / 2
    end
    ways[i] = { c = w.c, n = w.n, p = p }
  end
  sel = { version = sel.version + 1, anchor = anchor, ox = ox, oy = oy, r = R }
  dirty = false
  return { version = sel.version, ways = ways }
end

-- The ways within R of (x, y) in the world frame of anchor: { {c = class, x = {...}, y = {...}} } (the crowds keep off
-- them: roadsnear.fromWays).
function M.waysNear(anchor, x, y, R)
  local out = {}
  if not anchor then return out end
  for key in pairs(tiles) do
    for _, w in ipairs(frameTile(key, anchor).ways) do
      if w.x1 >= x - R and w.x0 <= x + R and w.y1 >= y - R and w.y0 <= y + R then out[#out + 1] = w end
    end
  end
  return out
end

-- A number that changes whenever the tiles do.
function M.tilesVersion() return M._tv or 0 end

-- Where the car is in the current selection (x, y from its origin) and its version.
function M.offset(cx, cy) return cx - sel.ox, cy - sel.oy, sel.version end
function M.version() return sel.version end
function M.invalidate() dirty = true end
function M.reset() framed, sel.anchor, dirty = {}, nil, true end

return M
