/*
 * Mode 748 configuration for the International Karate port test.
 */
#ifndef M74CFG_H
#define M74CFG_H

/* Fixed-address flash data (linker section .tiles, see Makefile).
** The converter puts the 256-byte recolour table first, then the ROM tiles. */
#define TILES_SECT         0xC000

#define M74_SPR_ENABLE     1
#define M74_MSK_ENABLE     0
#define M74_RECTB_OFF      TILES_SECT

/* RAM tiles for sprites: 0x0600 - 0x0EFF (72 tiles, below the palette buffer
** at 0x0F00). All C globals must end below 0x05A0 (Mode 4 buffer); the Makefile checks this. */
#define RT_BASE            48U
#define RT_MAX             72U

/* Mode 4's 96-byte line buffer, moved from its default 0x1020 (just below the
** main stack) to 0x05A0-0x05FF, so the main stack can use 0x1020-0x10FF. The
** deeper call chains of the sampled sound effects overflowed the default space. */
#define M74_M4_BUFFER      0x05A0

#endif
