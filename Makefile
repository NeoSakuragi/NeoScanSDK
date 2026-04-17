all: sdk examples

sdk:
	$(MAKE) -C sdk

examples: sdk
	$(MAKE) -C examples/hello_neo

clean:
	$(MAKE) -C sdk clean
	$(MAKE) -C examples/hello_neo clean

.PHONY: all sdk examples clean
