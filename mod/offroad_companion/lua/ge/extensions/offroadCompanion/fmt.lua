-- Distances, speeds and the app's few sentences in English and Spanish. Pure.
local M = {}

local floor = math.floor

M.T = {
  en = {
    ['in'] = 'In %s', now = 'Now', arrived = 'You have arrived', rerouting = 'Rerouting…', planning = 'Planning route…',
    left = 'Left', right = 'Right', hairpin = 'hairpin', long = 'long', into = 'into',
    offCourse = 'Course %s to your %s', wrongWay = 'Wrong way', backOn = 'Back on course',
    speedZone = 'Speed zone %s', speedZoneAhead = 'Speed zone in %s', speedZoneEnd = 'Speed zone ends',
    slowDown = 'Slow down', danger = 'Danger in %s', vcpHit = '%s: checked', vcpMiss = 'Missed %s',
    cpHit = '%s reached', finished = 'Finished: %s', lap = 'Lap %d: %s', bestLap = 'Best lap',
    nextWp = 'Next: %s', reached = 'Reached %s', yourLeft = 'left', yourRight = 'right',
    toStart = 'Start is %s away', startTimer = 'Timer started',
  },
  es = {
    ['in'] = 'En %s', now = 'Ahora', arrived = 'Llegaste a tu destino', rerouting = 'Recalculando…',
    planning = 'Calculando ruta…', left = 'Izquierda', right = 'Derecha', hairpin = 'horquilla', long = 'larga',
    into = 'y', offCourse = 'Curso a %s a tu %s', wrongWay = 'Sentido contrario', backOn = 'De vuelta en el curso',
    speedZone = 'Zona de velocidad %s', speedZoneAhead = 'Zona de velocidad en %s',
    speedZoneEnd = 'Termina zona de velocidad', slowDown = 'Baja la velocidad', danger = 'Peligro en %s',
    vcpHit = '%s: registrado', vcpMiss = 'Perdiste %s', cpHit = '%s alcanzado', finished = 'Terminaste: %s',
    lap = 'Vuelta %d: %s', bestLap = 'Mejor vuelta', nextWp = 'Siguiente: %s', reached = 'Llegaste a %s',
    yourLeft = 'izquierda', yourRight = 'derecha', toStart = 'La salida está a %s', startTimer = 'Cronómetro iniciado',
  },
}

function M.t(lang, key, ...)
  local tbl = M.T[lang] or M.T.en
  local s = tbl[key] or M.T.en[key] or key
  if select('#', ...) > 0 then return string.format(s, ...) end
  return s
end

-- "350 m", "1.2 km", "0.3 mi", "800 ft". imperial: miles / feet.
function M.dist(m, imperial)
  if m == nil then return '' end
  if m < 0 then m = 0 end
  if imperial then
    local ft = m * 3.28084
    if ft < 1000 then return string.format('%d ft', floor(ft / 50 + 0.5) * 50) end
    local mi = m / 1609.344
    if mi < 10 then return string.format('%.1f mi', mi) end
    return string.format('%d mi', floor(mi + 0.5))
  end
  if m < 1000 then
    local r = m < 100 and 10 or 50
    return string.format('%d m', floor(m / r + 0.5) * r)
  end
  if m < 10000 then return string.format('%.1f km', m / 1000) end
  return string.format('%d km', floor(m / 1000 + 0.5))
end

function M.speed(ms, imperial)
  if ms == nil then return '' end
  if imperial then return string.format('%d', floor(ms * 2.23694 + 0.5)) end
  return string.format('%d', floor(ms * 3.6 + 0.5))
end

function M.limit(kph, imperial)
  if not kph then return '' end
  if imperial then return string.format('%d mph', floor(kph / 1.609344 + 0.5)) end
  return string.format('%d km/h', floor(kph + 0.5))
end

-- "1:23.45" / "1:02:03"
function M.laptime(s)
  if not s then return '' end
  local h = floor(s / 3600)
  local m = floor(s / 60) % 60
  local sec = s - floor(s / 60) * 60
  if h > 0 then return string.format('%d:%02d:%02d', h, m, floor(sec)) end
  return string.format('%d:%05.2f', m, sec)
end

-- "12 min", "1 h 05 min"
function M.duration(s)
  if not s then return '' end
  local mins = floor(s / 60 + 0.5)
  if mins < 60 then return string.format('%d min', math.max(1, mins)) end
  return string.format('%d h %02d min', floor(mins / 60), mins % 60)
end

-- A corner call: "Left 3", "Right hairpin", "Left 4 long".
function M.corner(lang, c)
  if not c then return nil end
  local dir = M.t(lang, c.dir)
  local g = c.grade == 'hairpin' and M.t(lang, 'hairpin') or tostring(c.grade)
  local s = dir .. ' ' .. g
  if c.long then s = s .. ' ' .. M.t(lang, 'long') end
  return s
end

return M
