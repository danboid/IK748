/*
 * International Karate port - fight rules (moves, input, movement, hits)
 */
#ifndef FIGHT_H
#define FIGHT_H

#include <stdbool.h>
#include <avr/pgmspace.h>
#include <uzebox.h>

/* Positions are in C64 multicolour pixels, as used by the move tables. */
typedef struct {
	u8  x;          /* left edge of the 36-pixel fighter box */
	u8  face;       /* 0 = facing right, 1 = facing left */
	u8  turned;     /* turned during the current move (affects input mirroring) */
	u8  move;       /* current move */
	u8  step;       /* current step (index into the step tables) */
	u8  next;       /* step to show on the next tick */
	u8  frame;      /* C64 frame number of the current step */
	u8  req;        /* move requested by input */
	u8  held;       /* input still matches the current move */
	u8  hold;       /* ticks spent holding at a chain point */
	u8  rev;        /* playing the move backwards (stick released at a hold point) */
	u8  holdpt;     /* current step is a hold point */
	u8  atk;        /* current step is a strike step */
	u8  fallen;     /* stopped on the last step of a knockdown / victory move */
	u8  sflags;     /* flags of the current step (the C64's sound rules use them) */
	u8  points;     /* half points this bout (capped at 5) */
	u16 score;      /* in hundreds */
} fighter_t;

typedef struct {
	u8   attacker;
	bool full;      /* full point (else half point) */
	u8   react;     /* move the victim is forced into */
	u8   score;     /* score to add, in hundreds */
	u8   call;      /* referee call / sound id (unused for now) */
} hit_t;

#define MOVE_STAND    0U
#define MOVE_TURN     8U     /* up + away */
#define MOVE_BLOCK   20U
#define MOVE_VICTORY 32U

typedef struct {
	u8 move;        /* joystick move containing a strike */
	u8 strike;      /* strike index */
	u8 steps;       /* steps from the start of the move to the strike */
	s8 dx;          /* travel before a turn (positive = towards the starting facing) */
	s8 dx2;         /* travel after the turn (towards the new facing) */
	u8 turn;        /* the move turns the fighter before the strike */
} atk_info_t;

extern atk_info_t atk_list[16];
extern u8         atk_count;

extern fighter_t fgt[2];
extern u8        fgt_front;     /* fighter drawn in front */

void fight_place(void);                     /* both fighters to their starting marks */
void fight_start_move(u8 i, u8 m);
void fight_input(u8 i, u16 pad);            /* pad -> requested move */
void fight_tick(u8 i);                      /* advance one animation step */
bool fight_hit_test(hit_t* h);              /* true if a strike scored this tick */
void fight_init(void);                      /* build the attack catalogue */
u8   fight_rel(u8 p, u8* dist);             /* relative position code, distance/4 */
u8   fight_strike_eval(u8 a, u8 ax, u8 aface, u8 y, hit_t* h);  /* 0 miss, 1 half, 2 full */
s8   fight_move_dx(u8 m);                   /* total travel of a move */
bool fight_is_strike_frame(u8 frame);

#endif
