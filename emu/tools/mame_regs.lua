-- Quick script to discover register names
local function dump_regs()
    local cpu = manager.machine.devices[":maincpu"]
    if not cpu then print("No CPU"); return end
    print("=== Available registers ===")
    for k, v in pairs(cpu.state) do
        print(string.format("  '%s' = %08X", k, v.value))
    end
    manager.machine:exit()
end

emu.register_frame_done(dump_regs, "reg_discover")
