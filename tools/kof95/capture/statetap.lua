-- Plays SEQ for P1 and logs every write to P1's game state word ($108172) and animation pointer ($108128-B):
-- "frame PC address value". Optional TAP="addr-addr" overrides the watched range.
local cpu = manager.machine.devices[":maincpu"]; local mem = cpu.spaces["program"]
local port = manager.machine.ioport.ports[":edge:joy:JOY1"]
local F = {U = port.fields["P1 Up"], D = port.fields["P1 Down"], L = port.fields["P1 Left"], R = port.fields["P1 Right"],
           a = port.fields["P1 A"], b = port.fields["P1 B"], c = port.fields["P1 C"], d = port.fields["P1 D"]}
local q = {}
for frames, inp in string.gmatch(os.getenv("SEQ"), "(%d+):([^,]+)") do q[#q + 1] = {tonumber(frames), inp} end
local out = io.open(os.getenv("OUT"), "w")
local n, step, left = 0, 1, q[1][1]
local lo, hi = 0x108172, 0x108173
local t = os.getenv("TAP"); if t then local a, b = string.match(t, "(%x+)-(%x+)"); lo, hi = tonumber(a, 16), tonumber(b, 16) end
local tap = mem:install_write_tap(lo, hi, "st", function(offset, data, mask)
  out:write(string.format("%d %06X %06X %04X %04X\n", n, cpu.state["PC"].value, offset, data, mask))
end)
local port2 = manager.machine.ioport.ports[":edge:joy:JOY2"]
local F2 = {L = port2.fields["P2 Left"], c = port2.fields["P2 C"]}
local q2 = {}
for frames, inp in string.gmatch(os.getenv("SEQ2") or "", "(%d+):([^,]+)") do q2[#q2 + 1] = {tonumber(frames), inp} end
local step2, left2 = 1, q2[1] and q2[1][1] or 1e9
local pokes = {}
for fr, list in string.gmatch(os.getenv("POKE") or "", "(%d+):([^;]+)") do
  for a, v in string.gmatch(list, "(%x+)=(%x+)") do pokes[#pokes + 1] = {tonumber(fr), tonumber(a, 16), tonumber(v, 16)} end
end
local function apply2() local inp = q2[step2] and q2[step2][2] or "-"; for k, f in pairs(F2) do f:set_value(string.find(inp, k, 1, true) and 1 or 0) end end
apply2()
local function apply() local inp = q[step] and q[step][2] or "-"; for k, f in pairs(F) do f:set_value(string.find(inp, k, 1, true) and 1 or 0) end end
apply()
emu.register_frame_done(function()
  n = n + 1
  for _, p in ipairs(pokes) do if p[1] == n then mem:write_u8(p[2], p[3]) end end
  left2 = left2 - 1
  if left2 <= 0 then step2 = step2 + 1; left2 = q2[step2] and q2[step2][1] or 1e9; apply2() end
  left = left - 1
  if left <= 0 then step = step + 1; if not q[step] then out:close(); tap:remove(); manager.machine:exit(); return end; left = q[step][1]; apply() end
end)
