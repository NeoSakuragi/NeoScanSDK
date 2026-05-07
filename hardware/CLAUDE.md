# Hardware — NeoCart FPGA Dev Cart

FPGA-based development cartridge for real MVS hardware. ECP5-25F FPGA + 4x SDRAM (128MB) + RP2040 USB loader.

## Structure

| Directory | What |
|-----------|------|
| `neocart/fpga/rtl/` | Verilog: neocart_top, prog_bus, cha_bus, sdram_ctrl, spi_slave, bus_snooper |
| `neocart/fpga/firmware/` | RP2040 USB bootloader + SPI loader |
| `neocart/adapter/` | Level-shift PCBs, CHA adapter, programming breakout |
| `neocart/production/` | Gerbers, BOM, placement files for JLCPCB |

## Important

Claude CANNOT design PCBs. Stick to: Verilog RTL, firmware C code, architecture docs, pin assignment tables, BOM spreadsheets. Do NOT attempt to generate KiCad files, place components, or route traces.

## Physical layout

MVS cart shell: screw side = PROG board, flat side = CHA board. Connector: EDAC 345-120-520-201 (2x60, 2.54mm pitch).

## JLCPCB conventions

Rotation offsets: +270° for SOIC packages, 0° for passives. Use JLCPCB parts API for stock checks.
