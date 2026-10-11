/*
 * International Karate port - sound effects (original patches)
 * Waves: 0 sine, 1 saw, 2 triangle, 3/4/5 square 25/50/75 %.
 * The six SFX_C64_* effects are the game's own samples (export_moves.py).
 */
#ifndef SFX_H
#define SFX_H
#include <stddef.h>

#include "ik_sfx.h"     /* the game's own sampled effects, from export_moves.py */

/* The six sampled effects play on the inline mixer's PCM channel (channel 5,
** SOUND_CHANNEL_5_ENABLE=1), one at a time as on the C64. The synthesised patches cover events the C64 doesn't voice. */
enum { SFX_C64_0, SFX_C64_1, SFX_C64_2, SFX_C64_3, SFX_C64_4, SFX_C64_5,
       SFX_BLOCK, SFX_WIN, SFX_LOSE, SFX_BLIP, SFX_BEGIN };

static const char p_block[] PROGMEM = {       /* dry click */
	0,PC_WAVE,3, 0,PC_PITCH,84, 0,PC_ENV_SPEED,-60, 3,PC_NOTE_CUT,0, 0,PATCH_END };
static const char p_win[] PROGMEM = {         /* rising arpeggio */
	0,PC_WAVE,2, 0,PC_ENV_SPEED,-2, 0,PC_PITCH,60, 7,PC_PITCH,64, 7,PC_PITCH,67,
	7,PC_PITCH,72, 7,PC_PITCH,76, 7,PC_PITCH,79, 30,PC_NOTE_CUT,0, 0,PATCH_END };
static const char p_lose[] PROGMEM = {        /* falling minor line */
	0,PC_WAVE,2, 0,PC_ENV_SPEED,-2, 0,PC_PITCH,67, 10,PC_PITCH,63, 10,PC_PITCH,60,
	10,PC_PITCH,55, 40,PC_NOTE_CUT,0, 0,PATCH_END };
static const char p_blip[] PROGMEM = {
	0,PC_WAVE,4, 0,PC_PITCH,76, 0,PC_ENV_SPEED,-40, 4,PC_NOTE_CUT,0, 0,PATCH_END };
static const char p_begin[] PROGMEM = {       /* low gong-like tone */
	0,PC_WAVE,0, 0,PC_PITCH,48, 0,PC_ENV_SPEED,-3, 0,PC_TREMOLO_LEVEL,0x40,
	0,PC_TREMOLO_RATE,24, 50,PC_NOTE_CUT,0, 0,PATCH_END };

static const char p_pcm0[] PROGMEM = { 0,PC_PITCH,SFX_PCM_NOTE, SFX_PCM_TICKS_0,PC_NOTE_CUT,0, 0,PATCH_END };
static const char p_pcm1[] PROGMEM = { 0,PC_PITCH,SFX_PCM_NOTE, SFX_PCM_TICKS_1,PC_NOTE_CUT,0, 0,PATCH_END };
static const char p_pcm2[] PROGMEM = { 0,PC_PITCH,SFX_PCM_NOTE, SFX_PCM_TICKS_2,PC_NOTE_CUT,0, 0,PATCH_END };
static const char p_pcm3[] PROGMEM = { 0,PC_PITCH,SFX_PCM_NOTE, SFX_PCM_TICKS_3,PC_NOTE_CUT,0, 0,PATCH_END };
static const char p_pcm4[] PROGMEM = { 0,PC_PITCH,SFX_PCM_NOTE, SFX_PCM_TICKS_4,PC_NOTE_CUT,0, 0,PATCH_END };
static const char p_pcm5[] PROGMEM = { 0,PC_PITCH,SFX_PCM_NOTE, SFX_PCM_TICKS_5,PC_NOTE_CUT,0, 0,PATCH_END };

static const struct PatchStruct sfx_patches[] PROGMEM = {
	{2,sfx_pcm_0,p_pcm0,SFX_PCM_LEN_0,SFX_PCM_LEN_0+64}, {2,sfx_pcm_1,p_pcm1,SFX_PCM_LEN_1,SFX_PCM_LEN_1+64},
	{2,sfx_pcm_2,p_pcm2,SFX_PCM_LEN_2,SFX_PCM_LEN_2+64}, {2,sfx_pcm_3,p_pcm3,SFX_PCM_LEN_3,SFX_PCM_LEN_3+64},
	{2,sfx_pcm_4,p_pcm4,SFX_PCM_LEN_4,SFX_PCM_LEN_4+64}, {2,sfx_pcm_5,p_pcm5,SFX_PCM_LEN_5,SFX_PCM_LEN_5+64},
	{0,NULL,p_block,0,0}, {0,NULL,p_win,0,0}, {0,NULL,p_lose,0,0},
	{0,NULL,p_blip,0,0},  {0,NULL,p_begin,0,0},
};

#endif
