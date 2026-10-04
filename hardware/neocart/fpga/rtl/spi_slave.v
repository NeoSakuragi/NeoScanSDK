// SPI slave — receives ROM data from RP2040
//
// Protocol:
//   Byte 0:    command (0x01=write, 0x02=read snoop)
//   Byte 1-3:  24-bit address (MSB first)
//   Byte 4-5:  16-bit data (for write)
//
// Write command: RP2040 sends address + data, FPGA stores in SDRAM
// Snoop read: FPGA sends next snoop FIFO entry to RP2040

module spi_slave (
    input  wire        clk,
    input  wire        rst_n,

    // SPI pins
    input  wire        sck,
    input  wire        mosi,
    output reg         miso,
    input  wire        cs_n,

    // Write port to SDRAM
    output reg         wr_en,
    output reg  [24:0] wr_addr,
    output reg  [15:0] wr_data,

    // Snoop FIFO read
    input  wire  [7:0] snoop_byte,
    input  wire        snoop_valid,
    output wire        irq
);

    // Sync SPI signals to system clock
    reg [2:0] sck_sync;
    reg [1:0] cs_sync;
    reg [1:0] mosi_sync;

    always @(posedge clk) begin
        sck_sync  <= {sck_sync[1:0], sck};
        cs_sync   <= {cs_sync[0], cs_n};
        mosi_sync <= {mosi_sync[0], mosi};
    end

    wire sck_rise = (sck_sync[2:1] == 2'b01);
    wire sck_fall = (sck_sync[2:1] == 2'b10);
    wire cs_active = ~cs_sync[1];

    // Shift register
    reg [7:0]  shift_in;
    reg [2:0]  bit_cnt;
    reg [3:0]  byte_cnt;
    reg        byte_ready;

    // Command state
    reg [7:0]  cmd;
    reg [23:0] addr_buf;
    reg [15:0] data_buf;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            bit_cnt    <= 0;
            byte_cnt   <= 0;
            byte_ready <= 0;
            wr_en      <= 0;
            cmd        <= 0;
        end else begin
            wr_en      <= 0;
            byte_ready <= 0;

            if (!cs_active) begin
                bit_cnt  <= 0;
                byte_cnt <= 0;
            end else if (sck_rise) begin
                shift_in <= {shift_in[6:0], mosi_sync[1]};
                bit_cnt  <= bit_cnt + 1;

                if (bit_cnt == 7) begin
                    byte_ready <= 1;
                    byte_cnt   <= byte_cnt + 1;

                    case (byte_cnt)
                        0: cmd <= {shift_in[6:0], mosi_sync[1]};
                        1: addr_buf[23:16] <= {shift_in[6:0], mosi_sync[1]};
                        2: addr_buf[15:8]  <= {shift_in[6:0], mosi_sync[1]};
                        3: addr_buf[7:0]   <= {shift_in[6:0], mosi_sync[1]};
                        4: data_buf[15:8]  <= {shift_in[6:0], mosi_sync[1]};
                        5: begin
                            data_buf[7:0] <= {shift_in[6:0], mosi_sync[1]};
                            if (cmd == 8'h01) begin
                                wr_en   <= 1;
                                wr_addr <= {1'b0, addr_buf};
                                wr_data <= {data_buf[15:8], shift_in[6:0], mosi_sync[1]};
                            end
                            // Auto-increment address for streaming
                            addr_buf <= addr_buf + 1;
                            byte_cnt <= 4; // loop back to data bytes
                        end
                    endcase
                end
            end

            // MISO: send snoop data on falling edge
            if (sck_fall && cs_active && cmd == 8'h02) begin
                miso <= snoop_byte[7 - bit_cnt];
            end
        end
    end

    assign irq = snoop_valid;

endmodule
