// NeoCart FPGA — Top-level module
// Lattice ECP5-25, BGA-256
//
// Serves all Neo Geo ROM types from a single 32MB SDRAM:
//   PROG bus: P ROM (68k program), V ROMs (ADPCM samples)
//   CHA bus:  C ROMs (sprites), S ROM (fix layer), M ROM (Z80 sound)
//
// RP2040 loads ROM data into SDRAM over SPI.
// Bus snooper captures 68k transactions for debugging.

module neocart_top (
    // ─── Clock ───
    input wire clk_12m,             // 12MHz crystal → PLL → 100MHz

    // ─── PROG bus (CTRG2) — directly on board ───
    input  wire [19:1] prog_addr,   // 68k address A1-A19
    inout  wire [15:0] prog_data,   // 68k data D0-D15 (active bidirectional)
    input  wire        prog_romoe,  // P ROM output enable (active low)
    input  wire        prog_romoeu, // upper byte enable
    input  wire        prog_romoel, // lower byte enable
    input  wire        prog_rw,     // 68k R/W (1=read, 0=write)

    // V ROM bus (shared on CTRG2)
    input  wire [23:0] vrom_addr,   // V ROM address (SDRA/SDPA lines)
    inout  wire  [7:0] vrom_data,   // V ROM data (SDPAD lines)
    input  wire        vrom_oe,     // V ROM output enable (SDROE)

    // ─── CHA bus (CTRG1) — via FFC cable ───
    input  wire [23:0] crom_addr,   // C ROM address (P0-P23 from LSPC)
    output wire [31:0] crom_data,   // C ROM data (CR0-CR31)
    input  wire        crom_pck1b,  // C ROM clock 1 (active low)
    input  wire        crom_pck2b,  // C ROM clock 2 (active low)

    input  wire [15:0] srom_addr,   // S ROM address (SDA0-SDA15)
    output wire  [7:0] srom_data,   // S ROM data (SDD0-SDD7)
    input  wire        srom_oe,     // S ROM read (SDMRD, active low)

    input  wire [16:0] mrom_addr,   // M ROM address (from Z80)
    inout  wire  [7:0] mrom_data,   // M ROM data
    input  wire        mrom_oe,     // M ROM output enable

    // ─── SDRAM (IS42S16320D) ───
    output wire        sdram_clk,
    output wire        sdram_cke,
    output wire        sdram_cs_n,
    output wire        sdram_ras_n,
    output wire        sdram_cas_n,
    output wire        sdram_we_n,
    output wire  [1:0] sdram_ba,
    output wire [12:0] sdram_addr,
    inout  wire [15:0] sdram_dq,
    output wire  [1:0] sdram_dqm,

    // ─── SPI slave (from RP2040) ───
    input  wire        spi_sck,
    input  wire        spi_mosi,
    output wire        spi_miso,
    input  wire        spi_cs_n,
    output wire        spi_irq,     // snoop data ready

    // ─── Status ───
    output wire        led
);

    // ─── Clock generation ───
    wire clk_100m;
    wire clk_locked;

    clk_pll pll (
        .clk_in(clk_12m),
        .clk_out(clk_100m),
        .locked(clk_locked)
    );

    assign sdram_clk = clk_100m;

    // ─── SDRAM controller (multi-port) ───
    // Port 0: PROG bus reads (P ROM + V ROM)
    // Port 1: CHA bus reads (C ROM + S ROM + M ROM)
    // Port 2: SPI writes (loading ROM data)
    // Port 3: Snoop writes (bus trace capture)

    wire        port0_req;
    wire [24:0] port0_addr;
    wire [15:0] port0_rdata;
    wire        port0_ready;

    wire        port1_req;
    wire [24:0] port1_addr;
    wire [15:0] port1_rdata;
    wire        port1_ready;

    wire        port2_req;
    wire        port2_we;
    wire [24:0] port2_addr;
    wire [15:0] port2_wdata;
    wire        port2_ready;

    sdram_ctrl sdram (
        .clk(clk_100m),
        .rst_n(clk_locked),

        // Physical pins
        .sd_cke(sdram_cke),
        .sd_cs_n(sdram_cs_n),
        .sd_ras_n(sdram_ras_n),
        .sd_cas_n(sdram_cas_n),
        .sd_we_n(sdram_we_n),
        .sd_ba(sdram_ba),
        .sd_addr(sdram_addr),
        .sd_dq(sdram_dq),
        .sd_dqm(sdram_dqm),

        // Port 0: PROG reads
        .p0_req(port0_req),
        .p0_addr(port0_addr),
        .p0_rdata(port0_rdata),
        .p0_ready(port0_ready),

        // Port 1: CHA reads
        .p1_req(port1_req),
        .p1_addr(port1_addr),
        .p1_rdata(port1_rdata),
        .p1_ready(port1_ready),

        // Port 2: SPI writes (loading)
        .p2_req(port2_req),
        .p2_we(port2_we),
        .p2_addr(port2_addr),
        .p2_wdata(port2_wdata),
        .p2_ready(port2_ready)
    );

    // ─── PROG bus interface ───
    prog_bus prog (
        .clk(clk_100m),
        .rst_n(clk_locked),

        // Neo Geo bus
        .addr(prog_addr),
        .data(prog_data),
        .romoe_n(prog_romoe),
        .romoeu_n(prog_romoeu),
        .romoel_n(prog_romoel),
        .rw(prog_rw),
        .vrom_addr(vrom_addr),
        .vrom_data(vrom_data),
        .vrom_oe_n(vrom_oe),

        // SDRAM port 0
        .mem_req(port0_req),
        .mem_addr(port0_addr),
        .mem_rdata(port0_rdata),
        .mem_ready(port0_ready)
    );

    // ─── CHA bus interface ───
    cha_bus cha (
        .clk(clk_100m),
        .rst_n(clk_locked),

        // Neo Geo bus
        .crom_addr(crom_addr),
        .crom_data(crom_data),
        .pck1b(crom_pck1b),
        .pck2b(crom_pck2b),
        .srom_addr(srom_addr),
        .srom_data(srom_data),
        .srom_oe_n(srom_oe),
        .mrom_addr(mrom_addr),
        .mrom_data(mrom_data),
        .mrom_oe_n(mrom_oe),

        // SDRAM port 1
        .mem_req(port1_req),
        .mem_addr(port1_addr),
        .mem_rdata(port1_rdata),
        .mem_ready(port1_ready)
    );

    // ─── SPI slave (RP2040 interface) ───
    wire        spi_wr_en;
    wire [24:0] spi_wr_addr;
    wire [15:0] spi_wr_data;
    wire  [7:0] snoop_byte;
    wire        snoop_valid;

    spi_slave spi (
        .clk(clk_100m),
        .rst_n(clk_locked),

        .sck(spi_sck),
        .mosi(spi_mosi),
        .miso(spi_miso),
        .cs_n(spi_cs_n),

        .wr_en(spi_wr_en),
        .wr_addr(spi_wr_addr),
        .wr_data(spi_wr_data),

        .snoop_byte(snoop_byte),
        .snoop_valid(snoop_valid),
        .irq(spi_irq)
    );

    assign port2_req   = spi_wr_en;
    assign port2_we    = 1'b1;
    assign port2_addr  = spi_wr_addr;
    assign port2_wdata = spi_wr_data;

    // ─── Bus snooper ───
    bus_snooper snooper (
        .clk(clk_100m),
        .rst_n(clk_locked),

        .prog_addr(prog_addr),
        .prog_data(prog_data),
        .prog_rw(prog_rw),
        .prog_romoe_n(prog_romoe),

        .out_byte(snoop_byte),
        .out_valid(snoop_valid)
    );

    // Heartbeat LED
    reg [23:0] led_cnt;
    always @(posedge clk_100m)
        led_cnt <= led_cnt + 1;
    assign led = led_cnt[23];

endmodule
