CC      = m68k-linux-gnu-gcc
AS      = m68k-linux-gnu-gcc
AR      = m68k-linux-gnu-ar
CFLAGS  = -m68000 -O2 -ffreestanding -nostdlib -Iinclude -Wall
ASFLAGS = -m68000 -nostdlib

SRCS    = src/neo_palette.c src/neo_sprite.c src/neo_vblank.c src/neo_anim.c src/neo_input.c src/neo_fix.c src/neo_sound.c src/neo_bullet.c
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

clean:
	rm -f $(OBJS) lib/libneoscan.a lib/crt0.o

.PHONY: all clean
