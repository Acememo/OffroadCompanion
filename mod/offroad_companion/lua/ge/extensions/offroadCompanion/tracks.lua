-- The course's dirt track drawn in the game, for a BeamNG.Earth whose server has no course painter (its packaged
-- .exe): the companion plans the track (OffroadCompanion/gpsd/paintsource.py: where the course leaves the roads, how wide
-- from the terrain clearance) and this draws it as dirt DecalRoads, streamed with BeamNG.Earth's own road tiles.
--
-- It hooks BeamNG.Earth's road tiles (beamngEarth/roads.lua): when a tile arrives (onTile), the track pieces over its
-- square are clipped to it and drawn (Johnson Valley's m_dirt_road, the material BeamNG.Earth's dirt roads use);
-- when the tile goes (onDrop, a new anchor, a rebase, roads off, the level's end) its track goes with it. So the
-- track is there exactly where BeamNG.Earth's roads are, in the same frame, and never piles up behind the car.
-- The tiles are recorded even while nothing is drawn, so a course loaded later is drawn on the tiles already there.
--
-- (With the course painter in BeamNG.Earth's server the track is part of its road data instead: graded ground and
-- the dirt feel; main.lua picks one or the other.)
local M = {}

M.TILE_M = 256
M.OVERLAP = 2.0
M.PER_FRAME = 3             -- DecalRoads made per frame at most
M.MAX_NODES = 100
M.MATERIAL, M.TEXTURE_LENGTH, M.PRIORITY = 'm_dirt_road', 88, 22
M.GROUP = 'OffroadCompanion_tracks'
M.FADE = '450 150'

local active = false
local cid = nil
local pieces = {}           -- { id, w, ll = {{lon, lat}...}, z = {...}, box = {lon0, lat0, lon1, lat1} }
local seen = {}             -- piece id -> true
local tiles = {}            -- key "aid:tx_ty" -> { aid, tx, ty, objs = {}, drawn = { piece id = true } }
local anchorAid = nil
local queue = {}            -- { key, nodes = {{x, y, z}...}, w }
local hooked = nil          -- { mod = roads module, orig = { name = fn } }
local getAnchor = nil       -- function(aid) -> geodesy anchor of that anchor id, or nil
M.made, M.deleted, M.errors = 0, 0, 0

-- -- pure helpers ------------------------------------------------------------------------------------------------
-- Pure: the parts of polyline pts {{x, y, z}...} inside the box [x0, x1] x [y0, y1] (Liang-Barsky per segment, runs
-- joined), each a list of at least two points.
function M.clip(pts, x0, y0, x1, y1)
  local out, run = {}, nil
  local function inside(p) return p[1] >= x0 and p[1] <= x1 and p[2] >= y0 and p[2] <= y1 end
  for i = 1, #pts - 1 do
    local a, b = pts[i], pts[i + 1]
    local dx, dy, dz = b[1] - a[1], b[2] - a[2], b[3] - a[3]
    local t0, t1 = 0, 1
    local ok = true
    for _, c in ipairs({ { -dx, a[1] - x0 }, { dx, x1 - a[1] }, { -dy, a[2] - y0 }, { dy, y1 - a[2] } }) do
      local p, q = c[1], c[2]
      if p == 0 then
        if q < 0 then ok = false end
      else
        local r = q / p
        if p < 0 then if r > t1 then ok = false elseif r > t0 then t0 = r end
        else if r < t0 then ok = false elseif r < t1 then t1 = r end end
      end
    end
    if ok then
      local pa = { a[1] + t0 * dx, a[2] + t0 * dy, a[3] + t0 * dz }
      local pb = { a[1] + t1 * dx, a[2] + t1 * dy, a[3] + t1 * dz }
      if not run then run = { pa } end
      run[#run + 1] = pb
      if t1 < 1 then out[#out + 1] = run; run = nil end
    elseif run then
      out[#out + 1] = run; run = nil
    end
  end
  if run then out[#out + 1] = run end
  local keep = {}
  for _, r in ipairs(out) do if #r >= 2 then keep[#keep + 1] = r end end
  return keep
end

local function box(p)
  local x0, y0, x1, y1 = math.huge, math.huge, -math.huge, -math.huge
  for _, q in ipairs(p.ll) do
    if q[1] < x0 then x0 = q[1] end
    if q[1] > x1 then x1 = q[1] end
    if q[2] < y0 then y0 = q[2] end
    if q[2] > y1 then y1 = q[2] end
  end
  return { x0, y0, x1, y1 }
end

-- -- the scene ---------------------------------------------------------------------------------------------------
local function group()
  local g = scenetree.findObject(M.GROUP)
  if not g then
    g = createObject('SimGroup')
    g.canSave = false
    g:registerObject(M.GROUP)
    scenetree.MissionGroup:addObject(g)
  end
  return g
end

local function fields()
  local c = { m = M.MATERIAL, tl = M.TEXTURE_LENGTH, p = M.PRIORITY }
  local r = hooked and hooked.mod and hooked.mod.fieldsFor
  if r then
    local ok, f = pcall(r, c)
    if ok and type(f) == 'table' then return f end
  end
  return { { 'material', c.m }, { 'textureLength', tostring(c.tl) }, { 'renderPriority', tostring(c.p) },
           { 'drivability', '-1' }, { 'improvedSpline', 'true' }, { 'overObjects', 'false' },
           { 'distanceFade', M.FADE }, { 'decalBias', '0.1' } }
end

local function makeRoad(nodes, w)
  local r = createObject('DecalRoad')
  for _, f in ipairs(fields()) do r:setField(f[1], 0, f[2]) end
  r.canSave = false
  r:registerObject('')
  group():addObject(r)
  for _, n in ipairs(nodes) do r:insertNodeNoRegen(vec3(n[1], n[2], n[3]), w, -1) end
  r:regenerate()
  M.made = M.made + 1
  return r:getId()
end

local function deleteIds(ids)
  for _, id in ipairs(ids) do
    local o = scenetree.findObjectById(id)
    if o then o:delete(); M.deleted = M.deleted + 1 end
  end
end

local function dropTile(key)
  local t = tiles[key]
  if not t then return end
  deleteIds(t.objs)
  t.objs, t.drawn = {}, {}
  local keep = {}
  for _, q in ipairs(queue) do if q.key ~= key then keep[#keep + 1] = q end end
  queue = keep
end

local function forgetTile(key)
  dropTile(key)
  tiles[key] = nil
end

local function dropAll(forget)
  for key in pairs(tiles) do dropTile(key) end
  if forget then tiles = {} end
  queue = {}
end

-- BeamNG.Earth 1.7.2's road geotiles ('g17_x_y', roads.lua onGeoTile): a tile of a global Web-Mercator grid that
-- belongs to no anchor and stays across rebases and teleports near (placed into the new anchor: roads.replace). Its
-- track is clipped by latitude / longitude and drawn in the current anchor's frame, again after each rebase.
-- Pure: (z, x, y) of a geotile key, or nil.
function M.geoParse(key)
  local z, x, y = tostring(key):match('^g(%d+)_(%-?%d+)_(%-?%d+)$')
  if not z then return nil end
  return tonumber(z), tonumber(x), tonumber(y)
end

-- Pure: a geotile's { west, south, east, north } in degrees (as BeamNG.Earth's geotile.bounds).
function M.geoBounds(z, x, y)
  local n = 2 ^ z
  local function lat(yf) local t = math.pi * (1 - 2 * yf / n); return math.deg(math.atan(0.5 * (math.exp(t) - math.exp(-t)))) end
  return { x / n * 360 - 180, lat(y + 1), (x + 1) / n * 360 - 180, lat(y) }
end

-- The anchor's tiles dropped (a new anchor, a rebase); the geotiles' objects too, the geotiles kept (drawn again on
-- the next anchor: replaced).
local function dropAnchorTiles()
  for key, t in pairs(tiles) do
    dropTile(key)
    if not t.geo then tiles[key] = nil end
  end
  queue = {}
end

-- -- drawing ---------------------------------------------------------------------------------------------------------
-- The piece in the anchor's frame: {x, y, z} per node (kept per anchor).
local function framed(p, anchor)
  if p._anchor == anchor then return p._pts end
  local pts = {}
  for i, q in ipairs(p.ll) do
    local x, y, z = anchor:geodeticToEnu(q[2], q[1], (p.z and p.z[i]) or 0)
    pts[i] = { x, y, z }
  end
  p._anchor, p._pts = anchor, pts
  return pts
end

-- The tile's square in lat / lon (its corners; for the cheap test against the pieces' boxes).
local function tileBox(t, anchor)
  if t.box and t.boxAnchor == anchor then return t.box end
  local x0, y0 = t.tx * M.TILE_M - 10, t.ty * M.TILE_M - 10
  local x1, y1 = x0 + M.TILE_M + 20, y0 + M.TILE_M + 20
  local la0, lo0, la1, lo1 = math.huge, math.huge, -math.huge, -math.huge
  for _, c in ipairs({ { x0, y0 }, { x1, y0 }, { x0, y1 }, { x1, y1 } }) do
    local la, lo = anchor:enuToGeodetic(c[1], c[2], 0)
    la0, la1 = math.min(la0, la), math.max(la1, la)
    lo0, lo1 = math.min(lo0, lo), math.max(lo1, lo)
  end
  t.box, t.boxAnchor = { lo0, la0, lo1, la1 }, anchor
  return t.box
end

-- A piece's runs inside geotile t, in anchor's frame (clipped by longitude / latitude: the tiles share their edges).
local function geoRuns(p, t, anchor)
  local g = t.geoBox
  local pts = {}
  for i, q in ipairs(p.ll) do pts[i] = { q[1], q[2], (p.z and p.z[i]) or 0 } end
  local out = {}
  for _, run in ipairs(M.clip(pts, g[1], g[2], g[3], g[4])) do
    local r = {}
    for i, q in ipairs(run) do
      local x, y, z = anchor:geodeticToEnu(q[2], q[1], q[3])
      r[i] = { x, y, z }
    end
    out[#out + 1] = r
  end
  return out
end

-- Queue the pieces over tile key (those not drawn there yet).
local function drawTile(key)
  local t = tiles[key]
  if not t or not active or #pieces == 0 then return end
  local anchor = getAnchor and getAnchor(t.aid)
  if not anchor then return end
  if t.geoBox then
    local b = t.geoBox
    for _, p in ipairs(pieces) do
      local pb = p.box
      if not t.drawn[p.id] and pb[1] <= b[3] and pb[3] >= b[1] and pb[2] <= b[4] and pb[4] >= b[2] then
        t.drawn[p.id] = true
        for _, run in ipairs(geoRuns(p, t, anchor)) do
          local i = 1
          while i < #run do
            local j = math.min(#run, i + M.MAX_NODES - 1)
            local nodes = {}
            for k = i, j do nodes[#nodes + 1] = run[k] end
            queue[#queue + 1] = { key = key, nodes = nodes, w = p.w }
            i = j
          end
        end
      end
    end
    return
  end
  local b = tileBox(t, anchor)
  local x0, y0 = t.tx * M.TILE_M - M.OVERLAP, t.ty * M.TILE_M - M.OVERLAP
  local x1, y1 = (t.tx + 1) * M.TILE_M + M.OVERLAP, (t.ty + 1) * M.TILE_M + M.OVERLAP
  for _, p in ipairs(pieces) do
    local pb = p.box
    if not t.drawn[p.id] and pb[1] <= b[3] and pb[3] >= b[1] and pb[2] <= b[4] and pb[4] >= b[2] then
      t.drawn[p.id] = true
      for _, run in ipairs(M.clip(framed(p, anchor), x0, y0, x1, y1)) do
        -- (long runs in chunks of MAX_NODES, sharing their end nodes)
        local i = 1
        while i < #run do
          local j = math.min(#run, i + M.MAX_NODES - 1)
          local nodes = {}
          for k = i, j do nodes[#nodes + 1] = run[k] end
          queue[#queue + 1] = { key = key, nodes = nodes, w = p.w }
          i = j
        end
      end
    end
  end
end

-- -- BeamNG.Earth's road tiles ----------------------------------------------------------------------------------------
local function onEarthTile(msg, currentAnchor)
  if type(msg) ~= 'table' or not msg.key then return end
  local gz, gx, gy = M.geoParse(msg.key)
  if gz then                                  -- a geotile: any anchor's, drawn in the current one
    local key = 'g:' .. tostring(msg.key)
    if tiles[key] then dropTile(key) end
    tiles[key] = { aid = currentAnchor ~= nil and currentAnchor or msg.anchorId, geo = true,
      geoBox = M.geoBounds(gz, gx, gy), objs = {}, drawn = {} }
    drawTile(key)
    return
  end
  if msg.anchorId ~= anchorAid then          -- a new anchor: BeamNG.Earth drops the old one's roads, so do we
    dropAnchorTiles()
    anchorAid = msg.anchorId
  end
  local tx, ty = tostring(msg.key):match('^(%-?%d+)_(%-?%d+)$')
  if not tx then return end
  local key = tostring(msg.anchorId) .. ':' .. tostring(msg.key)
  if tiles[key] then dropTile(key) end
  tiles[key] = { aid = msg.anchorId, tx = tonumber(tx), ty = tonumber(ty), objs = {}, drawn = {} }
  drawTile(key)
end

local function wrap(mod, name, after)
  local orig = mod[name]
  if type(orig) ~= 'function' then return end
  hooked.orig[name] = orig
  mod[name] = function(...)
    local r = { orig(...) }
    local ok, err = pcall(after, r[1], ...)
    if not ok then
      M.errors = M.errors + 1
      M.lastError = tostring(err)
    end
    return unpack(r)
  end
  hooked.mine[name] = mod[name]
end

-- Hook BeamNG.Earth's roads (again after a Lua reload replaced its module). Returns whether hooked.
function M.install()
  local ok, mod = pcall(require, 'beamngEarth/roads')
  if not ok or type(mod) ~= 'table' then return false end
  if hooked and hooked.mod == mod and mod.onTile == hooked.mine.onTile then return true end
  hooked = { mod = mod, orig = {}, mine = {} }
  tiles, anchorAid, queue = {}, nil, {}
  wrap(mod, 'onTile', function(r, msg, currentAnchor) if r then onEarthTile(msg, currentAnchor) end end)
  wrap(mod, 'onDrop', function(_, msg)
    if type(msg) ~= 'table' then return end
    if M.geoParse(msg.key) then forgetTile('g:' .. tostring(msg.key))
    else forgetTile(tostring(msg.anchorId) .. ':' .. tostring(msg.key)) end
  end)
  -- a rebase: BeamNG.Earth deletes its DecalRoads (old frame) and the new anchor's tiles follow; its geotiles stay and
  -- are placed into the new anchor (replace): their track drawn there again
  wrap(mod, 'transform', function() dropAnchorTiles() end)
  wrap(mod, 'replace', function(_, a, aid)
    for key, t in pairs(tiles) do
      if t.geo then
        dropTile(key)
        t.aid = aid
        drawTile(key)
      end
    end
  end)
  wrap(mod, 'clear', function() dropAll(true) end)
  wrap(mod, 'reset', function() tiles, queue, anchorAid = {}, {}, nil end)   -- (the level took the objects)
  pcall(function()                                                     -- a previous Lua state's objects
    local g = scenetree.MissionGroup and scenetree.findObject(M.GROUP)
    if g and g:getCount() > 0 then g:deleteAllObjects() end
  end)
  return true
end

function M.uninstall()
  if not hooked then return end
  for name, fn in pairs(hooked.orig) do
    if hooked.mod[name] == hooked.mine[name] then hooked.mod[name] = fn end
  end
  dropAll(true)
  hooked = nil
end

-- -- the course's pieces ------------------------------------------------------------------------------------------
-- Drawing on / off (off: the track goes, the tiles stay recorded).
function M.setActive(on, anchorFn)
  getAnchor = anchorFn or getAnchor
  on = on and true or false
  if on == active then return end
  active = on
  if not on then
    dropAll(false)
    pieces, seen, cid = {}, {}, nil
  end
end

-- New windows of the course `newCid` ({ {k, pieces = {...}} }); another cid: the old track goes first. Returns the
-- number of new pieces.
function M.addWindows(newCid, windows)
  if newCid ~= cid then
    dropAll(false)
    pieces, seen, cid = {}, {}, newCid
  end
  local n = 0
  for _, w in ipairs(windows or {}) do
    for _, p in ipairs(w.pieces or {}) do
      if type(p) == 'table' and p.id and not seen[p.id] and type(p.ll) == 'table' and #p.ll >= 2 then
        seen[p.id] = true
        p.box = box(p)
        p.w = tonumber(p.w) or 4
        pieces[#pieces + 1] = p
        n = n + 1
      end
    end
  end
  if n > 0 then for key in pairs(tiles) do drawTile(key) end end
  return n
end

function M.cid() return cid end

-- Every frame: a few of the queued DecalRoads made.
function M.update()
  local made = 0
  while made < M.PER_FRAME and #queue > 0 do
    local q = table.remove(queue, 1)
    local t = tiles[q.key]
    if t then
      local ok, id = pcall(makeRoad, q.nodes, q.w)
      if ok then t.objs[#t.objs + 1] = id
      else M.errors, M.lastError = M.errors + 1, tostring(id) end
      made = made + 1
    end
  end
end

function M.status()
  local nt, nobj = 0, 0
  for _, t in pairs(tiles) do
    nt = nt + 1
    nobj = nobj + #t.objs
  end
  return { active = active, hooked = hooked ~= nil, cid = cid, pieces = #pieces, tiles = nt, roads = nobj,
           queued = #queue, made = M.made, errors = M.errors, lastError = M.lastError }
end

return M
