-- MAME: log every byte the 68000 writes to REG_SOUND ($320000) with its frame, P1's inputs and P2's life word, while
-- P1 plays SEQ ("frames:inputs,..." from U D L R a b c d, '-' = none, as record96.lua). OUT: "frame cmd p1inputs p2life".
-- mame kof98 -state c3 -autoboot_script sound_tap.lua -noplugin cart_bridge -video none -sound none -nothrottle
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local port = manager.machine.ioport.ports[":edge:joy:JOY1"]
local F = {U = port.fields["P1 Up"], D = port.fields["P1 Down"], L = port.fields["P1 Left"], R = port.fields["P1 Right"],
           a = port.fields["P1 A"], b = port.fields["P1 B"], c = port.fields["P1 C"], d = port.fields["P1 D"]}
local seq = {}
for frames, inp in string.gmatch(os.getenv("SEQ") or "", "(%d+):([^,]+)") do seq[#seq + 1] = {tonumber(frames), inp} end
local out = io.open(os.getenv("OUT"), "w")
local life = tonumber(os.getenv("LIFE_ADDR") or "0", 16)
local frame, step, left, cur = 0, 1, 0, "-"
local function apply()
  local e = seq[step]; cur = e and e[2] or "-"; left = e and e[1] or 0
  for k, f in pairs(F) do f:set_value(string.find(cur, k, 1, true) and 1 or 0) end
end
apply()
tap = mem:install_write_tap(0x320000, 0x320001, "snd", function(offset, data, mask)
  local b = (mask & 0xFF00) ~= 0 and (data >> 8) or (data & 0xFF)
  out:write(string.format("%d %02X %s %04X\n", frame, b, cur, life ~= 0 and mem:read_u16(life) or 0)); out:flush()
end)
emu.register_frame_done(function()
  frame = frame + 1; left = left - 1
  if left <= 0 then step = step + 1; if step > #seq then out:close(); manager.machine:exit() return end; apply() end
end)
