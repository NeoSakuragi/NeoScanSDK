-- Take a screenshot after the BIOS screen passes (~350 frames) and exit
local frame_count = 0
local screenshot_taken = false

emu.register_frame_done(function()
    frame_count = frame_count + 1
    if frame_count == 400 and not screenshot_taken then
        emu.print_verbose("Taking screenshot at frame " .. frame_count)
        manager.machine.video:snapshot()
        screenshot_taken = true
    end
    if frame_count == 410 then
        manager.machine:exit()
    end
end)
