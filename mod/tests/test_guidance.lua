-- luajit test_guidance.lua (from mod/tests): the app's pure guidance logic with a flat fake anchor.
package.path = '../offroad_companion/lua/ge/extensions/?.lua;' .. package.path

local poly = require('offroadCompanion/poly')
local fmt = require('offroadCompanion/fmt')
local course = require('offroadCompanion/course')
local nav = require('offroadCompanion/nav')
local link = require('offroadCompanion/link')

local pass, fail = 0, 0
local function check(cond, name)
  if cond then pass = pass + 1 else fail = fail + 1; print('FAIL: ' .. name) end
end
local function near(a, b, tol, name) check(a and b and math.abs(a - b) <= tol, name .. ' (' .. tostring(a) .. ' vs ' .. tostring(b) .. ')') end

-- flat anchor around (lat0, lon0): equirectangular metres (what geodeticToEnu gives near the anchor)
local LAT0, LON0 = 31.8667, -116.6
local K = 111195.0
local anchor = {}
function anchor:geodeticToEnu(lat, lon) return (lon - LON0) * K * math.cos(math.rad(LAT0)), (lat - LAT0) * K, 0 end
local function ll(x, y) return { LAT0 + y / K, LON0 + x / (K * math.cos(math.rad(LAT0))) } end

-- -- poly ---------------------------------------------------------------------------------------------------------
do
  -- straight 500 m east, a 90° right-hander of radius 30 m, then 500 m south
  local xs, ys = {}, {}
  for i = 0, 50 do xs[#xs + 1], ys[#ys + 1] = i * 10, 0 end
  for a = 1, 15 do
    local t = math.rad(a * 6)
    xs[#xs + 1], ys[#ys + 1] = 500 + 30 * math.sin(t), -30 + 30 * math.cos(t)
  end
  for i = 1, 50 do xs[#xs + 1], ys[#ys + 1] = 530, -30 - i * 10 end
  local e = poly.fromXY(xs, ys)
  local cs = poly.corners(e, 300, 400)
  check(#cs == 1, 'one corner ahead: ' .. #cs)
  if cs[1] then
    check(cs[1].dir == 'right', 'corner is a right')
    check(cs[1].grade == 2, 'R30 is grade 2, got ' .. tostring(cs[1].grade))
    near(cs[1].s0, 500, 25, 'corner starts near 500 m')
    near(cs[1].angle, 90, 15, 'corner angle')
  end
  check(fmt.corner('en', cs[1]) == 'Right 2', 'call text')
  check(fmt.corner('es', cs[1]) == 'Derecha 2', 'call text es')
  -- a hairpin: 180° in 60 m
  local hx, hy = {}, {}
  for i = 0, 30 do hx[#hx + 1], hy[#hy + 1] = i * 10, 0 end
  for a = 1, 18 do
    local t = math.rad(a * 10)
    hx[#hx + 1], hy[#hy + 1] = 300 + 12 * math.sin(t), 12 - 12 * math.cos(t)
  end
  for i = 1, 30 do hx[#hx + 1], hy[#hy + 1] = 300 - i * 10, 24 end
  local he = poly.fromXY(hx, hy)
  local hc = poly.corners(he, 150, 300)
  check(hc[1] and hc[1].grade == 'hairpin' and hc[1].dir == 'left', 'hairpin left: ' .. tostring(hc[1] and hc[1].grade))
  -- straight: no corners
  check(#poly.corners(poly.fromXY({ 0, 1000 }, { 0, 0 }), 0, 400) == 0, 'straight has no corners')

  -- follow on an out-and-back: stays on the pass it is on
  local ox, oy = {}, {}
  for i = 0, 100 do ox[#ox + 1], oy[#oy + 1] = i * 10, 0 end
  for i = 99, 0, -1 do ox[#ox + 1], oy[#oy + 1] = i * 10, 3 end
  local oe = poly.fromXY(ox, oy)
  local s1 = poly.follow(oe, 200, 1.0, nil)
  near(s1, 200, 2, 'first pass found')
  local s2 = poly.follow(oe, 200, 2.0, 1790)   -- on the way back near x=200 (s ~ 1800)
  near(s2, 1800, 3, 'stays on the return pass')
  -- race miles
  near(poly.raceMile({ { 0, 0 }, { 1609.344, 1 } }, 3218.688), 2, 1e-6, 'race mile extrapolates')
  near(poly.raceMile({ { 1000, 10 }, { 2000, 11 } }, 1500), 10.5, 1e-6, 'race mile interpolates')
  near(poly.raceMile(nil, 1609.344), 1, 1e-6, 'race mile without anchors')
  check(poly.angleDiff(350, 10) == 20 and poly.angleDiff(10, 350) == -20, 'angleDiff wraps')
end

-- -- course: open course with VCP, speed zone, timing ---------------------------------------------------------------
do
  local pts = {}
  for i = 0, 300 do pts[#pts + 1] = ll(i * 10, 0) end         -- 3 km east
  local function at(x) local p = ll(x, 0); return p[1], p[2] end
  local la1, lo1 = at(1000)
  local la2, lo2 = at(2000)
  local track = {
    name = 'Test course', kind = 'course', points = pts, length = 3000, closed = false,
    waypoints = {
      { name = 'VCP 1', kind = 'vcp', lat = la1, lon = lo1, s = 1000, off = 0 },
      { name = 'VCP 2', kind = 'vcp', lat = la2, lon = lo2, s = 2000, off = 0 },
      { name = 'DANGER 1', kind = 'danger', lat = la2, lon = lo2, s = 2100, off = 0 },
    },
    zones = { { name = 'SZ01', s0 = 400, s1 = 800, limit = 60 } },
    rm = {},
  }
  local c = course.new(track)
  local now = 0
  local st
  -- drive along at 25 m/s, sidestepping VCP 2 by 150 m
  for x = 0, 3000, 20 do
    local y = (x > 1850 and x < 2150) and 150 or 0
    now = now + 0.8
    st = c:update(anchor, x, y, 90, 25, now, 'en', false)
    if x == 600 then
      check(st.zone and st.zone.limit == 60 and st.zone.speeding, 'in the speed zone, speeding')
    end
    if x == 200 then
      check(st.zoneAhead and math.abs(st.zoneAhead.dist - 200) < 1, 'zone ahead 200 m')
      check(st.ahead[1] and st.ahead[1].name == 'VCP 1', 'next callout VCP 1')
      check(st.timing.elapsed ~= nil, 'stage timer started')
    end
    if x == 1960 then
      check(st.offCourse and st.offCourse.dir == 'right', 'off course: course is to the right (heading east, 150 m north)')
      check(st.danger and st.danger.name == 'DANGER 1', 'danger ahead')
    end
  end
  check(c.judged[1] == 'hit', 'VCP 1 hit')
  check(c.judged[2] == 'miss', 'VCP 2 missed')
  check(st.vcp.hit == 1 and st.vcp.miss == 1, 'vcp counts')
  check(st.timing.finished, 'finished')
  -- wrong way
  st = c:update(anchor, 2900, 0, 270, 10, now + 1, 'en', false)
  check(st.wrongWay, 'wrong way detected')
end

-- -- course: closed circuit laps ------------------------------------------------------------------------------------
do
  local pts = {}
  local R = 200
  for a = 0, 72 do
    local t = math.rad(a * 5)
    pts[#pts + 1] = ll(R * math.sin(t), R * math.cos(t))       -- clockwise from north
  end
  local c = course.new({ name = 'Ring', kind = 'circuit', points = pts, closed = true, waypoints = {}, zones = {}, rm = {} })
  local now, st = 0, nil
  for lap = 1, 3 do
    for a = 0, 355, 5 do
      now = now + 1
      local t = math.rad(a)
      st = c:update(anchor, R * math.sin(t), R * math.cos(t), (a + 90) % 360, 20, now, 'en', false)
    end
  end
  now = now + 1
  st = c:update(anchor, 0, R, 90, 20, now, 'en', false)
  check(c.lap == 2, 'two full laps timed after three passes of the line: ' .. c.lap)
  near(c.best, 72, 1.5, 'lap time ~72 s')
  check(st.timing.mode == 'laps', 'lap timing')
  check(st.corner and st.corner.dir == 'right', 'ring corner is a right')
end

-- -- course: waypoints only ---------------------------------------------------------------------------------------
do
  local w1, w2 = ll(0, 1000), ll(1000, 1000)
  local c = course.new({ name = 'Towns', kind = 'waypoints', points = {}, length = 2000,
    waypoints = { { name = 'A', kind = 'start', lat = w1[1], lon = w1[2], s = 0 }, { name = 'B', kind = 'place', lat = w2[1], lon = w2[2], s = 1000 } } })
  local st = c:update(anchor, 0, 0, 0, 10, 1, 'en', false)
  check(st.target and st.target.name == 'A' and st.target.dir == 'ahead', 'target A ahead')
  near(st.remaining, 2000, 5, 'remaining over the waypoints')
  st = c:update(anchor, 0, 980, 0, 10, 2, 'en', false)
  check(st.target and st.target.name == 'B' and st.target.dir == 'right', 'reached A, B to the right')
  st = c:update(anchor, 1000, 1000, 90, 10, 3, 'en', false)
  check(st.finished, 'waypoints finished')
end

-- -- nav: maneuvers ---------------------------------------------------------------------------------------------------
do
  local pts = {}
  for i = 0, 100 do pts[#pts + 1] = ll(i * 10, 0) end
  for i = 1, 50 do pts[#pts + 1] = ll(1000, -i * 10) end
  local p0, p1, p2 = pts[1], pts[101], pts[#pts]
  local route = { points = pts, dist = 1500, dur = 150, steps = {
    { text = 'Head east on A', icon = 'straight', type = 'depart', lat = p0[1], lon = p0[2], road = 'A' },
    { text = 'Turn right onto B', icon = 'right', type = 'turn', lat = p1[1], lon = p1[2], road = 'B' },
    { text = 'Arrive', icon = 'arrive', type = 'arrive', lat = p2[1], lon = p2[2], road = 'B' } } }
  local n = nav.new(route, {})
  local st = n:update(anchor, 300, 2, 1)
  check(st.next and st.next.text == 'Turn right onto B', 'next is the right turn')
  near(st.next.dist, 700, 3, 'distance to the turn')
  check(st.road == 'A', 'on road A')
  near(st.eta, 120, 2, 'eta scaled')
  st = n:update(anchor, 1000, -100, 2)
  check(st.next and st.next.type == 'arrive', 'after the turn: arrive next')
  st = n:update(anchor, 1300, 200, 3)       -- far off
  check(not st.offRoute, 'not rerouted at once')
  st = n:update(anchor, 1300, 200, 7)
  check(st.offRoute, 'rerouted after a while off route')
  st = n:update(anchor, 1000, -495, 8)
  check(st.arrived, 'arrived at the end')
end

-- -- link framing / fmt ------------------------------------------------------------------------------------------------
do
  local r = link.newReader()
  local f = link.encode('{"type":"hello"}') .. link.encode('{"x":1}')
  for i = 1, #f, 3 do r.feed(f:sub(i, i + 2)) end
  check(r.pop() == '{"type":"hello"}', 'frame 1')
  check(r.pop() == '{"x":1}', 'frame 2')
  check(r.pop() == nil, 'no frame 3')
  local big = string.rep('a', 70000)
  r.feed(link.encode(big))
  check(r.pop() == big, 'large frame')
  check(fmt.dist(349) == '350 m' and fmt.dist(1234) == '1.2 km' and fmt.dist(42) == '40 m', 'metric distances')
  check(fmt.dist(160, true) == '500 ft' and fmt.dist(4828, true) == '3.0 mi', 'imperial distances')
  check(fmt.laptime(83.456) == '1:23.46', 'lap time ' .. fmt.laptime(83.456))
  check(fmt.duration(3900) == '1 h 05 min', 'duration')
  check(fmt.t('es', 'lap', 2, '1:00.00') == 'Vuelta 2: 1:00.00', 'spanish format')
end

print(string.format('%d passed, %d failed', pass, fail))
os.exit(fail == 0 and 0 or 1)
