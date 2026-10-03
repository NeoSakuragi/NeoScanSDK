-- KOF98 sound ground truth: every YM2610 write by the sound CPU (I/O ports 4-7) and every sound command the
-- 68000 sends (write to $320000), with the screen frame. OUT=file, FRAMES=n (then MAME exits).
-- Lines: "f <frame>" once per frame with activity, "c <cmd>" 68000 command, "a <reg> <val>" port A, "b <reg> <val>" port B.
-- SEND="frame:hex,..." writes sound commands to $320000 at those frames (as the 68000 does).
-- IRQ=1 adds an "i" line at every sound-CPU read of YM status port $04: only the timer ISR ($1954) reads it, so one
-- line per timer-A interrupt (the sequencer's clock). BLOCK=n: from frame n on, commands the game itself sends are
-- replaced by $60 on the Z80 side (a type-0 command: queued, then ignored; NOT $00, which advances the NMI ring
-- index without storing and so replays a stale command); only SEND commands get through.
-- With IRQ=1 also "q n" at every non-zero write of the ISR's re-entry counter $FD9B: q 1 = a timer-A interrupt that
-- runs the sequencer, q 2 = one that came while the previous ISR was still running (the driver drops it).
-- SEQ="frames:keys,..." plays P1 inputs (U D L R a b c d, '-' = none) as tools/kof96/capture/record96.lua does.
-- PATCH="addr:hexbytes,..." writes bytes into the M1 ROM (region :cslot1:audiocpu, at addr and its reload at
-- addr+$10000) before the game runs: test songs in the free $2C56-$2DFF area (tools/kof98snd/testsong98.py).
local out = io.open(os.getenv("OUT"), "w")
do
  local reg = manager.machine.memory.regions[":cslot1:audiocpu"]
  for a, hex in string.gmatch(os.getenv("PATCH") or "", "(%x+):(%x+)") do
    local base = tonumber(a, 16)
    for i = 0, #hex / 2 - 1 do
      local b = tonumber(hex:sub(2 * i + 1, 2 * i + 2), 16)
      reg:write_u8(base + i, b); reg:write_u8(base + 0x10000 + i, b)
    end
  end
end
local port = manager.machine.ioport.ports[":edge:joy:JOY1"]
local F = {U = port.fields["P1 Up"], D = port.fields["P1 Down"], L = port.fields["P1 Left"], R = port.fields["P1 Right"],
           a = port.fields["P1 A"], b = port.fields["P1 B"], c = port.fields["P1 C"], d = port.fields["P1 D"]}
local seq = {}
for fr, inp in string.gmatch(os.getenv("SEQ") or "", "(%d+):([^,]+)") do seq[#seq + 1] = {tonumber(fr), inp} end
local si, left = 1, (seq[1] and seq[1][1] or math.huge)
local function apply()
  local e = seq[si]; local inp = e and e[2] or "-"
  for k, f in pairs(F) do f:set_value(string.find(inp, k, 1, true) and 1 or 0) end
end
apply()
local frames = tonumber(os.getenv("FRAMES") or "600")
local n, lastf = 0, -1
local addr = {0, 0}
local function mark() if lastf ~= n then out:write("f ", n, "\n"); lastf = n end end
local aio = manager.machine.devices[":audiocpu"].spaces["io"]
-- OUT (n),A puts A on the upper address lines: tap the whole I/O space, the port is the low byte
_G.ymtap = aio:install_write_tap(0x0000, 0xFFFF, "ym", function(offset, data, mask)
  local port = offset & 0xFF
  if port == 4 then addr[1] = data & 0xFF
  elseif port == 6 then addr[2] = data & 0xFF
  elseif port == 5 then mark(); out:write(string.format("a %02X %02X\n", addr[1], data & 0xFF))
  elseif port == 7 then mark(); out:write(string.format("b %02X %02X\n", addr[2], data & 0xFF)) end
  return data
end)
local block = tonumber(os.getenv("BLOCK") or "0")
local irqon = os.getenv("IRQ")
local allow = {}
if os.getenv("IRQ") or block > 0 then
  _G.irqtap = aio:install_read_tap(0x0000, 0xFFFF, "irq", function(offset, data, mask)
    local port = offset & 0xFF
    if port == 4 and irqon then out:write(string.format("i %02X\n", data & 0xFF)) end
    if port == 0 and block > 0 and n >= block then
      if allow[data & 0xFF] then allow[data & 0xFF] = nil else return 0x60 end
    end
    return data
  end)
end
if irqon then   -- the ISR's re-entry counter $FD9B: "q 1" = this timer-A interrupt runs the sequencer, "q 2" = nested (dropped)
  _G.nesttap = manager.machine.devices[":audiocpu"].spaces["program"]:install_write_tap(0xFD9B, 0xFD9B, "nest",
    function(offset, data, mask) if data ~= 0 then out:write(string.format("q %d\n", data)) end return data end)
end
local mp = manager.machine.devices[":maincpu"].spaces["program"]
_G.cmdtap = mp:install_write_tap(0x320000, 0x320001, "snd", function(offset, data, mask)
  mark(); out:write(string.format("c %04X %04X\n", data & 0xFFFF, mask & 0xFFFF)); return data
end)
_G.ymframe = emu.add_machine_frame_notifier(function()
  n = n + 1
  for fr, cmd in string.gmatch(os.getenv("SEND") or "", "(%d+):(%x+)") do   -- SEND="frame:hex,...": a sound command
    if tonumber(fr) == n then allow[tonumber(cmd, 16)] = true; mp:write_u8(0x320000, tonumber(cmd, 16)) end
  end
  left = left - 1
  if left <= 0 and seq[si] then si = si + 1; left = seq[si] and seq[si][1] or math.huge; apply() end
  if n >= frames then out:close(); manager.machine:exit() end
end)
