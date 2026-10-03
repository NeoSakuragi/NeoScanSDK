-- KOF95 recorder. From a save state, plays scripted input sequences for P1 (SEQ) and optionally P2 (SEQ2) and dumps the
-- P1 and P2 character objects ($108100 and $108300, $200 bytes each) every frame.
-- Sequences: "frames:inputs,..." with inputs from U D L R a b c d ('-' = none). The run ends when SEQ ends.
-- OUT: one text line per frame: "frame p1inputs p2inputs <P1 object hex> <P2 object hex>".
-- Object fields (found 2026-10-02): +$18.w X (+$1A fraction), +$20.w height (+$22 fraction), +$28.l current frame record
-- (low 24 bits; top byte = flags), +$31 bit 0 facing, +$3C.l sprite definition table, +$72.w game state.
local cpu = manager.machine.devices[":maincpu"]; local mem = cpu.spaces["program"]
local function fields(tag, p)
  local port = manager.machine.ioport.ports[tag]
  return {U = port.fields[p .. " Up"], D = port.fields[p .. " Down"], L = port.fields[p .. " Left"], R = port.fields[p .. " Right"],
          a = port.fields[p .. " A"], b = port.fields[p .. " B"], c = port.fields[p .. " C"], d = port.fields[p .. " D"]}
end
local function parse(s)
  local q = {}
  for frames, inp in string.gmatch(s or "", "(%d+):([^,]+)") do q[#q + 1] = {tonumber(frames), inp} end
  return q
end
local players = {
  {F = fields(":edge:joy:JOY1", "P1"), seq = parse(os.getenv("SEQ")), step = 1},
  {F = fields(":edge:joy:JOY2", "P2"), seq = parse(os.getenv("SEQ2")), step = 1},
}
local function apply(p)
  local e = p.seq[p.step]; local inp = e and e[2] or "-"
  for k, f in pairs(p.F) do f:set_value(string.find(inp, k, 1, true) and 1 or 0) end
  p.left = e and e[1] or math.huge; p.cur = inp
end
for _, p in ipairs(players) do apply(p) end
local out = io.open(os.getenv("OUT"), "w")
-- CAM_OUT: per frame "frame stage-left stage-right camera-x" ($10B14C, $10B150: stage limits the throw routine keeps
-- victims inside, +32 / +288; $10B078: camera x, 16.16; fighters are clamped to camera +32 .. +288)
local cam = os.getenv("CAM_OUT") and io.open(os.getenv("CAM_OUT"), "w") or nil
local n = 0
-- POKE="frame:addr=byte,addr=byte;frame:..." writes work-RAM bytes at the start of those frames (cast swap, health).
local pokes = {}
for fr, list in string.gmatch(os.getenv("POKE") or "", "(%d+):([^;]+)") do
  for a, v in string.gmatch(list, "(%x+)=(%x+)") do
    pokes[#pokes + 1] = {tonumber(fr), tonumber(a, 16), tonumber(v, 16)}
  end
end
-- READTAP_PC="lo-hi" (hex) + READTAP_OUT: log work-RAM reads made by instructions in that PC range, with A0
-- ("frame pc address A0"); e.g. 4AE6-4AEC gives the throw table each frame of a throw
local rt = nil
if os.getenv("READTAP_PC") then
  local lo, hi = string.match(os.getenv("READTAP_PC"), "(%x+)-(%x+)"); lo, hi = tonumber(lo, 16), tonumber(hi, 16)
  local cpu = manager.machine.devices[":maincpu"]; local rf = io.open(os.getenv("READTAP_OUT"), "w")
  rt = mem:install_read_tap(0x100000, 0x10FFFF, "rt", function(offset, data, mask)
    local pc = cpu.state["PC"].value
    if pc >= lo and pc <= hi then rf:write(string.format("%d %06X %06X %08X\n", n, pc, offset, cpu.state["A0"].value)); rf:flush() end
  end)
end
-- SNAPS="frame,frame,...": screenshots at those frames (needs a window: run under xvfb-run with -window)
local snaps = {}
for v in string.gmatch(os.getenv("SNAPS") or "", "%d+") do snaps[tonumber(v)] = true end
emu.register_frame_done(function()
  n = n + 1
  if snaps[n] then manager.machine.video:snapshot() end
  for _, p in ipairs(pokes) do if p[1] == n then mem:write_u8(p[2], p[3]) end end
  local t = {string.format("%05d %s %s", n, players[1].cur, players[2].cur)}
  for _, base in ipairs({0x108100, 0x108300}) do
    local h = {}
    for i = 0, 0x1FF, 2 do h[#h + 1] = string.format("%04X", mem:read_u16(base + i)) end
    t[#t + 1] = table.concat(h)
  end
  out:write(table.concat(t, " ") .. "\n")
  if cam then cam:write(string.format("%d %d %d %d\n", n, mem:read_i16(0x10B14C), mem:read_i16(0x10B150), mem:read_i32(0x10B078))) end
  for i, p in ipairs(players) do
    p.left = p.left - 1
    if p.left <= 0 then
      p.step = p.step + 1
      if i == 1 and p.step > #p.seq then out:close(); manager.machine:exit(); return end
      apply(p)
    end
  end
end)
