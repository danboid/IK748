/*
 * International Karate port - HUD drawn into the mode 4 bitmap (SPI RAM)
 *
 * Text cells are 4 pixels wide (3x5 glyphs), 40 cells across the C64 area.
 * Call only right after vsync, before the frame starts streaming SPI RAM.
 */
#ifndef HUD_H
#define HUD_H
#include <uzebox.h>

#define HUD_MARK_FULL   '#'
#define HUD_MARK_HALF   '%'
#define HUD_MARK_EMPTY  '$'

void hud_init(u32 bitmap_spi);                           /* set stage bitmap, clear HUD lines */
void hud_text(u8 col, u8 y, const char* s, u8 colour);  /* RAM string */
void hud_text_P(u8 col, u8 y, const char* s, u8 colour);/* flash string */
void hud_blank(u8 col, u8 y, u8 len);                   /* clear len cells (5 lines) */

#endif
