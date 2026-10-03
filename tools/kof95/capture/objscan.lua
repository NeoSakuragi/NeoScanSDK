-- Plays SEQ for P1 and, every frame, lists $200-byte object slots in $108000-$10BFFF whose +$28 frame record points
-- into the program ROM (an animated object). OUT: "frame slotaddr record x y" lines.
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local port = manager.machine.ioport.ports[":edge:joy:JOY1"]
local F = {U = port.fields["P1 Up"], D = port.fields["P1 Down"], L = port.fields["P1 Left"], R = port.fields["P1 Right"],
           a = port.fields["P1 A"], b = port.fields["P1 B"], c = port.fields["P1 C"], d = port.fields["P1 D"]}
local q = {}
for frames, inp in string.gmatch(os.getenv("SEQ"), "(%d+):([^,]+)") do q[#q + 1] = {tonumber(frames), inp} end
local out = io.open(os.getenv("OUT"), "w")
local n, step, left = 0, 1, q[1][1]
local function apply() local inp = q[step] and q[step][2] or "-"; for k, f in pairs(F) do f:set_value(string.find(inp, k, 1, true) and 1 or 0) end end
apply()
emu.register_frame_done(function()
  n = n + 1
  for base = 0x108000, 0x10BE00, 0x100 do
    local rec = mem:read_u32(base + 0x28) & 0xFFFFFF
    if rec >= 0x080000 and rec < 0x200000 then
      out:write(string.format("%d %06X %06X %d %d %04X\n", n, base, rec, mem:read_i16(base + 0x18), mem:read_i16(base + 0x20), mem:read_u16(base + 0x3C + 2)))
    end
  end
  left = left - 1
  if left <= 0 then step = step + 1; if not q[step] then out:close(); manager.machine:exit(); return end; left = q[step][1]; apply() end
end)
