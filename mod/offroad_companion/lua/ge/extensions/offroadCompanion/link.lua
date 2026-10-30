-- Non-blocking TCP client for the Offroad Companion (127.0.0.1:47614), the same framing as BeamNG.Earth's server:
-- 4-byte little-endian length + UTF-8 JSON. luasocket with settimeout(0): never blocks a frame; reconnects every
-- RECONNECT_S. update() returns this frame's messages plus {type='_connected'} / {type='_disconnected'}.
-- Pure Lua framing (ffi.cast is a stub in the game's sandbox).
local M = {}

M.HOST, M.PORT = '127.0.0.1', 47614
M.RECONNECT_S = 3.0
M.CONNECT_TIMEOUT_S = 2.0
M.MAX_FRAME = 32 * 1024 * 1024

local byte, char, floor = string.byte, string.char, math.floor

function M.encode(payload)
  local n = #payload
  return char(n % 256, floor(n / 256) % 256, floor(n / 65536) % 256, floor(n / 16777216) % 256) .. payload
end

-- Reassembler: feed(chunk), pop() -> payload | nil; .err on a bad stream.
function M.newReader()
  local r = { parts = {}, pending = 0, buf = '', need = nil, err = nil }
  function r.feed(chunk)
    if chunk and #chunk > 0 then
      r.parts[#r.parts + 1] = chunk
      r.pending = r.pending + #chunk
    end
  end
  function r.pop()
    if r.err then return nil end
    local have = #r.buf + r.pending
    if (not r.need and have < 4) or (r.need and have < 4 + r.need) then return nil end
    if r.pending > 0 then
      r.buf = r.buf .. table.concat(r.parts)
      r.parts, r.pending = {}, 0
    end
    if not r.need then
      local b1, b2, b3, b4 = byte(r.buf, 1, 4)
      local n = b1 + b2 * 256 + b3 * 65536 + b4 * 16777216
      if n > M.MAX_FRAME then r.err = 'frame too large'; return nil end
      r.need = n
      if #r.buf < 4 + n then return nil end
    end
    local n = r.need
    local payload = r.buf:sub(5, 4 + n)
    r.buf = r.buf:sub(5 + n)
    r.need = nil
    return payload
  end
  function r.reset() r.parts, r.pending, r.buf, r.need, r.err = {}, 0, '', nil, nil end
  return r
end

local socketLib, sock = nil, nil
local state, timer = 'disconnected', M.RECONNECT_S
local rx = M.newReader()
local out, outPos = {}, 1
local events = {}
M.lastError = nil

local function close(err)
  if sock then pcall(sock.close, sock) end
  local was = state == 'connected'
  sock, state, timer = nil, 'disconnected', 0
  rx.reset()
  out, outPos = {}, 1
  M.lastError = err
  if was then events[#events + 1] = { type = '_disconnected', error = err } end
end

local function connected()
  state, M.lastError = 'connected', nil
  pcall(sock.setoption, sock, 'tcp-nodelay', true)
  events[#events + 1] = { type = '_connected' }
end

local function startConnect()
  local ok, lib = pcall(require, 'socket')
  if not ok then M.lastError = 'luasocket unavailable'; timer = 0; return end
  socketLib = lib
  sock = socketLib.tcp()
  sock:settimeout(0)
  local res, err = sock:connect(M.HOST, M.PORT)
  if res then connected()
  elseif err == 'timeout' or err == 'Operation already in progress' then state, timer = 'connecting', 0
  else close(err) end
end

local function flush()
  while sock and out[1] do
    local last, err, partial = sock:send(out[1], outPos)
    if last then
      table.remove(out, 1)
      outPos = 1
    elseif err == 'timeout' then
      outPos = (partial or (outPos - 1)) + 1
      return
    else
      close('send: ' .. tostring(err))
      return
    end
  end
end

function M.update(dt, decode)
  if state == 'disconnected' then
    timer = timer + dt
    if timer >= M.RECONNECT_S then startConnect() end
  elseif state == 'connecting' then
    if sock:getpeername() then connected()
    else
      timer = timer + dt
      if timer >= M.CONNECT_TIMEOUT_S then close('companion not running (127.0.0.1:' .. M.PORT .. ')') end
    end
  end
  local res = events
  events = {}
  if state == 'connected' then
    flush()
    local closeErr = nil
    for _ = 1, 256 do
      if not sock then break end
      local data, err, partial = sock:receive(65536)
      rx.feed(data or partial)
      if err and err ~= 'timeout' then closeErr = err; break end
      if not data then break end
    end
    while true do
      local payload = rx.pop()
      if not payload then break end
      local msg = decode(payload)
      if type(msg) == 'table' then res[#res + 1] = msg end
    end
    if rx.err then close(rx.err) elseif closeErr then close(closeErr == 'closed' and 'companion closed' or closeErr) end
  end
  for _, e in ipairs(events) do res[#res + 1] = e end
  events = {}
  return res
end

function M.send(msg, encodeJson)
  if state ~= 'connected' then return false end
  out[#out + 1] = M.encode(encodeJson(msg))
  flush()
  return true
end

function M.state() return state end
function M.connected() return state == 'connected' end
function M.close() close('closed'); events = {}; timer = M.RECONNECT_S end

return M
