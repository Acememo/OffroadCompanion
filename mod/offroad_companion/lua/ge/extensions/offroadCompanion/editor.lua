-- Making a track in the game: record it by driving (a point every STEP_M), add the car's spot, or tap points on the
-- app's map; undo, clear, save (the companion writes a GPX into the tracks folder, then it is loaded like any
-- course: BeamNG.Earth's server clears it of buildings, walls and low bridges and lays its dirt track).
-- Points are kept in lat / lon. Pure apart from the anchor it is given.
local M = {}

M.STEP_M = 8
M.MAX_POINTS = 20000

local mode = 'off'          -- 'off' | 'record' | 'plan'
local pts = {}              -- {{lat, lon}...}
local cps = {}              -- checkpoints {{name, lat, lon, after = number of points when it was added}}
local framedFor, fx, fy = nil, {}, {}

local function geod(a, b)
  local r = math.rad
  local p1, p2 = r(a[1]), r(b[1])
  local h = math.sin((p2 - p1) / 2) ^ 2 + math.cos(p1) * math.cos(p2) * math.sin(r(b[2] - a[2]) / 2) ^ 2
  return 2 * 6371008.8 * math.asin(math.min(1, math.sqrt(h)))
end
M.geod = geod

function M.setMode(m)
  if m ~= 'record' and m ~= 'plan' then m = 'off' end
  mode = m
  return mode
end
function M.mode() return mode end

function M.add(lat, lon)
  lat, lon = tonumber(lat), tonumber(lon)
  if not lat or not lon or #pts >= M.MAX_POINTS then return false end
  local last = pts[#pts]
  if last and geod(last, { lat, lon }) < 0.5 then return false end
  pts[#pts + 1] = { lat, lon }
  framedFor = nil
  return true
end

function M.checkpoint(lat, lon)
  lat, lon = tonumber(lat), tonumber(lon)
  if not lat or not lon then return false end
  cps[#cps + 1] = { name = 'CP ' .. (#cps + 1), lat = lat, lon = lon, after = #pts }
  return true
end

-- Recording: called with the car's lat / lon; a point when it has moved STEP_M from the last.
function M.update(lat, lon)
  if mode ~= 'record' or not lat then return false end
  local last = pts[#pts]
  if not last or geod(last, { lat, lon }) >= M.STEP_M then return M.add(lat, lon) end
  return false
end

-- Undo: the last checkpoint if it was added after the last point, else the last point.
function M.undo()
  if #cps > 0 and cps[#cps].after >= #pts then
    cps[#cps] = nil
    return
  end
  pts[#pts] = nil
  framedFor = nil
end

function M.clear() pts, cps, framedFor = {}, {}, nil end

function M.length()
  local s = 0
  for i = 2, #pts do s = s + geod(pts[i - 1], pts[i]) end
  return s
end

function M.points() return pts end
function M.checkpoints()
  local out = {}
  for i, c in ipairs(cps) do out[i] = { name = c.name, lat = c.lat, lon = c.lon } end
  return out
end

function M.state()
  return { mode = mode, n = #pts, length = M.length(), checkpoints = #cps }
end

-- For the map: the points car-relative (x east, y north) in the anchor's frame, as lines {{{x, y}...}...}: only the
-- part within `reach` metres of the car (a point is kept when it or a neighbour is inside), and the checkpoints
-- {{x, y, name}}.
function M.mapLines(anchor, cx, cy, reach)
  if not anchor or (#pts == 0 and #cps == 0) then return {}, {} end
  if framedFor ~= anchor then
    fx, fy = {}, {}
    for i, q in ipairs(pts) do fx[i], fy[i] = anchor:geodeticToEnu(q[1], q[2], 0) end
    framedFor = anchor
  end
  reach = reach or math.huge
  local function inside(i)
    return fx[i] ~= nil and math.abs(fx[i] - cx) <= reach and math.abs(fy[i] - cy) <= reach
  end
  local lines, cur = {}, nil
  for i = 1, #fx do
    if inside(i) or inside(i - 1) or inside(i + 1) then
      if not cur then cur = {}; lines[#lines + 1] = cur end
      cur[#cur + 1] = { math.floor((fx[i] - cx) * 10 + 0.5) / 10, math.floor((fy[i] - cy) * 10 + 0.5) / 10 }
    else
      cur = nil
    end
  end
  local marks = {}
  for _, c in ipairs(cps) do
    local x, y = anchor:geodeticToEnu(c.lat, c.lon, 0)
    marks[#marks + 1] = { math.floor(x - cx + 0.5), math.floor(y - cy + 0.5), c.name }
  end
  return lines, marks
end

return M
