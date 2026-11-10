-- Spectators along the course (the user, 2026-10-25: "spectator models around the sections of the track where it would
-- make sense"). Where people gather at a desert race:
--   start / finish   the biggest crowds, both sides, under pop-up canopies, flags
--   checkpoints      the checkpoint crew's canopy, chairs and a cooler on one side, a few fans on the other
--   jumps            fans both sides of the landing (the track terrain's kickers: the companion says where, the same
--                    ones the ground has: OffroadCompanion/gpsd/spots.py)
--   danger spots     a group well back from the course (the course file's DANGER waypoints)
--   paved crossings  people parked by the road walk over (the companion again: where the course crosses a paved road)
--   hairpins         a group on the inside of the turn (cars run wide on the outside)
-- Gates (start, finish, checkpoints) always get theirs; the others at most one per BIN_M of course (the best kind:
-- jumps before danger spots before crossings before hairpins), and none near a gate. Settings: Off / Some / Lots.
--
-- Every choice (which spot of a stretch, how many people, who stands where, their poses and clothes) is a hash of the
-- course's place, so the crowds are the same for everyone on the same course; a stretch gets its crowd only once all
-- its jumps and crossings are known (the companion's answers come in around the car), never from part of them.
-- Spectators stand past the track's edge (its real width where the companion knows it: markers.placeFor's rule),
-- face the course, and turn to watch the car going by. Nothing collides: a crowd never ends a run.
local poly = require('offroadCompanion/poly')
local markers = require('offroadCompanion/markers')
local roadsnear = require('offroadCompanion/roadsnear')
local streetmap = require('offroadCompanion/streetmap')

local M = {}

M.level = 'some'            -- 'off' | 'some' | 'lots'
M.BIN_M = { some = 1600, lots = 800 }
M.SCALE = { some = 1.0, lots = 1.7 }
M.GATE_CLEAR_M = 300        -- no other crowd this near a gate's
M.HAIRPIN_DEG = 110
M.SPAWN_M, M.DESPAWN_M = 450, 650
-- Parked vehicles and canopies stand only on open, nearly level ground (the user, 2026-10-31: pickups on rooftops in
-- town and floating off a hillside): rays down at their middle and FOOT_R[kind] m out in four directions (the model's
-- long side either way); a hit over BeamNG.Earth's terrain by more than ON_TOP_M is a roof or a wall, heights spread
-- over FOOT_STEP_M a slope. Such a spot is tried SHIFTS_M along the line, else left empty. Once each, when made.
M.FOOT_R = { vehicle = 2.7, canopy = 1.6 }
M.FOOT_STEP_M = { vehicle = 0.45, canopy = 0.6 }
M.ON_TOP_M = 0.6
M.SHIFTS_M = { 0, 3.5, -3.5, 7, -7 }
M.SURE_M = 300
M.REGROUND_S = 4.0          -- within SURE_M the ground under each one is measured again this often ...
M.REGROUND_PER = 40         -- ... at most this many each update ...
M.REGROUND_DZ = 0.3         -- ... and it is put back on it when it is this far off
M.PER_UPDATE = 10
M.WATCH_M = 140             -- spectators this near the car turn to watch it ...
M.TURN_DEG_S = 160          -- ... this fast
M.WATCH_MAX_DEG = 100       -- ... at most this far from facing the course
M.DEFAULT_HALF_M = 4.0      -- the track's half width while it is not known
M.PLAN_BACK_M, M.PLAN_AHEAD_M = 1500, 4000   -- the crowds planned around the car (made again as it moves on) ...
M.PLAN_SLACK_M = 1200                         -- ... once it is this far into the stretch past the last plan
M.REPLAN_S = 10             -- planned again for new spots / towns at most this often (a Lots plan takes a moment)

M.FANS = { 'fan_a', 'fan_b', 'fan_c', 'fan_d', 'fan_e', 'fan_f', 'fan_g', 'fan_h', 'fan_i', 'fan_j', 'fan_k', 'fan_l' }
M.CANOPIES = { 'canopy_red', 'canopy_blue', 'canopy_white' }
M.CHAIRS = { 'chair_blue', 'chair_green', 'chair_red' }
M.MODELS = { 'cooler', 'flag_checker', 'flag_orange', 'campfire', 'light_tower', 'flag_mexico', 'canopy_green',
             'fence_orange' }
-- the Lots lines (the user, 2026-10-25: photos of SCORE Baja races, "The closer to urban centers the larger the
-- crowd"): the course lined both sides, behind an orange safety fence, canopies behind the people and parked trucks
-- behind those, longer and denser the more urban the place (the companion says how urban: gpsd/urban.py)
M.STRIPS_SPARSE = { 'crowd_a', 'crowd_b', 'crowd_c', 'crowd_d' }     -- 2.5 m of people each (tools/make_crowds.py)
M.STRIPS_DENSE = { 'crowd_e', 'crowd_f', 'crowd_g', 'crowd_h' }
M.PEOPLE = { crowd_a = 2, crowd_b = 3, crowd_c = 4, crowd_d = 4, crowd_e = 6, crowd_f = 7, crowd_g = 8, crowd_h = 8 }
M.LINE_CANOPIES = { 'canopy_blue', 'canopy_blue', 'canopy_blue', 'canopy_white', 'canopy_white', 'canopy_green',
                    'canopy_red' }
M.VEHICLES = { 'pickup_white', 'pickup_silver', 'pickup_red', 'pickup_black', 'suv_white', 'suv_gray', 'suv_blue',
               'suv_maroon' }
M.LINE_M = { start = 70, finish = 70, checkpoint = 35, jump = 45, crossing = 35, hairpin = 35, danger = 25, line = 50 }
M.LINE_URBAN = 3.0          -- a line LINE_M long in open country, (1 + LINE_URBAN) times that in a town
M.FENCE_LAT, M.STRIP_LAT, M.CANOPY_LAT, M.VEHICLE_LAT = 2.2, 2.8, 6.0, 11.0   -- m past the track's edge
M.STRIP_M, M.FENCE_M, M.CANOPY_EVERY_M, M.VEHICLE_EVERY_M, M.FLAG_EVERY_M = 2.5, 5.0, 3.6, 3.0, 12.0
M.LINE_MIN_U = 0.3          -- Lots: a stretch with no jump, turn or crossing this urban gets a plain line
-- the fence only in town or along a really big crowd (the user, 2026-10-25: "the crowds should only have fences inside
-- urban zones or when the crowds are really large"); each 5 m piece laid from its two ends past the track's edge, so
-- pieces join along a gentle curve; on a sharp one (a corner in town: pieces crossed each other) it is left out
M.FENCE_MIN_U, M.FENCE_BIG_M = 0.5, 150
M.FENCE_STRETCH, M.FENCE_TURN_DEG = 0.2, 25
M.PER_UPDATE_LOTS = 40      -- (objects made per update on Lots: a line is a few hundred)
M.country = nil             -- (where the car is: Mexico's flags in Mexico)
for _, l in ipairs({ M.STRIPS_SPARSE, M.STRIPS_DENSE, M.VEHICLES }) do
  for _, n in ipairs(l) do M.MODELS[#M.MODELS + 1] = n end
end
M.GLOWING = { 'flames', 'lamps', 'lantern' }    -- (lit: their material glows)
for _, l in ipairs({ M.FANS, M.CANOPIES, M.CHAIRS }) do for _, n in ipairs(l) do M.MODELS[#M.MODELS + 1] = n end end
for _, n in ipairs(M.MODELS) do      -- (their materials made with the markers': markers.ensureMaterials)
  markers.MATERIALS['egps_' .. n] = { { 'colorMap', n .. '.png' }, { 'diffuseColor', '1 1 1 1' } }
end
-- (the fence's mesh: see-through where its picture is, in a game that cuts out by alpha)
markers.MATERIALS.egps_fence_orange = { { 'colorMap', 'fence_orange.png' }, { 'diffuseColor', '1 1 1 1' },
  { 'alphaTest', '1' }, { 'alphaRef', '80' } }
for _, n in ipairs(M.GLOWING) do
  markers.MATERIALS['egps_' .. n] = { { 'colorMap', n .. '.png' }, { 'diffuseColor', '1 1 1 1' }, { 'emissive', '1' },
                                      { 'glow', '1' }, { 'castShadows', '0' } }
  M.MODELS[#M.MODELS + 1] = n
end

-- kind -> { prio, sides (1 one side, 2 both), fans {min, max} a side, setback m past the edge, spread m along,
--          canopies, chairs, coolers, flag }
M.KINDS = {
  start = { prio = 100, sides = 2, fans = { 12, 18 }, setback = 4.0, spread = 22, canopies = 2, chairs = 3, coolers = 2,
            flag = 'flag_checker', min = 7.5 },
  finish = { prio = 100, sides = 2, fans = { 14, 20 }, setback = 4.0, spread = 26, canopies = 2, chairs = 3, coolers = 2,
             flag = 'flag_checker', min = 7.5 },
  checkpoint = { prio = 90, sides = 1, fans = { 5, 8 }, setback = 4.0, spread = 12, canopies = 1, chairs = 2,
                 coolers = 1, flag = 'flag_orange', other = { 2, 4 } },
  jump = { prio = 60, sides = 2, fans = { 5, 10 }, setback = 9.0, spread = 14, canopies = 1, chairs = 2, coolers = 1,
           along = 18 },
  danger = { prio = 50, sides = 1, fans = { 4, 8 }, setback = 11.0, spread = 12, canopies = 1, chairs = 1, coolers = 1 },
  crossing = { prio = 40, sides = 2, fans = { 4, 8 }, setback = 5.0, spread = 10, canopies = 0, chairs = 2, coolers = 1,
               along = 16 },
  hairpin = { prio = 30, sides = 1, fans = { 4, 9 }, setback = 8.0, spread = 12, canopies = 1, chairs = 2, coolers = 0 },
  line = { prio = 10, sides = 2, fans = { 2, 4 }, setback = 4.0, spread = 10, canopies = 0, chairs = 0, coolers = 0 },
}

-- -- a hash of the place (exact integer arithmetic: the same on every computer) -------------------------------------
local bit = rawget(_G, 'bit') or require('bit')
local TWO32 = 4294967296
local function mul32(a, b)                  -- (a * b) mod 2^32 of uint32s, exactly (no double rounding)
  local ah, al = math.floor(a / 65536), a % 65536
  return ((ah * b % 65536) * 65536 + al * b) % TWO32
end
local function u32(x) return x % TWO32 end
local function mix(x)
  x = u32(bit.bxor(x, bit.rshift(x, 16)) % TWO32)
  x = mul32(x, 0x45d9f3b)
  x = u32(bit.bxor(x, bit.rshift(x, 16)) % TWO32)
  x = mul32(x, 0x45d9f3b)
  x = u32(bit.bxor(x, bit.rshift(x, 16)) % TWO32)
  return x
end
-- [0, 1) from integers a, b and a salt
function M.hash(a, b, salt)
  local x = mix(u32(math.floor(a) + 0x9e3779b9))
  x = mix(u32(x + mul32(u32(math.floor(b) + 0x7f4a7c15), 0x27d4eb2d)))
  x = mix(u32(x + mul32(u32((salt or 0) + 0x632be5ab), 0x165667b1)))
  return x / TWO32
end

-- -- where the crowds are -----------------------------------------------------------------------------------------
-- Pure: the spots of a course: { {s, kind, side (+1 right, -1 left, 0 both), size} } sorted by s. waypoints (with s /
-- off), extra: the companion's { {s, kind = 'jump' | 'crossing', size} }, complete(binIndex) -> whether that stretch's
-- extra spots are all known (nil: always). Gates always; the others the best one per BIN_M, none near a gate. Lots:
-- urbanAt(s) -> 0..1 (how urban, nil: not known): a stretch with none of those, urban enough, gets a plain line.
function M.spots(e, waypoints, length, closed, extra, level, complete, win, urbanAt)
  level = level or M.level
  local out = {}
  if level == 'off' or not (e and e.n and e.n >= 2) then return out end
  length = length or e.length or 0
  local bin = M.BIN_M[level] or M.BIN_M.some
  -- win {a, b}: only the spots there (whole stretches: a and b on stretch edges, the turns looked for a little past)
  local wa, wb = 0, length
  if win then wa, wb = math.max(0, math.floor(win[1] / bin) * bin), math.min(length, math.ceil(win[2] / bin) * bin) end
  local gates = {}
  local started, finished = false, false
  for _, w in ipairs(waypoints or {}) do
    if w.s and (w.off or 0) <= markers.NEAR_LINE_M then
      local k = w.kind
      if k == 'start' then started = true end
      if k == 'finish' then finished = true end
      if (k == 'start' or k == 'checkpoint' or (k == 'finish' and not closed)) then
        gates[#gates + 1] = { s = w.s, kind = k, side = k == 'checkpoint' and 1 or 0, size = 1 }
      end
    end
  end
  if not started then table.insert(gates, 1, { s = math.min(60, length), kind = 'start', side = 0, size = 1 }) end
  if not finished and not closed then gates[#gates + 1] = { s = math.max(0, length - 60), kind = 'finish', side = 0,
    size = 1 } end
  local function nearGate(s)
    for _, g in ipairs(gates) do if math.abs(g.s - s) < M.GATE_CLEAR_M then return true end end
    return false
  end
  -- the other candidates
  local cands = {}
  for _, w in ipairs(waypoints or {}) do
    if w.kind == 'danger' and w.s and (w.off or 0) <= markers.NEAR_LINE_M then
      cands[#cands + 1] = { s = w.s, kind = 'danger', side = (M.hash(math.floor(w.s), 7, 1) < 0.5) and 1 or -1, size = 1 }
    end
  end
  for _, f in ipairs(extra or {}) do
    if (f.kind == 'jump' or f.kind == 'crossing') and type(f.s) == 'number' then
      cands[#cands + 1] = { s = f.s, kind = f.kind, side = 0, size = tonumber(f.size) or 0.5 }
    end
  end
  local c0 = math.max(0, wa - 300)
  local ok, corners = pcall(poly.corners, e, c0, math.min(length, wb + 300) - c0)
  for _, c in ipairs(ok and corners or {}) do
    if c.angle >= M.HAIRPIN_DEG and c.s0 then
      local s = (c.s0 + (c.s1 or c.s0)) / 2
      cands[#cands + 1] = { s = s, kind = 'hairpin', side = c.dir == 'right' and 1 or -1, size = 1 }   -- (inside)
    end
  end
  -- the best of each stretch
  local best = {}
  for _, c in ipairs(cands) do
    if c.s >= 0 and c.s <= length and not nearGate(c.s) then
      local b = math.floor(c.s / bin)
      if not complete or complete(b) then
        local h = M.hash(math.floor(c.s * 10 + 0.5), b, 3)
        local cur = best[b]
        local p = M.KINDS[c.kind].prio
        if not cur or p > cur.p or (p == cur.p and h < cur.h) then best[b] = { c = c, p = p, h = h } end
      end
    end
  end
  -- Lots, near towns: people line the course even where nothing happens (a plain line), every stretch urban enough
  if level == 'lots' and urbanAt then
    for b = math.floor(wa / bin), math.ceil(wb / bin) - 1 do
      if not best[b] and (not complete or complete(b)) then
        local s = (b + 0.25 + 0.5 * M.hash(b, 17, 5)) * bin
        local u = urbanAt(s)
        if s > 0 and s < length and u and u >= M.LINE_MIN_U and not nearGate(s) then
          best[b] = { c = { s = math.floor(s * 10 + 0.5) / 10, kind = 'line', side = 0, size = u }, p = 0, h = 0 }
        end
      end
    end
  end
  for _, g in ipairs(gates) do if g.s >= wa - 1 and g.s <= wb + 1 then out[#out + 1] = g end end
  for b, v in pairs(best) do if b * bin >= wa - 1 and b * bin < wb then out[#out + 1] = v.c end end
  table.sort(out, function(a, b) return a.s < b.s end)
  return out
end

-- Pure: whether [a, b] of the course lies inside the ranges { {a, b} ... } the companion has answered for.
function M.covered(ranges, a, b)
  for _, r in ipairs(ranges or {}) do
    if r[1] <= a and r[2] >= b then return true end
  end
  return false
end

-- Pure: ranges { {a, b} } with [a, b] added, overlapping ones merged.
function M.addRange(ranges, a, b)
  local out = {}
  table.insert(ranges, { a, b })
  table.sort(ranges, function(p, q) return p[1] < q[1] end)
  for _, r in ipairs(ranges) do
    local last = out[#out]
    if last and r[1] <= last[2] then
      if r[2] > last[2] then last[2] = r[2] end
    else
      out[#out + 1] = { r[1], r[2] }
    end
  end
  return out
end

-- The companion's course_sides answer m: its spots (jumps, crossings) added to the course's, the stretch it covered
-- noted; crs.spotsVersion moves on when anything changed (the crowds planned again).
function M.merge(crs, m)
  -- how urban the stretch is (the Lots lines): kept every urbStep m, the stretches known noted; 'pending' (the towns
  -- still being fetched): nothing yet
  local urbChanged = false
  if m.urbState ~= nil then crs.urbanOn = true end
  if type(m.urb) == 'table' and tonumber(m.urbStep) and tonumber(m.urbK0) and #m.urb > 0 then
    local step, k0 = tonumber(m.urbStep), tonumber(m.urbK0)
    crs.urban = (crs.urban and crs.urban.step == step) and crs.urban or { step = step, v = {} }
    for j, v in ipairs(m.urb) do
      local k = k0 + j - 1
      if tonumber(v) and crs.urban.v[k] ~= tonumber(v) then crs.urban.v[k], urbChanged = tonumber(v), true end
    end
    local before = crs.urbRanges and #crs.urbRanges or 0
    crs.urbRanges = M.addRange(crs.urbRanges or {}, k0 * step - step / 2, (k0 + #m.urb - 1) * step + step / 2)
    if #crs.urbRanges ~= before then urbChanged = true end
  end
  if urbChanged then crs.spotsVersion = (crs.spotsVersion or 0) + 1 end
  if type(m.spots) ~= 'table' or not tonumber(m.spotsFrom) or not tonumber(m.spotsTo) then return urbChanged end
  crs.spots, crs.spotKeys = crs.spots or {}, crs.spotKeys or {}
  local changed = false
  for _, f in ipairs(m.spots) do
    local k = tostring(f.kind) .. '@' .. tostring(f.s)
    if type(f.s) == 'number' and not crs.spotKeys[k] then
      crs.spotKeys[k] = true
      crs.spots[#crs.spots + 1] = { s = f.s, kind = f.kind, size = f.size }
      changed = true
    end
  end
  local old = crs.spotRanges or {}
  local was = #old > 0 and (#old .. ':' .. old[1][1] .. ':' .. old[#old][2]) or ''
  crs.spotRanges = M.addRange(old, tonumber(m.spotsFrom), tonumber(m.spotsTo))
  local r = crs.spotRanges
  local now = #r .. ':' .. r[1][1] .. ':' .. r[#r][2]
  if changed or now ~= was then crs.spotsVersion = (crs.spotsVersion or 0) + 1; return true end
  return urbChanged
end

-- Pure: the objects of one spot: { {key, model, s, side, lat (m past the edge), along (m), turn (rad, from facing the
-- course), fan (bool)} }. sc: the crowd size scale (Some 1, Lots 1.7).
function M.group(spot, sc)
  sc = sc or 1
  local K = M.KINDS[spot.kind]
  local out = {}
  local base = math.floor(spot.s * 10 + 0.5)
  local n0 = 0
  local function put(model, side, lat, along, turn, fan, night, light)
    n0 = n0 + 1
    out[#out + 1] = { key = spot.kind .. ':' .. base .. ':' .. n0, model = model, s = spot.s + along, side = side,
                      lat = lat, along = along, turn = turn or 0, fan = fan, night = night, light = light }
  end
  local canopyAt = {}
  local sides = {}
  if K.sides == 2 or spot.side == 0 then sides = { 1, -1 } else sides = { spot.side } end
  if spot.kind == 'checkpoint' then sides = { 1, -1 } end
  local size = 0.6 + 0.8 * (spot.size or 0.5)
  for si, side in ipairs(sides) do
    local salt = 100 * si
    local lo, hi = K.fans[1], K.fans[2]
    if spot.kind == 'checkpoint' and side == -1 then lo, hi = K.other[1], K.other[2] end
    if spot.kind == 'jump' then lo, hi = lo * size, hi * size end
    local n = math.floor((lo + (hi - lo) * M.hash(base, si, 1)) * sc + 0.5)
    local centre = (K.along or 0) * (M.hash(base, si, 2) < 0.5 and 1 or -1)    -- (a crossing: either side of its road)
    if spot.kind == 'jump' then centre = K.along end      -- (the landing: past the kicker)
    local spread = K.spread * math.min(1.6, 0.7 + n / 14)
    -- people stand in little groups (friends, a camp), 2-5 each, a couple of metres apart within one
    local nc = math.max(1, math.ceil(n / 3.5))
    local centres = {}
    for c = 1, nc do
      local t = nc == 1 and 0.5 or (c - 1) / (nc - 1)
      centres[c] = (t - 0.5) * 2 * spread + (M.hash(base, salt + c, 20) - 0.5) * spread / nc
    end
    for i = 1, n do
      local c = 1 + (i - 1) % nc
      local u = centres[c] + (M.hash(base, salt + i, 3) - 0.5) * 3.2
      local row = math.floor(M.hash(base, salt + i, 4) * (n > 8 and 3 or 2))
      local lat = K.setback + row * 1.1 + M.hash(base, salt + i, 5) * 0.9
      local fan = M.FANS[1 + math.floor(M.hash(base, salt + i, 6) * #M.FANS) % #M.FANS]
      put(fan, side, lat, centre + u, (M.hash(base, salt + i, 7) - 0.5) * 0.7, true)
    end
    local canopies = K.canopies
    if spot.kind ~= 'start' and spot.kind ~= 'finish' and spot.kind ~= 'checkpoint' then
      canopies = (M.hash(base, si, 8) < 0.6) and canopies or 0
    end
    if spot.kind == 'checkpoint' and side == -1 then canopies = 0 end
    for i = 1, canopies do
      local u = centre + centres[1 + (i - 1) % nc] + (M.hash(base, salt + i, 9) - 0.5) * 2
      local col = M.CANOPIES[1 + math.floor(M.hash(base, salt + i, 10) * #M.CANOPIES) % #M.CANOPIES]
      put(col, side, K.setback + 5.5, u, (M.hash(base, salt + i, 11) - 0.5) * 0.3)
      canopyAt[#canopyAt + 1] = { side, u, (M.hash(base, salt + i, 11) - 0.5) * 0.3 }
    end
    local chairs = (spot.kind == 'checkpoint' and side == -1) and 0 or K.chairs
    for i = 1, chairs do
      local u = centre + centres[1 + (i - 1) % nc] + (M.hash(base, salt + i, 12) - 0.5) * 3
      local col = M.CHAIRS[1 + math.floor(M.hash(base, salt + i, 13) * #M.CHAIRS) % #M.CHAIRS]
      put(col, side, K.setback + 3.2 + M.hash(base, salt + i, 14) * 2.5, u, (M.hash(base, salt + i, 15) - 0.5) * 1.2)
    end
    local coolers = (spot.kind == 'checkpoint' and side == -1) and 0 or K.coolers
    for i = 1, coolers do
      put('cooler', side, K.setback + 4.2, centre + centres[1 + (i - 1) % nc] + (M.hash(base, salt + i, 16) - 0.5) * 3,
          (M.hash(base, salt + i, 17) - 0.5) * 2)
    end
    if K.flag and (side == 1 or spot.kind == 'start' or spot.kind == 'finish') then
      put(K.flag, side, (K.min or K.setback) + 0.5, centre - spread - 2, 0)
    end
    -- after dark (the user, 2026-10-25: "add some lights to the spectators"): a lantern under every canopy, a light
    -- tower at the gates (both sides of the start and finish, the crew's side of a checkpoint), a campfire behind
    -- the other crowds (the same place as the canopy's or the tower's own: placeOf moves them alike)
    for _, c in ipairs(canopyAt) do
      if c[1] == side then put('lantern', side, K.setback + 5.5, c[2], c[3], false, true, 'lantern') end
    end
    local gate = spot.kind == 'start' or spot.kind == 'finish' or spot.kind == 'checkpoint'
    if gate and (side == 1 or spot.kind ~= 'checkpoint') then
      local u = centre + (spread + 5) * side
      put('light_tower', side, K.setback + 7.5, u, 0)
      put('lamps', side, K.setback + 7.5, u, 0, false, true, 'tower')
    elseif not gate or side == -1 then
      local u = centre + (nc > 1 and centres[nc] or 4) + (M.hash(base, salt, 30) - 0.5) * 2
      local turn = M.hash(base, salt, 31) * 6.28
      put('campfire', side, K.setback + 7.0, u, turn, false, true)
      put('flames', side, K.setback + 7.0, u, turn, false, true, 'fire')
    end
  end
  return out
end

-- Pure: the Lots line of a spot, u (0..1) urban there: { objects as group's } (fence, people strips, canopies with
-- their lanterns at night, parked vehicles, flags; light towers at a gate's ends). skip[side] = { along ... }: where
-- group's own spectators stand at the fence (they turn to watch: the line leaves them room).
function M.line(spot, u, skip)
  u = math.max(0, math.min(1, u or 0))
  local out = {}
  local base = math.floor(spot.s * 10 + 0.5)
  local n0 = 0
  local function put(model, side, lat, along, turn, people, night, light)
    n0 = n0 + 1
    out[#out + 1] = { key = spot.kind .. ':' .. base .. ':L' .. n0, model = model, s = spot.s + along, side = side,
                      lat = lat, along = along, turn = turn or 0, people = people, night = night, light = light,
                      line = true }
  end
  local K = M.KINDS[spot.kind] or {}
  local sides = { 1, -1 }
  if (K.sides or 2) == 1 and spot.side ~= 0 then sides = { spot.side } end
  local L = (M.LINE_M[spot.kind] or 30) * (1 + M.LINE_URBAN * u)
  local gate = spot.kind == 'start' or spot.kind == 'finish' or spot.kind == 'checkpoint'
  local mexico = M.country and tostring(M.country):lower():find('mexic') ~= nil
  for si, side in ipairs(sides) do
    local c = spot.kind == 'jump' and (K.along or 0) or 0
    local a0 = c - L / 2
    local h = function(k, salt) return M.hash(base, si * 4096 + k, salt) end
    -- the fence: in town, or along a really big crowd
    if u >= M.FENCE_MIN_U or L >= M.FENCE_BIG_M then
      for k = 0, math.floor(L / M.FENCE_M) - 1 do
        put('fence_orange', side, M.FENCE_LAT, a0 + (k + 0.5) * M.FENCE_M, 0)
        out[#out].fence = true
      end
    end
    -- the people, 2.5 m at a time: more of them, more packed, the more urban
    local occ, dense = 0.55 + 0.45 * u, 0.2 + 0.7 * u
    for k = 0, math.floor(L / M.STRIP_M) - 1 do
      local x = a0 + (k + 0.5) * M.STRIP_M
      local free = true
      for _, sx in ipairs(skip and skip[side] or {}) do if math.abs(sx - x) < 1.3 then free = false end end
      if free and h(k, 40) < occ then
        local list = h(k, 41) < dense and M.STRIPS_DENSE or M.STRIPS_SPARSE
        local m = list[1 + math.floor(h(k, 42) * #list) % #list]
        put(m, side, M.STRIP_LAT, x + (h(k, 43) - 0.5) * 0.4, (h(k, 44) - 0.5) * 0.15, M.PEOPLE[m])
      end
    end
    -- canopies behind them (a lantern under most at night), parked trucks behind those
    for k = 0, math.floor(L / M.CANOPY_EVERY_M) - 1 do
      if h(k, 50) < 0.2 + 0.6 * u then
        local x = a0 + (k + 0.5) * M.CANOPY_EVERY_M
        local m = M.LINE_CANOPIES[1 + math.floor(h(k, 51) * #M.LINE_CANOPIES) % #M.LINE_CANOPIES]
        local turn = (h(k, 52) - 0.5) * 0.2
        put(m, side, M.CANOPY_LAT, x, turn)
        if h(k, 53) < 0.6 then put('lantern', side, M.CANOPY_LAT, x, turn, nil, true, 'lantern') end
      end
    end
    for k = 0, math.floor(L / M.VEHICLE_EVERY_M) - 1 do
      if h(k, 60) < 0.1 + 0.6 * u then
        local m = M.VEHICLES[1 + math.floor(h(k, 61) * #M.VEHICLES) % #M.VEHICLES]
        put(m, side, M.VEHICLE_LAT + (h(k, 62) - 0.5) * 1.5, a0 + (k + 0.5) * M.VEHICLE_EVERY_M, (h(k, 63) - 0.5) * 0.35)
      end
    end
    -- flags waved in the crowd
    for k = 0, math.floor(L / M.FLAG_EVERY_M) - 1 do
      if h(k, 70) < 0.12 + 0.2 * u then
        put(mexico and 'flag_mexico' or 'flag_orange', side, M.STRIP_LAT + 1.6, a0 + (k + 0.5) * M.FLAG_EVERY_M, 0)
      end
    end
    -- a gate's ends: light towers
    if gate then
      for _, x in ipairs({ a0 - 3, a0 + L + 3 }) do
        put('light_tower', side, M.STRIP_LAT + 1.0, x, 0)
        put('lamps', side, M.STRIP_LAT + 1.0, x, 0, nil, true, 'tower')
      end
    end
  end
  return out
end

-- Pure: objs (a spot's) slid along the course, all together, so none stands before its start or past its end.
function M.fitOn(objs, length)
  local lo, hi = math.huge, -math.huge
  for _, o in ipairs(objs) do lo, hi = math.min(lo, o.s), math.max(hi, o.s) end
  if lo == math.huge then return objs end
  local d = 0
  if lo < 0 then d = -lo end
  if hi + d > length then d = math.max(-lo, length - hi) end   -- (a course shorter than the crowd: from its start)
  if d ~= 0 then for _, o in ipairs(objs) do o.s, o.along = o.s + d, o.along + d end end
  return objs
end

M.TURN_LOOK_M = 6           -- the course's turn measured this far either side of a line object
-- Pure: is line object o on the inside of a turn too tight for it (its neighbours would overlap it)?
function M.insideTurn(e, length, o)
  local s = math.max(0, math.min(length, o.s))
  local _, _, ax, ay = poly.at(e, math.max(0, s - M.TURN_LOOK_M))
  local _, _, bx, by = poly.at(e, math.min(length, s + M.TURN_LOOK_M))
  local cross = ax * by - ay * bx                       -- > 0: turning left
  local ang = math.atan2(math.abs(cross), ax * bx + ay * by)
  if ang < 0.05 then return false end
  local inside = (cross > 0 and o.side == -1) or (cross < 0 and o.side == 1)
  if not inside then return false end
  local radius = 2 * M.TURN_LOOK_M / ang
  return radius < o.lat + M.DEFAULT_HALF_M + 8
end

-- Clear of the course: nobody stands on any pass of it, not only the stretch they face (the user, 2026-10-25: "the
-- spectators are blocking the route on some instances": a hairpin's inside is its other leg; a course comes back
-- past itself). CLEAR_M: how far past the track's edge each kind of thing keeps (its own size, and room).
-- (1.6.2, the user 2026-10-28: crowds too close "block the road and confuses the drivers as to where the track is":
-- people a clear 3 m back from the track's edge, canopies and parked trucks further)
M.CLEAR_M = { fan = 3.0, chair = 3.0, cooler = 3.0, flag = 2.5, canopy = 5.0, lantern = 5.0, light_tower = 4.0,
              lamps = 4.0, campfire = 4.0, flames = 4.0, crowd = 3.0, fence = 1.5, pickup = 4.5, suv = 4.5 }   -- (a lantern as its canopy, ... : moved alike)
M.PUSH_STEP_M, M.PUSH_MAX_M = 2.0, 30.0     -- a blocked place: moved back from the course this far at most, else left out

local function clearNeed(model)
  local m = tostring(model or '')
  for k, v in pairs(M.CLEAR_M) do if m:sub(1, #k) == k then return v end end
  return 2.0
end

local function halfAt(sides, s) return markers.halfAt(sides, s, M.DEFAULT_HALF_M) end

-- Pure: is the track's width at s still to come? The companion says where its track is (sides: course_sides) and
-- has said it for some of the course, not yet here: nothing is made here until it has (made on the course's line
-- with a guessed width, a canopy stood on a track that rounds a bend inside it or follows a road beside the line).
-- No sides at all (no painted course): never waited for.
function M.sidesPending(sides, s)
  if not (sides and sides.step and sides.hw and next(sides.hw) ~= nil) then return false end
  local i = math.floor((s or 0) / sides.step + 0.5)
  return type(sides.hw[i]) ~= 'number' or type(sides.ctr and sides.ctr[i]) ~= 'number'
end

-- Pure: is (x, y) clear of the course for model (CLEAR_M past the edge of every pass of it near)?
function M.clearFor(e, x, y, sides, model)
  if not e then return true end
  return M.clearance(e, x, y, sides) >= clearNeed(model)
end

-- Pure: how far (x, y) is past the track's edge, of the nearest pass of the course (markers.clearance's).
function M.clearance(e, x, y, sides, r) return markers.clearance(e, x, y, sides, M.DEFAULT_HALF_M, r) end

-- Pure: where object o stands (x, y) and the yaw that faces it to the course (its model faces -y); nil when there is
-- no room for it clear of the course (a tight hairpin's inside, between two passes). sides: the companion's track
-- widths (markers.placeFor's: step, hw, ctr), nil: not known.
function M.placeOf(e, length, o, sides)
  if o.fence then return M.fenceAt(e, length, o, sides) end
  local s = math.max(0, math.min(length or e.length or 0, o.s))
  local x, y, dx, dy = poly.at(e, s)
  local hw, ctr = halfAt(sides, s)
  local K = M.KINDS[o.kind or ''] or {}
  local off = hw + o.lat
  if K.min and off < K.min and not o.line then off = K.min end
  local need = clearNeed(o.model)
  -- facing the course: toward its middle at this s (the right normal is (dy, -dx))
  local fx, fy = -dy * o.side, dx * o.side
  local yaw = markers.faceYaw(-fx, -fy) + (o.turn or 0)
  local push = 0
  while push <= M.PUSH_MAX_M do
    local lat = -ctr + o.side * (off + push)
    local px, py = x + dy * lat, y - dx * lat
    if M.clearance(e, px, py, sides) >= need then return px, py, yaw end
    push = push + M.PUSH_STEP_M
  end
  return nil
end

-- Pure: where a fence piece stands (x, y, yaw), laid from its two ends (FENCE_M apart along the course, each o.lat past
-- the track's edge there): along the course's curve, nil where that is too sharp for a straight piece (it would be
-- stretched or squeezed more than FENCE_STRETCH, or turned more than FENCE_TURN_DEG from the course) or where an end
-- or its middle would stand on the course.
function M.fenceAt(e, length, o, sides)
  length = length or e.length or 0
  local half = M.FENCE_M / 2
  if o.s - half < 0 or o.s + half > length then return nil end
  local function edge(s)
    local x, y, dx, dy = poly.at(e, s)
    local hw, ctr = halfAt(sides, s)
    local lat = -ctr + o.side * (hw + o.lat)
    return x + dy * lat, y - dx * lat
  end
  local ax, ay = edge(o.s - half)
  local bx, by = edge(o.s + half)
  local cx, cy = bx - ax, by - ay
  local L = math.sqrt(cx * cx + cy * cy)
  if L < M.FENCE_M * (1 - M.FENCE_STRETCH) or L > M.FENCE_M * (1 + M.FENCE_STRETCH) then return nil end
  local _, _, tdx, tdy = poly.at(e, o.s)
  if (cx * tdx + cy * tdy) / L < math.cos(math.rad(M.FENCE_TURN_DEG)) then return nil end
  local mx, my = (ax + bx) / 2, (ay + by) / 2
  local need = clearNeed(o.model)
  if M.clearance(e, ax, ay, sides) < need or M.clearance(e, bx, by, sides) < need
      or M.clearance(e, mx, my, sides) < need then return nil end
  local ux, uy = cx / L, cy / L
  local fx, fy = -uy * o.side, ux * o.side          -- (facing the course, as placeOf: the piece's own way along it)
  return mx, my, markers.faceYaw(-fx, -fy) + (o.turn or 0)
end

-- -- after dark ------------------------------------------------------------------------------------------------------
-- (the user, 2026-10-25: "add some lights to the spectators to make it more immersive at night") Once the sun is down
-- where the car is, the campfires, the lanterns under the canopies and the light towers' lamps come out, and the
-- nearest of them light the ground for real (PointLights, no shadows: a handful near the car, the cost of a few car
-- lamps). Settings, Night lights: On / Bright / Off.
M.lights = 'on'
M.LIGHT_M = 400             -- lights lit within this of the car ...
M.MAX_LIGHTS = 16           -- ... the nearest this many at most
M.NIGHT_ON_DEG, M.NIGHT_OFF_DEG = 1.0, 3.0    -- lit once the sun is lower than this (degrees up), out again above that
M.BRIGHT = 2.5              -- Bright: this much more light
M.FLICKER_M, M.FLICKER_HZ = 150, 12            -- campfires this near flicker, this often
-- kind -> the light's height over the object's feet, forward (m, toward the course), reach (m), colour, lumens (and
-- the older brightness for games before physical light units)
M.LIGHTS = {
  lantern = { h = 2.0, fwd = 0, radius = 9, color = '1 0.8 0.55 1', lm = 800, brightness = 1.0 },
  tower = { h = 6.4, fwd = 1.5, radius = 40, color = '0.92 0.95 1 1', lm = 20000, brightness = 3.0 },
  fire = { h = 0.6, fwd = 0, radius = 12, color = '1 0.52 0.18 1', lm = 1600, brightness = 1.5, flicker = true },
}
M.isNight = false
M.sun = nil

function M.setLights(v)
  if v ~= 'off' and v ~= 'bright' then v = 'on' end
  M.lights = v
  return v
end

local CUM_DAYS = { 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334 }
-- Pure: the sun's height (degrees above the horizon) for the game's time of day tod (TimeOfDay's fields: time 0 noon,
-- 0.5 midnight, the local clock; year / month / day; utcOffset (h), latitude / longitude where BeamNG.Earth sets them),
-- at lat / lon (the car's) when tod has no place.
function M.sunElevation(tod, lat, lon)
  local h = ((tonumber(tod.time) or 0) + 0.5) % 1 * 24
  local tlat, tlon = tonumber(tod.latitude), tonumber(tod.longitude)
  if tlat and tlon and (tlat ~= 0 or tlon ~= 0) then lat, lon = tlat, tlon end
  lat = tonumber(lat) or 0
  local solar = h                       -- (a level without a place: its clock is the sun's)
  local off = tonumber(tod.utcOffset)
  if off and tonumber(lon) then solar = (h - off + lon / 15) % 24 end
  local month, day = tonumber(tod.month), tonumber(tod.day)
  local doy = (month and day and CUM_DAYS[month]) and (CUM_DAYS[month] + day) or 80
  local decl = math.rad(23.44) * math.sin(2 * math.pi * (284 + doy) / 365)
  local ha = math.rad(15 * (solar - 12))
  local la = math.rad(lat)
  local s = math.sin(la) * math.sin(decl) + math.cos(la) * math.cos(decl) * math.cos(ha)
  return math.deg(math.asin(math.max(-1, math.min(1, s))))
end

-- Whether it is dark where the car is (the game's own time of day), with a little hysteresis.
function M.nightNow(car)
  local env = rawget(_G, 'core_environment')
  local ok, tod = pcall(function() return env and env.getTimeOfDay and env.getTimeOfDay() end)
  if not ok or type(tod) ~= 'table' or tod.time == nil then M.sun = nil; M.isNight = false; return false end
  local el = M.sunElevation(tod, car and car.lat, car and car.lon)
  M.sun = el
  if M.isNight then M.isNight = el < M.NIGHT_OFF_DEG else M.isNight = el < M.NIGHT_ON_DEG end
  return M.isNight
end

-- -- in the world ---------------------------------------------------------------------------------------------------
local live = {}             -- key -> { id, x, y, z, yaw, base, fan, sure, light (its PointLight's id), lightKind }
local nowhere = {}          -- key -> true: no room for it where it was planned (a roof, a wall, a slope: spotFor)
local nLive = 0
local nLights = 0
local planned = { course = nil, anchor = nil, level = nil, list = {}, spotsV = nil, sidesV = nil, cheers = {} }
local serial = 0
local shapeOf = {}
local roadsV = nil
local osm = { idx = nil, tv = nil, anchor = nil, x = nil, y = nil }
M.OSM_R, M.OSM_MOVED_M = 900, 300

-- OpenStreetMap's ways around the car (tracks and dirt roads the game's road map leaves out) as a road index, built
-- again when the street tiles change, the world moves or the car went OSM_MOVED_M.
local function osmRoads(anchor, car)
  local tv = streetmap.tilesVersion()
  if osm.idx and osm.tv == tv and osm.anchor == anchor and
      (car.x - osm.x) ^ 2 + (car.y - osm.y) ^ 2 < M.OSM_MOVED_M * M.OSM_MOVED_M then
    return osm.idx
  end
  local ways = streetmap.waysNear(anchor, car.x, car.y, M.OSM_R)
  local idx = #ways > 0 and roadsnear.fromWays(ways) or nil
  if idx then osm.n = (osm.n or 0) + 1; idx.version = 'osm' .. osm.n end
  osm.idx, osm.tv, osm.anchor, osm.x, osm.y = idx, tv, anchor, car.x, car.y
  return idx
end

-- Does object o (placed: x, y, yaw) stand on a road of the game's road map idx? One on a road steps back from the
-- course (ROAD_STEP_M at a time, ROAD_PUSH_M at most: past the edge of a street the course runs along, its width
-- not known yet); still on one (a side street across the line: stepping back goes down it) it is left out. Worked
-- out once per road map, from where the course put it.
M.ROAD_STEP_M, M.ROAD_PUSH_M = 1.0, 12.0
function M.onRoad(idx, o)
  if not idx or not o.x then return false end
  if o.roadV == idx.version then return o.roadHit end
  o.roadV = idx.version
  if not o.px then o.px, o.py = o.x, o.y end
  local fx, fy = math.sin(o.yaw or 0), -math.cos(o.yaw or 0)         -- (its front: toward the course)
  local p = 0
  while p <= M.ROAD_PUSH_M + 1e-9 do
    local x, y = o.px - fx * p, o.py - fy * p
    if not roadsnear.blocked(idx, o.model, x, y, o.yaw) then
      o.x, o.y, o.roadHit = x, y, false
      return false
    end
    p = p + M.ROAD_STEP_M
  end
  o.roadHit = true
  return true
end
M.failed = nil
M.lightError = nil

local function lightPos(l, spec)
  -- (forward: the model's front, -y turned by its yaw: (sin yaw, -cos yaw))
  return l.x + spec.fwd * math.sin(l.base or 0), l.y - spec.fwd * math.cos(l.base or 0), l.z + spec.h
end

local function dropLight(l)
  if not l.light then return end
  local o = scenetree.findObjectById(l.light)
  if o then pcall(function() o:delete() end) end
  l.light, l.lightKind = nil, nil
  nLights = nLights - 1
end

local function makeLight(kind, l)
  local spec = M.LIGHTS[kind]
  if not spec or not rawget(_G, 'createObject') then return end
  local sc = M.lights == 'bright' and M.BRIGHT or 1
  local ok, id = pcall(function()
    local o = createObject('PointLight')
    o:setField('radius', 0, tostring(spec.radius * (sc > 1 and 1.3 or 1)))
    o:setField('color', 0, spec.color)
    o:setField('brightness', 0, tostring(spec.brightness * sc))
    o:setField('intensity', 0, tostring(spec.lm * sc))
    o:setField('intensityUnit', 0, 'lm')
    o:setField('castShadows', 0, '0')
    o:setField('isEnabled', 0, '1')
    local x, y, z = lightPos(l, spec)
    o:setPosition(vec3(x, y, z))
    o.canSave = false
    serial = serial + 1
    o:registerObject('egpsCrowdLight_' .. serial)
    scenetree.MissionGroup:addObject(o)
    return o:getID()
  end)
  if not ok then M.lightError = tostring(id); return end
  l.light, l.lightKind, l.lightScale = id, kind, sc
  l.ph = M.hash(math.floor(l.x * 10), math.floor(l.y * 10), 9) * 6.283
  nLights = nLights + 1
end

local function remove(key)
  local l = live[key]
  live[key] = nil
  nLive = nLive - 1
  if l then dropLight(l) end
  local o = l and scenetree.findObjectById(l.id)
  if o then pcall(function() o:delete() end) end
end

function M.clear()
  nowhere = {}
  for key in pairs(live) do remove(key) end
  live, nLive, nLights = {}, 0, 0
end

function M.setLevel(v)
  if v ~= 'off' and v ~= 'lots' then v = 'some' end
  M.level = v
  return v
end

-- Pure: what a footprint's ground says. hits: the rays' heights (middle first; nil where a ray found nothing yet),
-- terr: the terrain's heights under them (nil where unknown). -> 'ok', z (sunk a little into the low side, never
-- floating far) | 'wait' (the ground not there yet) | 'no', why ('structure' | 'slope').
function M.footprint(hits, terr, step)
  local lo, hi = math.huge, -math.huge
  for i = 1, #hits do
    local h = hits[i]
    if h == nil then return 'wait' end
    local t = terr and terr[i]
    if t and h - t > M.ON_TOP_M and h - t < 200 then return 'no', 'structure' end
    if h < lo then lo = h end
    if h > hi then hi = h end
  end
  if #hits == 0 then return 'wait' end
  if hi - lo > step then return 'no', 'slope' end
  return 'ok', lo + 0.4 * (hi - lo)
end

-- Which kind of footprint a model needs checked (nil: none).
local isVehicle = {}
for _, n in ipairs(M.VEHICLES) do isVehicle[n] = true end
function M.footKind(model)
  if isVehicle[model] then return 'vehicle' end
  if type(model) == 'string' and model:match('^canopy_') then return 'canopy' end
  return nil
end

local function terrainZ(x, y)
  local ct = rawget(_G, 'core_terrain')
  if not (ct and ct.getTerrainHeight) then return nil end
  local ok, h = pcall(ct.getTerrainHeight, vec3(x, y, 0))
  if ok and type(h) == 'number' then return h end
  return nil
end

-- The ground for o at (x, y): M.footprint's answer for its footprint kind.
local function footGround(kind, x, y, yaw, zHint)
  local r = M.FOOT_R[kind]
  local pts = { { x, y } }
  for k = 0, 3 do
    local a = (yaw or 0) + k * math.pi / 2
    pts[#pts + 1] = { x + r * math.cos(a), y + r * math.sin(a) }
  end
  local hits, terr = {}, {}
  for i, p in ipairs(pts) do
    hits[i] = markers.groundZ(p[1], p[2], zHint)
    terr[i] = terrainZ(p[1], p[2])
    if hits[i] == nil then return 'wait' end
  end
  return M.footprint(hits, terr, M.FOOT_STEP_M[kind])
end

-- Where o can stand: x, y, z | nil (wait) | false (nowhere: left empty). Along the line by SHIFTS_M (its yaw).
-- clear(x, y): is that clear of the course (nil: not checked)? (1.7.8, the user 2026-11-09, a canopy and a van on a
-- forest stage's road: a truck shifted along its line for level ground goes straight on, and on the inside of a bend
-- straight on is toward the track; a step back off a street can be toward another pass of the course)
local function spotFor(o, zHint, clear)
  local kind = M.footKind(o.model)
  if not kind then
    if clear and not clear(o.x, o.y) then return false end
    local z = markers.groundZ(o.x, o.y, zHint)
    if z then return o.x, o.y, z end
    return nil
  end
  local waiting = false
  for _, d in ipairs(M.SHIFTS_M) do
    local x, y = o.x + d * math.cos(o.yaw or 0), o.y + d * math.sin(o.yaw or 0)
    local verdict, z = 'no', nil
    if not clear or clear(x, y) then verdict, z = footGround(kind, x, y, o.yaw, zHint) end
    if verdict == 'ok' then return x, y, z end
    if verdict == 'wait' then waiting = true end
  end
  if waiting then return nil end
  return false
end

local function make(m, z, x, y)
  serial = serial + 1
  for _, shape in ipairs(shapeOf[m.model] and { shapeOf[m.model] } or markers.candidates(m.model)) do
    local id = markers.make(shape, x or m.x, y or m.y, z, m.yaw, 'egpsCrowd_' .. serial)
    if id then shapeOf[m.model] = shape; return id end
  end
  error('no model for ' .. tostring(m.model))
end

-- Pure: where a crowd cheers from (crowdsound.lua): the middle of its people, how many, a gate's or not.
function M.cheerOf(spot, objs)
  local sx, sy, n = 0, 0, 0
  for _, o in ipairs(objs) do
    local k = o.people or (o.fan and 1) or 0
    if k > 0 and o.x then sx, sy, n = sx + o.x * k, sy + o.y * k, n + k end
  end
  if n == 0 then return nil end
  return { key = spot.kind .. ':' .. math.floor(spot.s * 10 + 0.5), x = sx / n, y = sy / n, n = n, kind = spot.kind,
           gate = spot.kind == 'start' or spot.kind == 'finish' or spot.kind == 'checkpoint' }
end

-- The objects planned for the course, placed in the anchor's frame (again when the track's widths come in).
local function plan(crs, anchor)
  local e = crs.e and crs.e.anchor == anchor and crs.e or nil
  local list, cheers = {}, {}
  if e then
    local bin = M.BIN_M[M.level] or M.BIN_M.some
    local complete = nil
    if crs.spotRanges then        -- (the companion says where the jumps are: a stretch once all of it is known)
      complete = function(b) return M.covered(crs.spotRanges, b * bin, (b + 1) * bin) end
    end
    local sc = M.SCALE[M.level] or 1
    local win = nil
    if crs.s then win = { crs.s - M.PLAN_BACK_M, crs.s + M.PLAN_AHEAD_M } end
    planned.window = win
    local lots = M.level == 'lots'
    -- how urban (the companion's, every urban.step m along the course: the Lots lines' length and density)
    local urbanAt = nil
    if crs.urban then
      urbanAt = function(s) return crs.urban.v[math.floor(s / crs.urban.step + 0.5)] end
    end
    if lots and crs.urbanOn and complete then      -- (a stretch once how urban it is is known too)
      local c0 = complete
      complete = function(b) return c0(b) and M.covered(crs.urbRanges, b * bin, (b + 1) * bin) end
    end
    for _, sp in ipairs(M.spots(e, crs.track.waypoints, crs.length, crs.closed, crs.spots, M.level, complete, win,
                                urbanAt)) do
      local objs = M.group(sp, lots and 1 or sc)
      if lots then
        -- the spot's own spectators (they turn to watch) at the fence among the line's people, then the line
        local K = M.KINDS[sp.kind]
        local fans, skip = {}, { [1] = {}, [-1] = {} }
        for _, o in ipairs(objs) do
          if o.fan then
            o.lat = M.STRIP_LAT + 0.15 + (o.lat - K.setback) * 0.4
            fans[#fans + 1] = o
            table.insert(skip[o.side], o.along)
          end
        end
        objs = fans
        for _, o in ipairs(M.line(sp, urbanAt and urbanAt(sp.s) or 0, skip)) do objs[#objs + 1] = o end
      end
      -- a crowd that would reach past the course's start or end slides along to fit on it (the user, 2026-10-25: a
      -- start line's half before the start all stood at the start: fences crossed in an X, people in a heap)
      M.fitOn(objs, crs.length)
      for _, o in ipairs(objs) do
        o.kind = sp.kind
        o.x, o.y, o.yaw = M.placeOf(e, crs.length, o, crs.sides)
        if o.x and o.line and M.insideTurn(e, crs.length, o) then o.x = nil end   -- (overlapping on a tight turn)
        if o.x then list[#list + 1] = o end     -- (no room clear of the course: left out)
      end
      cheers[#cheers + 1] = M.cheerOf(sp, objs)
    end
    M.bin = bin
  end
  return list, cheers
end

-- Every second or so (with the markers): the crowds near the car made, far ones taken away; after dark their lights.
function M.update(crs, anchor, car)
  if M.failed and M.failedAt and os.clock() - M.failedAt > 30 then M.failed = nil end
  if M.level == 'off' or not crs or not anchor or not car or M.failed then
    if nLive > 0 then M.clear() end
    planned.course, planned.cheers = nil, {}
    return
  end
  local sv = crs.sides and crs.sides.version or 0
  local pv = crs.spotsVersion or 0
  local moved = crs.s and planned.window and (crs.s - M.PLAN_BACK_M < planned.window[1] - M.PLAN_SLACK_M
    or crs.s + M.PLAN_AHEAD_M > planned.window[2] + M.PLAN_SLACK_M)
  local now = os.clock()
  local newData = planned.spotsV ~= pv and (not planned.at or now - planned.at >= M.REPLAN_S)
  if planned.course ~= crs or planned.anchor ~= anchor or planned.level ~= M.level or newData or moved then
    local keep = planned.course == crs and planned.anchor == anchor and planned.level == M.level
    local list, cheers = plan(crs, anchor)
    if not keep then M.clear() end
    local want = {}
    for _, o in ipairs(list) do want[o.key] = true end
    for key in pairs(live) do if not want[key] then remove(key) end end
    if not keep then nowhere = {} end                -- (placed anew: judged again)
    if keep then
      -- (1.7.8) the ones standing that the new plan puts elsewhere (the track's widths came in with the new spots):
      -- taken away, made again where they now go; the others keep where they stand
      for _, o in ipairs(list) do
        local l = live[o.key]
        if l then
          if not o.x or math.abs((l.cx or l.px) - o.x) > 0.5 or math.abs((l.cy or l.py) - o.y) > 0.5 then
            remove(o.key)
          else
            o.px, o.py, o.x, o.y = l.cx or l.px, l.cy or l.py, l.px, l.py
          end
        end
      end
    end
    planned = { course = crs, anchor = anchor, level = M.level, list = list, spotsV = pv, sidesV = sv,
                window = planned.window, cheers = cheers, at = now }
  elseif planned.sidesV ~= sv then
    -- the track's widths known (more of them): everyone moved to stand past its edge
    planned.sidesV = sv
    local e = crs.e and crs.e.anchor == anchor and crs.e or nil
    for _, o in ipairs(planned.list) do
      if e then
        local nx, ny, yaw = M.placeOf(e, crs.length, o, crs.sides)
        if not nx then
          -- the track wider than thought: no room for this one any more
          o.x, o.y = nil, nil
          if live[o.key] then remove(o.key) end
        elseif not o.x or math.abs(nx - (o.px or o.x)) > 0.5 or math.abs(ny - (o.py or o.y)) > 0.5 then
          -- (made again where it now goes: its ground, the roads and the course checked there, not slid over)
          o.x, o.y, o.yaw, o.roadV, o.px, o.py = nx, ny, yaw, nil, nil, nil
          if live[o.key] then remove(o.key) end
          nowhere[o.key] = nil
        end
      end
    end
  end
  if not scenetree or not scenetree.MissionGroup then return end
  markers.ensureMaterials()
  local night = M.lights ~= 'off' and M.nightNow(car)
  if M.lights == 'off' then M.isNight = false end
  local made = 0
  local due = {}
  -- (the game's road map around the car and OpenStreetMap's ways: nothing made on a road or a track)
  local roads = roadsnear.combine(roadsnear.current(), osmRoads(anchor, car))
  local checks = 0
  for _, o in ipairs(planned.list) do
    local d2 = math.huge                     -- (no room for it now: never made; a night one by day: not now)
    if o.x and (night or not o.night) then d2 = (o.x - car.x) ^ 2 + (o.y - car.y) ^ 2 end
    local l = live[o.key]
    if l then
      if d2 > M.DESPAWN_M * M.DESPAWN_M then
        remove(o.key)
      elseif d2 < M.SURE_M * M.SURE_M and (not l.sure or (checks < M.REGROUND_PER
          and now - (l.checkedAt or 0) >= M.REGROUND_S)) then
        -- (made far away: the ground there may have been the far tiles'; measured again on the real one. And then
        -- again every REGROUND_S, a few each update (1.7.10, the user 2026-11-10: spectators and canopies in the air:
        -- the block they were measured on was the stand-in BeamNG.Earth sends first, or one built before the
        -- course's track was cut there; the graded one that replaced it is lower)
        checks = checks + (l.sure and 1 or 0)
        l.checkedAt = now
        local gz = markers.groundZ(l.x, l.y, car.z or l.z)
        local ob = scenetree.findObjectById(l.id)
        local kind = l.foot and M.footKind(o.model)
        local verdict, fz = nil, nil
        if kind and ob then verdict, fz = footGround(kind, l.x, l.y, l.yaw, car.z or l.z) end
        if verdict == 'ok' then gz = fz end
        if not ob then live[o.key], nLive = nil, nLive - 1; dropLight(l)
        elseif verdict == 'no' then
          remove(o.key)                                -- (made far away; on the real ground a roof or a slope)
          nowhere[o.key] = true
        elseif gz and verdict ~= 'wait' then
          if l.moved or math.abs(gz - l.z) > (l.sure and M.REGROUND_DZ or 0.15) then
            pcall(markers.place, ob, l.x, l.y, gz, l.yaw); l.z = gz; dropLight(l)
            if l.sure then M.reground = (M.reground or 0) + 1 end
          end
          l.sure, l.moved = true, nil
        end
      end
    end
    if not live[o.key] and not nowhere[o.key] and d2 < M.SPAWN_M * M.SPAWN_M and not M.sidesPending(crs.sides, o.s)
        and not M.onRoad(roads, o) then
      due[#due + 1] = { o = o, d2 = d2 }
    end
  end
  -- the road map changed (the car moved on): anything standing on a road now goes
  if roads and roads.version ~= roadsV then
    roadsV = roads.version
    for _, o in ipairs(planned.list) do
      local l = live[o.key]
      if l and (M.onRoad(roads, o) or math.abs((l.px or l.x) - o.x) > 0.3 or math.abs((l.py or l.y) - o.y) > 0.3) then
        remove(o.key)                                  -- (made again where it now stands, next time)
      end
    end
  end
  -- the nearest made first, a few each time (a Lots line is a few hundred things)
  local eNow = crs.e and crs.e.anchor == anchor and crs.e or nil
  table.sort(due, function(p, q) return p.d2 < q.d2 end)
  local per = M.level == 'lots' and M.PER_UPDATE_LOTS or M.PER_UPDATE
  for _, dd in ipairs(due) do
    if made >= per then break end
    local o = dd.o
    local x, y, z = spotFor(o, car.z or 0, eNow and function(px, py)
      return M.clearFor(eNow, px, py, crs.sides, o.model)
    end)
    if x == false then
      -- (a roof, a wall, a slope: left empty; judged on the far tiles' coarse ground: again when nearer)
      if dd.d2 < M.SURE_M * M.SURE_M then nowhere[o.key] = true end
    elseif x then
      local ok, id = pcall(make, o, z, x, y)
      if ok then
        live[o.key] = { id = id, x = x, y = y, z = z, yaw = o.yaw, base = o.yaw, fan = o.fan, px = o.x, py = o.y,
                        cx = o.px or o.x, cy = o.py or o.y,
                        foot = M.footKind(o.model) ~= nil, sure = dd.d2 < M.SURE_M * M.SURE_M }
        nLive, made = nLive + 1, made + 1
      else
        M.failed, M.failedAt = tostring(id), os.clock()
        if log then log('E', 'offroadCompanion', 'crowds: ' .. M.failed) end
        M.clear()
        return
      end
    end
  end
  -- the lights: the nearest few of the lit things standing, put out (or changed) when they are not wanted
  local want = {}
  if night then
    local cand = {}
    for _, o in ipairs(planned.list) do
      local l = live[o.key]
      if l and o.light then
        local d2 = (l.x - car.x) ^ 2 + (l.y - car.y) ^ 2
        if d2 < M.LIGHT_M * M.LIGHT_M then cand[#cand + 1] = { key = o.key, kind = o.light, d2 = d2 } end
      end
    end
    table.sort(cand, function(p, q) return p.d2 < q.d2 end)
    for i = 1, math.min(#cand, M.MAX_LIGHTS) do want[cand[i].key] = cand[i].kind end
  end
  local sc = M.lights == 'bright' and M.BRIGHT or 1
  for key, l in pairs(live) do
    if l.light and (want[key] ~= l.lightKind or l.lightScale ~= sc) then dropLight(l) end
  end
  for key, kind in pairs(want) do
    local l = live[key]
    if l and not l.light then makeLight(kind, l) end
  end
end

-- The crowds that cheer (crowdsound.lua): { {key, x, y, n, kind, gate} } of the planned ones.
function M.cheers() return planned.cheers or {} end

-- Pure: the yaw a spectator at (x, y) facing `base` turns toward the car at (cx, cy) from `cur`, after dt s.
function M.watchYaw(x, y, base, cur, cx, cy, dt)
  local tx, ty = cx - x, cy - y
  local want = base
  if tx * tx + ty * ty < M.WATCH_M * M.WATCH_M and tx * tx + ty * ty > 1 then
    want = markers.faceYaw(-tx, -ty)
    local d = (want - base + math.pi) % (2 * math.pi) - math.pi
    local lim = math.rad(M.WATCH_MAX_DEG)
    if d > lim then d = lim elseif d < -lim then d = -lim end
    want = base + d
  end
  local d = (want - cur + math.pi) % (2 * math.pi) - math.pi
  local step = math.rad(M.TURN_DEG_S) * (dt or 0)
  if d > step then d = step elseif d < -step then d = -step end
  return cur + d
end

-- Pure: a campfire's light at time t (s), 0.75 .. 1 of its own (two waves, its own phase ph).
function M.flicker(t, ph)
  return 0.875 + 0.125 * (0.6 * math.sin(t * 9.1 + ph) + 0.4 * math.sin(t * 15.3 + ph * 1.7))
end

-- Every frame: the spectators near the car turn to watch it (and back to the course once it is gone); the campfires
-- near it flicker.
local flickAt, flickT = 0, 0
function M.tick(dt, car)
  if nLive == 0 or not car then return end
  local r2 = (M.WATCH_M + 40) ^ 2
  for _, l in pairs(live) do
    if l.fan then
      local dx, dy = l.x - car.x, l.y - car.y
      local nearNow = dx * dx + dy * dy < r2
      if nearNow or math.abs(l.yaw - l.base) > 1e-3 then
        local y2 = M.watchYaw(l.x, l.y, l.base, l.yaw, car.x, car.y, dt)
        if math.abs(y2 - l.yaw) > math.rad(1.5) or (not nearNow and math.abs(y2 - l.base) < math.rad(1.5)) then
          if not nearNow and math.abs(y2 - l.base) < math.rad(1.5) then y2 = l.base end
          local o = scenetree.findObjectById(l.id)
          if o then pcall(markers.place, o, l.x, l.y, l.z, y2) end
          l.yaw = y2
        end
      end
    end
  end
  if nLights == 0 then return end
  flickT = flickT + (dt or 0)
  flickAt = flickAt + (dt or 0)
  if flickAt < 1 / M.FLICKER_HZ then return end
  flickAt = 0
  local sc = M.lights == 'bright' and M.BRIGHT or 1
  local spec = M.LIGHTS.fire
  local f2 = M.FLICKER_M * M.FLICKER_M
  for _, l in pairs(live) do
    if l.light and l.lightKind == 'fire' and (l.x - car.x) ^ 2 + (l.y - car.y) ^ 2 < f2 then
      local o = scenetree.findObjectById(l.light)
      if o then
        local k = M.flicker(flickT, l.ph or 0) * sc
        pcall(function()
          o:setField('brightness', 0, tostring(spec.brightness * k))
          o:setField('intensity', 0, tostring(spec.lm * k))
          if o.postApply then o:postApply() end
        end)
      end
    end
  end
end

function M.status()
  local spots = {}
  for _, o in ipairs(planned.list or {}) do spots[o.kind] = (spots[o.kind] or 0) + 1 end
  return { level = M.level, live = nLive, planned = #(planned.list or {}), failed = M.failed, objects = spots,
           lights = M.lights, night = M.isNight, sun = M.sun and math.floor(M.sun + 0.5) or nil, lit = nLights,
           lightError = M.lightError }
end

function M._live() return live end

return M
