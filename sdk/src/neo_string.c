/* memset / memcpy: a freestanding gcc may emit calls to them for structure clears and copies (e.g. `*f = (T){ 0 }`),
 * even with -ffreestanding, and there is no C library on the Neo Geo. Plain byte loops; -fno-tree-loop-distribute-patterns
 * on this file keeps gcc from turning the loops back into calls to themselves. */
#include <stddef.h>

void *memset(void *d, int c, size_t n) {
    unsigned char *p = d;
    while (n--) *p++ = (unsigned char)c;
    return d;
}

void *memcpy(void *d, const void *s, size_t n) {
    unsigned char *p = d;
    const unsigned char *q = s;
    while (n--) *p++ = *q++;
    return d;
}
