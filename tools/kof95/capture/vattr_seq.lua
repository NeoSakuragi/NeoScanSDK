-- After N frames, print palette numbers used by visible sprites (SCB1 attr of row 0) with their x and tile.
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local n = 0
local port = manager.machine.ioport.ports[":edge:joy:JOY1"]
local F = {D = port.fields["P1 Down"], R = port.fields["P1 Right"], a = port.fields["P1 A"]}
local seq = {{20, ""}, {4, "D"}, {4, "DR"}, {8, "Ra"}, {100, ""}}
local function vr(a) mem:write_u16(0x3C0000, a); return mem:read_u16(0x3C0002) end
local step, left = 1, 20
emu.register_frame_done(function()
  n = n + 1
  left = left - 1
  if left <= 0 and seq[step + 1] then step = step + 1; left = seq[step][1] end
  for k, f in pairs(F) do f:set_value(string.find(seq[step][2], k, 1, true) and 1 or 0) end
  if n == tonumber(os.getenv("AT") or "10") then
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
