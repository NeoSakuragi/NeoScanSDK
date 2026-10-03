-- Same input sequence as record.lua, but dumps all 64 KB of 68000 work RAM ($100000-$10FFFF) per frame, big-endian, to OUT (binary).
local cpu = manager.machine.devices[":maincpu"]; local mem = cpu.spaces["program"]
local port = manager.machine.ioport.ports[":edge:joy:JOY1"]
local F = {U = port.fields["P1 Up"], D = port.fields["P1 Down"], L = port.fields["P1 Left"], R = port.fields["P1 Right"],
           a = port.fields["P1 A"], b = port.fields["P1 B"], c = port.fields["P1 C"], d = port.fields["P1 D"]}
local seq = {}
for frames, inp in string.gmatch(os.getenv("SEQ"), "(%d+):([^,]+)") do seq[#seq + 1] = {tonumber(frames), inp} end
local out = io.open(os.getenv("OUT"), "wb")
local step, left = 1, seq[1][1]
local function apply(inp) for k, f in pairs(F) do f:set_value(string.find(inp, k, 1, true) and 1 or 0) end end
apply(seq[1][2])
emu.register_frame_done(function()
  local t = {}
  for i = 0, 0xFFFF, 2 do local v = mem:read_u16(0x100000 + i); t[#t + 1] = string.char(v >> 8, v & 0xFF) end
  out:write(table.concat(t))
  left = left - 1
  if left <= 0 then
    step = step + 1
    if step > #seq then out:close(); manager.machine:exit(); return end
    left = seq[step][1]; apply(seq[step][2])
  end
end)
