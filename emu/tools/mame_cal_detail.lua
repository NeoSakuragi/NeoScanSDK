-- Trace $380000 reads and $3A00xx writes WITHIN frame 245 using watchpoints
local frame = 0
local f = nil
local capturing = false

local function on_frame()
    frame = frame + 1
    if frame == 244 then
        capturing = true
        f = io.open("/tmp/mame_cal_detail.txt", "w")
        -- Set up memory read/write hooks
        local cpu = manager.machine.devices[":maincpu"]
        local dbg = cpu:debug()

        -- Watchpoint on $380000 reads (calendar read)
        dbg:wpset(emu.memory_space(cpu, "program"), "r", 0x380000, 1,
            string.format("wpdata = %d", 0))
        -- Watchpoint on $3A0000 writes (calendar write)
        dbg:wpset(emu.memory_space(cpu, "program"), "w", 0x3A0000, 0x40,
            string.format("wpdata = %d", 0))

        print("Watchpoints set for frame 245")
    end
    if frame == 246 then
        if f then
            f:write("DONE\n")
            f:close()
        end
        print("Trace complete")
        manager.machine:exit()
    end
end

emu.register_frame_done(on_frame, "cal_detail")
