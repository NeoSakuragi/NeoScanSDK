-- Dump complete Neo Geo machine state from MAME at frame 237
-- Output: binary file with CPU regs, WRAM, VRAM, palette, SRAM

local TARGET_FRAME = 237
local OUTPATH = os.getenv("MAME_STATE_FILE") or "/tmp/ngstate.bin"
local frame = 0
local done = false

local function dump_state()
    if done then return end
    frame = frame + 1
    if frame < TARGET_FRAME then return end
    done = true

    local cpu = manager.machine.devices[":maincpu"]
    local mem = cpu.spaces["program"]
    local st = cpu.state
    local f = io.open(OUTPATH, "wb")

    -- Header: "NGST" + frame number
    f:write("NGST")
    f:write(string.char(frame & 0xFF, (frame >> 8) & 0xFF, 0, 0))

    -- CPU registers: D0-D7, A0-A6, SP, PC, SR, USP (18 x 4 bytes = 72 bytes)
    local regs = {"D0","D1","D2","D3","D4","D5","D6","D7",
                  "A0","A1","A2","A3","A4","A5","A6","SP","PC","SR"}
    for _, name in ipairs(regs) do
        local v = st[name].value
        f:write(string.char(v & 0xFF, (v>>8) & 0xFF, (v>>16) & 0xFF, (v>>24) & 0xFF))
    end
    -- USP
    local usp = st["USP"].value
    f:write(string.char(usp & 0xFF, (usp>>8) & 0xFF, (usp>>16) & 0xFF, (usp>>24) & 0xFF))

    -- WRAM: 64KB from $100000
    print("Dumping WRAM...")
    for addr = 0x100000, 0x10FFFF do
        f:write(string.char(mem:read_u8(addr)))
    end

    -- Palette RAM: 8KB from $400000
    print("Dumping palette...")
    for addr = 0x400000, 0x401FFF do
        f:write(string.char(mem:read_u8(addr)))
    end

    -- SRAM: 64KB from $D00000
    print("Dumping SRAM...")
    for addr = 0xD00000, 0xD0FFFF do
        f:write(string.char(mem:read_u8(addr)))
    end

    -- VRAM: read through LSPC registers
    -- Save current state
    print("Dumping VRAM via LSPC...")
    -- Write mod=1
    mem:write_u16(0x3C0004, 1)
    -- Set address to 0
    mem:write_u16(0x3C0000, 0)
    -- Dummy read to prime latch
    mem:read_u16(0x3C0002)
    -- Read 65536 words
    for i = 0, 65535 do
        local v = mem:read_u16(0x3C0002)
        f:write(string.char(v & 0xFF, (v >> 8) & 0xFF))
    end

    -- System state: bios_vec (read from checking which ROM is at $000000)
    -- If $000000 reads as BIOS data → bios_vec=1, if cart data → bios_vec=0
    -- We can detect by checking if $000000 matches $C00000
    local v0 = mem:read_u16(0x000000)
    local vc = mem:read_u16(0xC00000)
    local bios_vec = (v0 == vc) and 1 or 0
    f:write(string.char(bios_vec, 0, 0, 0))

    f:close()
    print(string.format("State saved: frame %d -> %s (bios_vec=%d)", frame, OUTPATH, bios_vec))
    manager.machine:exit()
end

emu.register_frame_done(dump_state, "savestate")
print("Will dump state at frame " .. TARGET_FRAME)
