-- Trace calendar I/O ($380000 reads and $3A00xx writes) during frames 245-260
local frame = 0
local f = nil
local trace_count = 0

local function trace()
    frame = frame + 1
    if frame < 244 then return end
    if frame > 260 then
        if f then f:close() end
        print("Calendar trace done: " .. trace_count .. " entries")
        manager.machine:exit()
        return
    end

    local cpu = manager.machine.devices[":maincpu"]
    local mem = cpu.spaces["program"]

    if not f then
        f = io.open("/tmp/mame_cal_trace.txt", "w")
    end

    -- Read $380000 to see current calendar state
    local val = mem:read_u8(0x380000)
    local tp = (val >> 6) & 1
    local dout = (val >> 7) & 1
    f:write(string.format("F%d PC=%06X $380000=%02X TP=%d DOUT=%d\n",
        frame, cpu.state["PC"].value, val, tp, dout))
    trace_count = trace_count + 1
end

emu.register_frame_done(trace, "cal_trace")
