-- MAME Lua: dump CPU + WRAM state per frame for Neo Geo BIOS analysis
-- Env: MAME_DUMP_FILE, MAME_DUMP_FRAMES (default 600)

local outpath = os.getenv("MAME_DUMP_FILE") or "/tmp/mame_dump.txt"
local max_frames = tonumber(os.getenv("MAME_DUMP_FRAMES")) or 600
local frame = 0
local file = nil

local function do_dump()
    if not file then
        file = io.open(outpath, "w")
        if not file then print("DUMP ERROR: can't open " .. outpath); return end
    end

    frame = frame + 1
    local cpu = manager.machine.devices[":maincpu"]
    if not cpu then return end

    local st = cpu.state
    local mem = cpu.spaces["program"]

    file:write(string.format("F%04d PC=%06X SR=%04X D0=%08X D1=%08X D2=%08X D3=%08X D4=%08X D5=%08X D6=%08X D7=%08X A0=%08X A1=%08X A2=%08X A3=%08X A4=%08X A5=%08X A6=%08X SP=%08X\n",
        frame,
        st["PC"].value, st["SR"].value,
        st["D0"].value, st["D1"].value, st["D2"].value, st["D3"].value,
        st["D4"].value, st["D5"].value, st["D6"].value, st["D7"].value,
        st["A0"].value, st["A1"].value, st["A2"].value, st["A3"].value,
        st["A4"].value, st["A5"].value, st["A6"].value, st["SP"].value))

    -- BIOS variables $10FD00-$10FDFF
    local wram_fd = {}
    for i = 0, 255 do
        wram_fd[i+1] = string.format("%02X", mem:read_u8(0x10FD00 + i))
    end
    file:write("FD:" .. table.concat(wram_fd) .. "\n")

    -- Game WRAM $100000-$1000FF
    local wram_00 = {}
    for i = 0, 255 do
        wram_00[i+1] = string.format("%02X", mem:read_u8(0x100000 + i))
    end
    file:write("W0:" .. table.concat(wram_00) .. "\n")

    if frame >= max_frames then
        file:write("DONE\n")
        file:close()
        print(string.format("Dump: %d frames -> %s", frame, outpath))
        manager.machine:exit()
    end
end

emu.register_frame_done(do_dump, "frame_dump")
print("mame_dump: " .. max_frames .. " frames -> " .. outpath)
