-- Test: capture state from game A at frame 237, then verify it's truly
-- game-independent by comparing with game B at the same frame.
-- If they match, the state is universal.

local frame = 0
local done = false

local function check()
    if done then return end
    frame = frame + 1
    if frame ~= 237 then return end
    done = true

    local cpu = manager.machine.devices[":maincpu"]
    local st = cpu.state
    local mem = cpu.spaces["program"]

    -- Print full state for manual comparison
    print(string.format("FRAME 237 STATE:"))
    print(string.format("  PC=%06X SR=%04X", st["PC"].value, st["SR"].value))
    print(string.format("  D0=%08X D1=%08X D2=%08X D3=%08X", st["D0"].value, st["D1"].value, st["D2"].value, st["D3"].value))
    print(string.format("  D4=%08X D5=%08X D6=%08X D7=%08X", st["D4"].value, st["D5"].value, st["D6"].value, st["D7"].value))
    print(string.format("  A0=%08X A1=%08X A2=%08X A3=%08X", st["A0"].value, st["A1"].value, st["A2"].value, st["A3"].value))
    print(string.format("  A4=%08X A5=%08X A6=%08X SP=%08X", st["A4"].value, st["A5"].value, st["A6"].value, st["SP"].value))

    -- Key BIOS variables
    print(string.format("  FD80=%02X FDAE=%02X FDAF=%02X",
        mem:read_u8(0x10FD80), mem:read_u8(0x10FDAE), mem:read_u8(0x10FDAF)))

    -- Check bios_vec: compare $000000 with $C00000
    local v0 = mem:read_u16(0x000000)
    local vc = mem:read_u16(0xC00000)
    print(string.format("  $000000=%04X $C00000=%04X bios_vec=%s", v0, vc, v0 == vc and "1" or "0"))

    -- Also check if game ROM is visible at $200000
    print(string.format("  $200000=%04X $200004=%04X $200122=%04X",
        mem:read_u16(0x200000), mem:read_u16(0x200004), mem:read_u16(0x200122)))

    manager.machine:exit()
end

emu.register_frame_done(check, "check237")
