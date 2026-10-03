-- Dump 64 KB work RAM ($100000-$10FFFF) after N frames to OUT.
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local n, want = 0, tonumber(os.getenv("N") or "5")
emu.register_frame_done(function()
  n = n + 1
  if n == want then
    local f = io.open(os.getenv("OUT"), "wb")
    for a = 0x100000, 0x10FFFF do f:write(string.char(mem:read_u8(a))) end
    f:close(); manager.machine:exit()
  end
end)
