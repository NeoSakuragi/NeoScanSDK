-- KOF95 recorder with spawned objects (specials). Like record.lua; each line ends with P1-owned pool objects
-- "base:frame record:x:y:sprite-def table:facing:palette slot (+$80):state (+$72, = animation slot of its table)" joined by ";" ("-" if none).
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
local vat = nil
if os.getenv("VATTR_AT") then vat = {}; for v in string.gmatch(os.getenv("VATTR_AT"), "%d+") do vat[tonumber(v)] = true end end
local n = 0
-- POKE="frame:addr=byte,addr=byte;frame:..." writes work-RAM bytes at the start of those frames (cast swap, health).
local pokes = {}
for fr, list in string.gmatch(os.getenv("POKE") or "", "(%d+):([^;]+)") do
  for a, v in string.gmatch(list, "(%x+)=(%x+)") do
    pokes[#pokes + 1] = {tonumber(fr), tonumber(a, 16), tonumber(v, 16)}
  end
end
emu.register_frame_done(function()
  n = n + 1
  for _, p in ipairs(pokes) do if p[1] == n then mem:write_u8(p[2], p[3]) end end
  local t = {string.format("%05d %s %s", n, players[1].cur, players[2].cur)}
  for _, base in ipairs({0x108100, 0x108300}) do
    local h = {}
    for i = 0, 0x1FF, 2 do h[#h + 1] = string.format("%04X", mem:read_u16(base + i)) end
    t[#t + 1] = table.concat(h)
  end
  -- objects spawned by P1 (projectiles, effects): pool $100100-$107F00, $200 each, +$84 = owner object
  local o = {}
  for base = 0x100100, 0x107F00, 0x200 do
    local rec = mem:read_u32(base + 0x28) & 0xFFFFFF
    if mem:read_u32(base + 0x84) == 0x108100 and rec >= 0x080000 and rec < 0x200000 then
      o[#o + 1] = string.format("%06X:%06X:%d:%d:%06X:%d:%02X:%d", base, rec, mem:read_i16(base + 0x18), mem:read_i16(base + 0x20),
                                mem:read_u32(base + 0x3C) & 0xFFFFFF, mem:read_u8(base + 0x31) & 1, mem:read_u8(base + 0x80),
                                mem:read_u16(base + 0x72))
    end
  end
  t[#t + 1] = #o > 0 and table.concat(o, ";") or "-"
  if os.getenv("OBJDUMP_OUT") then                -- optional: full 512 bytes of every P1-owned pool object per frame
    local f = io.open(os.getenv("OBJDUMP_OUT"), "a")
    for base = 0x100100, 0x107F00, 0x200 do
      if mem:read_u32(base + 0x84) == 0x108100 then
        local h = {}
        for i = 0, 0x1FF, 2 do h[#h + 1] = string.format("%04X", mem:read_u16(base + i)) end
        f:write(string.format("%d %06X %s\n", n, base, table.concat(h)))
      end
    end
    f:close()
  end
  -- optional: at frames listed in VATTR_AT, append every visible sprite as "sprite:x:palette:tile(20 bit)" to VATTR_OUT
  if vat and vat[n] then
    local vr = function(a) mem:write_u16(0x3C0000, a); return mem:read_u16(0x3C0002) end
    local f = io.open(os.getenv("VATTR_OUT"), "a")
    for sp = 1, 380 do
      local scb3 = vr(0x8200 + sp)
      if (scb3 & 0x3F) > 0 then
        local attr = vr(sp * 64 + 1)
        f:write(string.format("%d %d %d %d %d\n", n, sp, vr(0x8400 + sp) >> 7, attr >> 8, vr(sp * 64) | (((attr >> 4) & 15) << 16)))
      end
    end
    f:close()
  end
  out:write(table.concat(t, " ") .. "\n")
  for i, p in ipairs(players) do
    p.left = p.left - 1
    if p.left <= 0 then
      p.step = p.step + 1
      if i == 1 and p.step > #p.seq then out:close(); manager.machine:exit(); return end
      apply(p)
    end
  end
end)
