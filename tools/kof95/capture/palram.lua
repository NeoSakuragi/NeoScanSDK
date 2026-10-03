-- Dump palette RAM ($400000-$401FFF, current bank) after N frames to OUT (raw big-endian words).
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local n, want = 0, tonumber(os.getenv("N") or "10")
emu.register_frame_done(function()
  n = n + 1
  if n == want then
    local f = io.open(os.getenv("OUT"), "wb")
    for a = 0x400000, 0x401FFE, 2 do local v = mem:read_u16(a); f:write(string.char(v >> 8, v & 0xFF)) end
    f:close(); manager.machine:exit()
  end
end)
