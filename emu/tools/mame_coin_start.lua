-- Insert coin and press start, then check if game code is reached
local frame = 0
local found_game = false
local coin_port, start_port

local function do_frame()
    frame = frame + 1

    -- Find input ports on first frame
    if frame == 1 then
        for name, port in pairs(manager.machine.ioport.ports) do
            for fname, field in pairs(port.fields) do
                if fname:find("Coin") then
                    print("Found coin: " .. name .. " / " .. fname)
                    coin_port = field
                end
                if fname:find("1 Start") or fname:find("Player 1 Start") then
                    print("Found start: " .. name .. " / " .. fname)
                    start_port = field
                end
            end
        end
    end

    -- Inject coin at frame 350
    if coin_port and frame >= 350 and frame <= 355 then
        coin_port:set_value(1)
    end

    -- Inject start at frame 400
    if start_port and frame >= 400 and frame <= 405 then
        start_port:set_value(1)
    end

    -- Track state
    local cpu = manager.machine.devices[":maincpu"]
    local st = cpu.state
    local pc = st["PC"].value
    local mem = cpu.spaces["program"]
    local fdae = mem:read_u8(0x10FDAE)

    if frame == 237 or frame == 300 or frame == 350 or frame == 400 or frame == 410 or
       frame == 420 or frame == 430 or frame == 450 or frame == 500 or frame == 600 or
       frame == 700 or frame == 800 then
        print(string.format("F%d PC=$%06X FDAE=%02X", frame, pc, fdae))
    end

    if not found_game and (pc >= 0x200000 and pc < 0x300000) then
        print(string.format("*** GAME CODE at F%d: PC=$%06X FDAE=%02X ***", frame, pc, fdae))
        found_game = true
    end

    if not found_game and pc < 0x100000 and pc > 0x1000 then
        local v0 = mem:read_u16(0x000000)
        local vc = mem:read_u16(0xC00000)
        if v0 ~= vc then
            print(string.format("*** GAME CODE (low map) at F%d: PC=$%06X FDAE=%02X ***", frame, pc, fdae))
            found_game = true
        end
    end

    if frame >= 900 then
        if not found_game then print("No game code reached in 900 frames") end
        manager.machine:exit()
    end
end

emu.register_frame_done(do_frame, "coin_start")
