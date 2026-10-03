-- Same input sequence; per frame dumps the P1 object (state at +$72) and the SCB1 tile numbers of all 381 sprites
-- (32 rows each, as two words: tile low 16 bits, attribute = palette:8 | tile bits 16-19:4 | auto-anim:2 | V flip | H flip),
-- via VRAM address/data ports $3C0000/$3C0002. Output OUT (binary): per frame 0x200 object bytes then 381*32*(lo, attr) u16, big-endian.
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
  for i = 0, 0x1FF, 2 do local v = mem:read_u16(0x108100 + i); t[#t + 1] = string.char(v >> 8, v & 0xFF) end
  -- the VRAM address only auto-increments after WRITES to the data port, so set it before every read
  for s = 0, 380 do
    for r = 0, 31 do
      mem:write_u16(0x3C0000, s * 64 + r * 2); local lo = mem:read_u16(0x3C0002)
      mem:write_u16(0x3C0000, s * 64 + r * 2 + 1); local attr = mem:read_u16(0x3C0002)
      t[#t + 1] = string.char(lo >> 8, lo & 0xFF, attr >> 8, attr & 0xFF)
    end
  end
  out:write(table.concat(t))
  left = left - 1
  if left <= 0 then
    step = step + 1
    if step > #seq then out:close(); manager.machine:exit(); return end
    left = seq[step][1]; apply(seq[step][2])
  end
end)
