VERILATOR = verilator
IVERILOG = iverilog
VVP = vvp

ROM_HEX = rbff2_prom.hex
ROM_WORDS = 2621440

# Verilator build (full ROM, fast)
.PHONY: verilator test clean

verilator: obj_dir/Vprom_cart__ALL.a verilator_bridge.cpp
	g++ -std=c++17 -O2 -I obj_dir -I /usr/share/verilator/include \
		verilator_bridge.cpp \
		obj_dir/Vprom_cart__ALL.a \
		/usr/share/verilator/include/verilated.cpp \
		/usr/share/verilator/include/verilated_threads.cpp \
		-lpthread \
		-o cart_bridge_test
	@echo "Built cart_bridge_test"

obj_dir/Vprom_cart__ALL.a: prom_cart.v
	$(VERILATOR) --cc prom_cart.v \
		-GROM_WORDS=$(ROM_WORDS) \
		--top-module prom_cart \
		--Mdir obj_dir
	$(MAKE) -C obj_dir -f Vprom_cart.mk

# Run the Verilator test
test: verilator
	./cart_bridge_test

# Iverilog (tiny ROM only, for quick checks)
tiny: prom_cart.v prom_tiny_tb.v test_tiny.hex
	$(IVERILOG) -o prom_tiny_tb prom_cart.v prom_tiny_tb.v
	$(VVP) prom_tiny_tb

clean:
	rm -rf obj_dir prom_tiny_tb prom_small_tb cart_bridge_test *.vcd
