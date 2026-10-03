-- KOF98 per-fighter starting state (run with -noplugin cart_bridge): from state "vs" (Kyo vs Yuri), swaps P1 to CID
-- (team ids $10A84E-50 + P1 health 1, P2 hits; the next round loads the fighter), then earns power stocks the game's
-- way (P1 hits P2 with C for ~1000 frames: poking the stock bytes did not make supers available), then puts both
-- fighters in place (P1 x $100, P2 x $260, P2 life full, timer 59) and saves state "c<CID>". Captures reload it
-- before every try, which restores stocks, positions, timer and life. EX=1: the EX version (team record +$10 bit per
-- member -> object +$1D6, which picks the second command list), saved as "c<CID>x".
local mem = manager.machine.devices[":maincpu"].spaces["program"]; local n = 0
local F = manager.machine.ioport.ports[":edge:joy:JOY1"].fields
local G = manager.machine.ioport.ports[":edge:joy:JOY2"].fields
local cid = tonumber(os.getenv("CID"))
local LOAD, FILL_END = tonumber(os.getenv("LOAD") or "1400"), tonumber(os.getenv("FILL_END") or "2500")
local function life(base, v) for _, o in ipairs({0x138, 0x13E, 0x146, 0x150}) do mem:write_u16(base + o, v) end end
_G.prep98 = emu.add_machine_frame_notifier(function()
  n = n + 1
  if n == 2 then life(0x108100, 1); for a = 0x10A84E, 0x10A850 do mem:write_u8(a, cid) end
    if os.getenv("EX") == "1" then mem:write_u8(0x10A85A, 7) end end      -- team record +$10: EX bit per member
  G["P2 Left"]:set_value((n > 20 and n < 80) and 1 or 0); G["P2 C"]:set_value((n > 85 and n < 88) and 1 or 0)
  local c = 0
  if n >= LOAD and n < FILL_END then
    if n % 40 == 0 then mem:write_u16(0x108118, 0x01C0); mem:write_u16(0x108318, 0x01E8); mem:write_u8(0x10A83A, 0x59); life(0x108300, 103) end
    if n % 40 < 3 then c = 1 end
  end
  F["P1 C"]:set_value(c)
  if n == FILL_END + 30 then mem:write_u16(0x108118, 0x0100); mem:write_u16(0x108318, 0x0260); mem:write_u8(0x10A83A, 0x59); life(0x108300, 103) end
  if n == FILL_END + 60 then
    print(string.format("P1 id %d state %d stock byte %d", mem:read_u16(0x108170), mem:read_u16(0x108172), mem:read_u8(0x108208)))
    manager.machine:save("c" .. cid .. (os.getenv("EX") == "1" and "x" or ""))
  end
  if n == FILL_END + 62 then manager.machine:exit() end
end)
