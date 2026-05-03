local frame_count = 0
local shot = 0

emu.register_frame_done(function()
    frame_count = frame_count + 1
    if frame_count == 400 or frame_count == 408 or frame_count == 416 then
        manager.machine.video:snapshot()
        shot = shot + 1
    end
    if frame_count == 420 then
        manager.machine:exit()
    end
end)
