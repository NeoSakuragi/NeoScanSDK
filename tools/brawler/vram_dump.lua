-- MAME: at frame DUMP_FRAME, write LSPC VRAM (words $0000-$85FF through the VRAMADDR / VRAMRW registers) to VRAM_OUT and
-- the current palette bank ($400000, 4096 words) to PAL_OUT, both big-endian words, then quit.
-- mame kof98 -state c4 -autoboot_script vram_dump.lua -noplugin cart_bridge -video none -sound none -nothrottle
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local frame, target = 0, tonumber(os.getenv("DUMP_FRAME") or "20")
local function words(path, n, read)
  local f = io.open(path, "wb")
  for i = 0, n - 1 do local w = read(i); f:write(string.char((w >> 8) & 255, w & 255)) end
  f:close()
end
emu.register_frame_done(function()
  frame = frame + 1
  if frame ~= target then return end
  words(os.getenv("VRAM_OUT"), 0x8600, function(a) mem:write_u16(0x3C0000, a); return mem:read_u16(0x3C0000) end)
  words(os.getenv("PAL_OUT"), 0x1000, function(i) return mem:read_u16(0x400000 + i * 2) end)
  manager.machine:exit()
end)
