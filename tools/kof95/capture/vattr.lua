-- After N frames, print palette numbers used by visible sprites (SCB1 attr of row 0) with their x and tile.
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local n = 0
local function vr(a) mem:write_u16(0x3C0000, a); return mem:read_u16(0x3C0002) end
emu.register_frame_done(function()
  n = n + 1
  if n == 10 then
    local f = io.open(os.getenv("OUT"), "w")
    for s = 1, 380 do
      local scb3 = vr(0x8200 + s)
      if (scb3 & 0x3F) > 0 or (scb3 & 0x40) ~= 0 then
        f:write(string.format("%d %d %d %d\n", s, vr(0x8400 + s) >> 7, vr(s * 64 + 1) >> 8, vr(s * 64)))
      end
    end
    f:close(); manager.machine:exit()
  end
end)
