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
_G.record96 = emu.add_machine_frame_notifier(function()
  n = n + 1
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
      if i == 1 and p.step > #p.seq then out:close(); manager.machine:exit(); return end
      apply(p)
    end
  end
end)
