// Bus snooper — captures 68k bus transactions into a FIFO
//
// Every time the 68k reads or writes, we capture:
//   [7:0]  flags: {R/W, 0, 0, 0, addr[19:16]}
//   [7:0]  addr high byte [15:8]
//   [7:0]  addr low byte [7:0] (actually [8:1] since A0 not on bus)
//   [7:0]  data high [15:8]
//   [7:0]  data low [7:0]
//
// 5 bytes per transaction, streamed to RP2040 via SPI

module bus_snooper (
    input  wire        clk,
    input  wire        rst_n,

    // 68k bus (directly from PROG connector)
    input  wire [19:1] prog_addr,
    input  wire [15:0] prog_data,
    input  wire        prog_rw,
    input  wire        prog_romoe_n,

    // Output FIFO byte stream
    output reg   [7:0] out_byte,
    output reg         out_valid
);

    // Detect bus activity: ROMOE falling edge = start of access
    reg [1:0] romoe_sync;
    always @(posedge clk)
        romoe_sync <= {romoe_sync[0], prog_romoe_n};

    wire bus_active = ~romoe_sync[1];
    wire bus_start  = romoe_sync[1:0] == 2'b10; // falling edge

    // Capture state
    reg [2:0] emit_cnt;
    reg [19:1] cap_addr;
    reg [15:0] cap_data;
    reg        cap_rw;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            emit_cnt  <= 0;
            out_valid <= 0;
        end else begin
            out_valid <= 0;

            if (bus_start) begin
                cap_addr <= prog_addr;
                cap_data <= prog_data;
                cap_rw   <= prog_rw;
                emit_cnt <= 1;
            end

            if (emit_cnt > 0) begin
                out_valid <= 1;
                case (emit_cnt)
                    1: out_byte <= {cap_rw, 3'b0, cap_addr[19:16]};
                    2: out_byte <= cap_addr[15:8];
                    3: out_byte <= {cap_addr[7:1], 1'b0};
                    4: out_byte <= cap_data[15:8];
                    5: out_byte <= cap_data[7:0];
                endcase

                if (emit_cnt == 5)
                    emit_cnt <= 0;
                else
                    emit_cnt <= emit_cnt + 1;
            end
        end
    end

endmodule
