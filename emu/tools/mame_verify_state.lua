-- Verify: does the BIOS actually reach game code after frame 237?
-- Check frames 237-500 for PC entering game ROM area ($200000+)

local frame = 0
local found_game = false

local function check()
    frame = frame + 1
    if frame < 237 or found_game then return end

    local cpu = manager.machine.devices[":maincpu"]
    local st = cpu.state
    local pc = st["PC"].value
    local mem = cpu.spaces["program"]
    local fdae = mem:read_u8(0x10FDAE)
    local fd80 = mem:read_u8(0x10FD80)

    if frame <= 245 or frame % 60 == 0 then
        print(string.format("F%d PC=$%06X FDAE=%02X FD80=%02X", frame, pc, fdae, fd80))
    end

    -- Check if PC is in game ROM ($000000-$0FFFFF with bios_vec=0, or $200000+)
    if pc >= 0x200000 and pc < 0x300000 then
        print(string.format("*** GAME CODE REACHED at frame %d: PC=$%06X ***", frame, pc))
        print(string.format("  FDAE=%02X D0=%08X A5=%08X SP=%08X",
            fdae, st["D0"].value, st["A5"].value, st["SP"].value))
        found_game = true
    end

    -- Also check for PC < $100000 with bios_vec=0 (cart ROM mapped low)
    if pc < 0x100000 and pc > 0x400 then
        local v0 = mem:read_u16(0x000000)
        local vc = mem:read_u16(0xC00000)
        if v0 ~= vc then -- bios_vec=0
            print(string.format("*** GAME CODE (low) at frame %d: PC=$%06X ***", frame, pc))
            found_game = true
        end
    end

    if frame >= 600 then
        print("Reached frame 600 without game code entry")
        manager.machine:exit()
    end
end

emu.register_frame_done(check, "verify")
