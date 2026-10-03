-- Plays SEQ for P1 and dumps 64 KB work RAM at the frames listed in AT to OUT<frame>.bin.
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local port = manager.machine.ioport.ports[":edge:joy:JOY1"]
local F = {U = port.fields["P1 Up"], D = port.fields["P1 Down"], L = port.fields["P1 Left"], R = port.fields["P1 Right"],
           a = port.fields["P1 A"], b = port.fields["P1 B"], c = port.fields["P1 C"], d = port.fields["P1 D"]}
local q = {}
for frames, inp in string.gmatch(os.getenv("SEQ"), "(%d+):([^,]+)") do q[#q + 1] = {tonumber(frames), inp} end
local at, last = {}, 0; for v in string.gmatch(os.getenv("AT"), "%d+") do at[tonumber(v)] = true; last = math.max(last, tonumber(v)) end
local n, step, left = 0, 1, q[1][1]
local function apply() local inp = q[step] and q[step][2] or "-"; for k, f in pairs(F) do f:set_value(string.find(inp, k, 1, true) and 1 or 0) end end
apply()
emu.register_frame_done(function()
  n = n + 1
  if at[n] then local f = io.open(os.getenv("OUT") .. n .. ".bin", "wb"); for a = 0x100000, 0x10FFFF do f:write(string.char(mem:read_u8(a))) end; f:close() end
  if n >= last then manager.machine:exit() end
  left = left - 1
  if left <= 0 then step = step + 1; left = q[step] and q[step][1] or 1e9; apply() end
end)
