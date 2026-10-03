-- KOF96 / KOF98 recorder (run MAME with -noplugin cart_bridge: that test plugin exits MAME at screen frame 3400).
-- From a save state, plays scripted inputs for P1 (SEQ) and P2 (SEQ2), "frames:inputs,..." with inputs from U D L R a b c d
-- ('-' = none); the run ends when SEQ ends. POKE="frame:addr=byte,...;frame:..." writes work-RAM bytes at the start of
-- those frames (cast swap, health, positions, timer).
-- OUT: one line per frame: "frame p1inputs p2inputs <P1 object hex> <P2 object hex> <objects>", P1/P2 = $108100/$108300,
-- $200 bytes each; objects = P1-owned pool objects ($100100 + n*$200, owner long at +$84 = $108100) as
-- "base:table id(+$70):state(+$72):steps(+$80):frame record(+$28):x(+$18):height(+$20):facing(+$31 bit 0)" joined by
-- ";" ("-" if none). KOF96 projectiles use their owner's animation table, so the frame record is in the owner's list.
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
local pokes = {}
for fr, list in string.gmatch(os.getenv("POKE") or "", "(%d+):([^;]+)") do
  for a, v in string.gmatch(list, "(%x+)=(%x+)") do pokes[#pokes + 1] = {tonumber(fr), tonumber(a, 16), tonumber(v, 16)} end
end
local out = io.open(os.getenv("OUT"), "w")
local n = 0
-- SNAPS="frame,frame,...": screenshots at those frames (needs a window: run under xvfb-run with -window)
local snaps = {}
for v in string.gmatch(os.getenv("SNAPS") or "", "%d+") do snaps[tonumber(v)] = true end
-- RELOAD="frame,frame,..." + RELOAD_STATE=name: load that save state at those frames (KOF98: each try starts from the
-- fighter's prepared state, which restores power stocks, positions, life and timer)
local reloads = {}
for v in string.gmatch(os.getenv("RELOAD") or "", "%d+") do reloads[tonumber(v)] = true end
-- SAVE="frame:name;...": save state <name> at those frames (same contract as neogeo_sdl --capture, which takes paths)
local saves = {}
for fr, name in string.gmatch(os.getenv("SAVE") or "", "(%d+):([^;]+)") do saves[tonumber(fr)] = name end
-- SNDLOG=path: every sound command the 68000 writes (REG_SOUND, the byte at $320000) as "frame value" lines (hit sounds)
-- PALDUMP="frame,frame,...": palette RAM ($400000, 8 KB) at those frames to OUT.pal<frame> (a victim's burn palette)
local sndlog = os.getenv("SNDLOG") and io.open(os.getenv("SNDLOG"), "w")
if sndlog then
  _G.record96_snd = mem:install_write_tap(0x320000, 0x320001, "sndlog", function(offset, data, mask)
    if mask & 0xFF00 ~= 0 then
      local ok, sp = pcall(function() return cpu.state["SP"].value end); if not ok then sp = cpu.state["A7"].value end; local st = {}
      for i = 0, 15 do st[#st + 1] = string.format("%06X", mem:read_u32(sp + i * 4) & 0xFFFFFF) end
      sndlog:write(string.format("%05d %02X pc=%06X sp=%s\n", n, (data >> 8) & 0xFF, cpu.state["PC"].value, table.concat(st, ",")))
    end
  end)
end
-- QLOG=path: KOF98's sound ring ($10D940, filled by $7A98) writes with the 68000's PC and stack (who sends a sound)
local qlog = os.getenv("QLOG") and io.open(os.getenv("QLOG"), "w")
if qlog then
  _G.record96_q = mem:install_write_tap(0x10D940, 0x10DA3F, "qlog", function(offset, data, mask)
    local ok, sp = pcall(function() return cpu.state["SP"].value end); if not ok then sp = cpu.state["A7"].value end
    local st = {}
    for i = 0, 11 do st[#st + 1] = string.format("%06X", mem:read_u32(sp + i * 2) & 0xFFFFFF) end
    local v = (mask & 0xFF00 ~= 0) and ((data >> 8) & 0xFF) or (data & 0xFF)
    qlog:write(string.format("%05d %02X pc=%06X d0=%08X a4=%06X sp=%s\n", n, v, cpu.state["PC"].value, cpu.state["D0"].value, cpu.state["A4"].value, table.concat(st, ",")))
    qlog:flush()
  end)
end
-- WLOG="addr,addr": writes to those work-RAM bytes with the PC (who sets a field)
local wlog = os.getenv("WLOG") and io.open(os.getenv("OUT") .. ".wlog", "w")
if wlog then
  _G.record96_w = {}
  for a in string.gmatch(os.getenv("WLOG"), "%x+") do
    local addr = tonumber(a, 16)
    _G.record96_w[#_G.record96_w + 1] = mem:install_write_tap(addr & ~1, addr | 1, "wlog" .. a, function(offset, data, mask)
      wlog:write(string.format("%05d %06X=%04X/%04X pc=%06X d0=%08X d1=%08X a0=%06X a1=%06X a4=%06X\n", n, offset, data, mask,
        cpu.state["PC"].value, cpu.state["D0"].value, cpu.state["D1"].value, cpu.state["A0"].value, cpu.state["A1"].value, cpu.state["A4"].value))
    end)
  end
end
local paldump = {}
for v in string.gmatch(os.getenv("PALDUMP") or "", "%d+") do paldump[tonumber(v)] = true end
_G.record96 = emu.add_machine_frame_notifier(function()
  n = n + 1
  if paldump[n] then
    local pf = io.open(os.getenv("OUT") .. ".pal" .. n, "wb")
    for a = 0x400000, 0x401FFE, 2 do local v = mem:read_u16(a); pf:write(string.char(v >> 8, v & 0xFF)) end
    pf:close()
  end
  if snaps[n] then manager.machine.video:snapshot() end
  if reloads[n] then manager.machine:load(os.getenv("RELOAD_STATE")) end
  if saves[n] then manager.machine:save(saves[n]) end
  for _, p in ipairs(pokes) do if p[1] == n then mem:write_u8(p[2], p[3]) end end
  local t = {string.format("%05d %s %s", n, players[1].cur, players[2].cur)}
  for _, base in ipairs({0x108100, 0x108300}) do
    local h = {}
    for i = 0, 0x1FF, 2 do h[#h + 1] = string.format("%04X", mem:read_u16(base + i)) end
    t[#t + 1] = table.concat(h)
  end
  local objs = {}
  for base = 0x100100, 0x107F00, 0x200 do
    if mem:read_u32(base + 0x84) == 0x108100 then
      local rec = mem:read_u32(base + 0x28) & 0xFFFFFF
      if rec >= 0x200000 and rec < 0x300000 then
        objs[#objs + 1] = string.format("%06X:%d:%d:%d:%06X:%d:%d:%d", base, mem:read_u16(base + 0x70), mem:read_u16(base + 0x72),
          mem:read_u16(base + 0x80), rec, mem:read_i16(base + 0x18), mem:read_i16(base + 0x20), mem:read_u8(base + 0x31) & 1)
      end
    end
  end
  t[#t + 1] = #objs > 0 and table.concat(objs, ";") or "-"
  out:write(table.concat(t, " ") .. "\n")
  for i, p in ipairs(players) do
    p.left = p.left - 1
    if p.left <= 0 then
      p.step = p.step + 1
      if i == 1 and p.step > #p.seq then out:close(); if sndlog then sndlog:close() end; manager.machine:exit(); return end
      apply(p)
    end
  end
end)
