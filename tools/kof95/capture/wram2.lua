-- Same inputs/pokes as record.lua would need are not required here: P1 health is poked to 1, P2 hits, and work RAM is dumped at frames listed in AT.
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local p2 = manager.machine.ioport.ports[":edge:joy:JOY2"]
local L, C = p2.fields["P2 Left"], p2.fields["P2 C"]
local at = {}; for v in string.gmatch(os.getenv("AT"), "%d+") do at[tonumber(v)] = true end
local n = 0
emu.register_frame_done(function()
  n = n + 1
  if n == 2 then for _, a in ipairs({0x108220, 0x108222, 0x10824C}) do mem:write_u16(a, 1) end end
  L:set_value((n >= 20 and n < 65) and 1 or 0); C:set_value((n >= 70 and n < 73) and 1 or 0)
  if at[n] then
    local f = io.open(os.getenv("OUT") .. n .. ".bin", "wb")
    for a = 0x100000, 0x10FFFF do f:write(string.char(mem:read_u8(a))) end
    f:close()
  end
  if n > 720 then manager.machine:exit() end
end)
