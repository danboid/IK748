/*
 * International Karate port - computer opponent (new code)
 */
#ifndef AI_H
#define AI_H
#include <uzebox.h>

void ai_reset(u8 level);          /* level 0 = easiest, rises with each bout won */
u8   ai_think(u8 me);             /* move request for fighter `me` this tick */
u8   ai_rand(void);

#endif
