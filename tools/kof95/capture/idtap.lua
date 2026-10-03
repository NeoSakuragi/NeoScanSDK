-- P1 health -> 1, P2 hits; logs writes to P1 object +$70/$71 (table id / character id) with PC across the round change.
local cpu = manager.machine.devices[":maincpu"]; local mem = cpu.spaces["program"]
local p2 = manager.machine.ioport.ports[":edge:joy:JOY2"]
local L, C = p2.fields["P2 Left"], p2.fields["P2 C"]
local out = io.open(os.getenv("OUT"), "w"); local n = 0
local tap = mem:install_write_tap(0x108170, 0x108171, "id", function(offset, data, mask)
  out:write(string.format("%d %06X %06X %04X %04X A0=%08X A1=%08X D0=%08X\n", n, cpu.state["PC"].value, offset, data, mask,
    cpu.state["A0"].value, cpu.state["A1"].value, cpu.state["D0"].value))
end)
emu.register_frame_done(function()
  n = n + 1
  if n == 2 then for _, a in ipairs({0x108220, 0x108222, 0x10824C}) do mem:write_u16(a, 1) end end
  L:set_value((n >= 20 and n < 65) and 1 or 0); C:set_value((n >= 70 and n < 73) and 1 or 0)
  if n > 700 then out:close(); tap:remove(); manager.machine:exit() end
end)
