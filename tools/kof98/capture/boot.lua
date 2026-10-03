-- Boot KOF98 into a 2-player versus fight and save state "vs": coins + both starts, then A every 20 frames through
-- team / order select. Detects fighters as pool objects whose +$28 points into P2 ($2xxxxx) with a table id < 38;
-- once two are in state 0 for 90 frames, saves the state and exits. Screenshots every 300 frames (needs -window).
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local P = manager.machine.ioport.ports
local coin, start = P[":AUDIO_COIN"], P[":edge:joy:START"]
local j1, j2 = P[":edge:joy:JOY1"], P[":edge:joy:JOY2"]
local n, calm, found = 0, 0, ""
local out = io.open(os.getenv("OUT") or "/tmp/claude-1000/k98boot.txt", "w")
local function set(port, name, v) local f = port.fields[name]; if f then f:set_value(v) end end
_G.boot98 = emu.add_machine_frame_notifier(function()
  n = n + 1
  set(coin, "Coin 1", (n >= 600 and n < 606) and 1 or 0)
  set(coin, "Coin 2", (n >= 650 and n < 656) and 1 or 0)
  set(start, "1 Player Start", (n >= 720 and n < 726) and 1 or 0)
  set(start, "2 Players Start", (n >= 760 and n < 766) and 1 or 0)
  local press = n > 800 and (n % 20) < 3
  set(j1, "P1 A", press and 1 or 0); set(j2, "P2 A", press and 1 or 0)
  if n % 300 == 0 then manager.machine.video:snapshot() end
  local objs = {}
  for base = 0x100000, 0x10FE00, 0x100 do
    local rec = mem:read_u32(base + 0x28) & 0xFFFFFF; local tid = mem:read_u16(base + 0x70)
    if rec >= 0x200000 and rec < 0x300000 and tid < 38 then objs[#objs + 1] = string.format("%06X:%d:%d", base, tid, mem:read_u16(base + 0x72)) end
  end
  local s = table.concat(objs, " ")
  if s ~= found then out:write(n, " ", s, "\n"); out:flush(); found = s end
  if n > 1500 and #objs >= 2 then calm = calm + 1 else calm = 0 end
  if calm == 90 then manager.machine:save("vs"); out:write("saved at ", n, "\n"); out:close() end
  if calm == 100 or n > 9000 then manager.machine:exit() end
end)
