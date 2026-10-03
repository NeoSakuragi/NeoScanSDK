-- Same input sequence as record.lua; saves a screenshot at the frames listed in SNAPS (comma separated).
local port = manager.machine.ioport.ports[":edge:joy:JOY1"]
local F = {U = port.fields["P1 Up"], D = port.fields["P1 Down"], L = port.fields["P1 Left"], R = port.fields["P1 Right"],
           a = port.fields["P1 A"], b = port.fields["P1 B"], c = port.fields["P1 C"], d = port.fields["P1 D"]}
local seq = {}
for frames, inp in string.gmatch(os.getenv("SEQ"), "(%d+):([^,]+)") do seq[#seq + 1] = {tonumber(frames), inp} end
local want = {}; for v in string.gmatch(os.getenv("SNAPS"), "%d+") do want[tonumber(v)] = true end
local step, left, n = 1, seq[1][1], 0
local function apply(inp) for k, f in pairs(F) do f:set_value(string.find(inp, k, 1, true) and 1 or 0) end end
apply(seq[1][2])
emu.register_frame_done(function()
  n = n + 1
  if want[n] then manager.machine.video:snapshot() end
  left = left - 1
  if left <= 0 then
    step = step + 1
    if step > #seq then manager.machine:exit(); return end
    left = seq[step][1]; apply(seq[step][2])
  end
end)
