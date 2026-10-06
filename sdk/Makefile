CC      = m68k-linux-gnu-gcc
AS      = m68k-linux-gnu-gcc
AR      = m68k-linux-gnu-ar
CFLAGS  = -m68000 -O2 -ffreestanding -nostdlib -fno-store-merging -Iinclude -Wall -MMD -MP   # -MMD: header changes rebuild the objects
# -fno-store-merging: GCC 15 merges byte stores at odd offsets into word / long moves even with -m68000 (-mstrict-align
# on): an address error on a real 68000
ASFLAGS = -m68000 -nostdlib

SRCS    = src/neo_palette.c src/neo_sprite.c src/neo_vblank.c src/neo_anim.c src/neo_input.c src/neo_fix.c src/neo_sound.c src/neo_bullet.c src/neo_string.c src/neo_backup.c src/neo_bank.c
OBJS    = $(SRCS:.c=.o)

all: lib/libneoscan.a lib/crt0.o

lib/libneoscan.a: $(OBJS)
	@mkdir -p lib
	$(AR) rcs $@ $^

lib/crt0.o: boot/crt0.s
	@mkdir -p lib
	$(AS) $(ASFLAGS) -c $< -o $@

src/%.o: src/%.c
	$(CC) $(CFLAGS) -Isrc -c $< -o $@

src/neo_string.o: CFLAGS += -fno-tree-loop-distribute-patterns   # memset must not compile into a call to memset

-include $(OBJS:.o=.d)

clean:
	rm -f $(OBJS) $(OBJS:.o=.d) lib/libneoscan.a lib/crt0.o

.PHONY: all clean
