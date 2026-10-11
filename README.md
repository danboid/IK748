# IK748 - International Karate C64 ported to Uzebox video mode 748

IK748 features rewritten game logic (main.c, fight.c, ai.c, hud.c, sfx.h) but requires graphic and sound
data to be ripped from the C64 version to build.

It currently lacks music. This may be added in the future.

Only 4 of the original 8 stages are included.

## Build

See IK748_BUILD.txt in the same directory as this README.

## Play

Title screen: left/right picks 1 PLAYER or 2 PLAYERS, Start (or A/B) begins.

- 1 player: pad 1 is white, the computer is red. Win a bout to go to the next stage against a
  faster, more aggressive opponent; lose and it's GAME OVER.
- 2 players: pad 1 white, pad 2 red.

Eight directions, each with and without fire (A/B/X/Y), give the sixteen moves. Pulling away
while the opponent strikes close by blocks; up+away turns round (fighters can pass each other,
as on the C64). Fire with the stick centred does nothing. A full point by a fighter who already
has a full point wins the bout.

Sound effects: the game's own six sampled effects, extracted from your copy by
export_moves.py and played on the inline mixer's PCM channel (SOUND_CHANNEL_5_ENABLE=1) at
the original rate, triggered by the C64's own rules (attack frames, after a point plus a
delayed second sample, falls in the knife round, each brick in the breaking round).
The samples are normalised to full scale, and the ones played on attack frames get extra
gain with soft clipping for more impact. Original synthesised patches cover what the C64
doesn't sample: block, bonus-round success, game over and the menu.

## Bonus rounds

One player: the breaking round after your 4th win, the knife round after your 9th.

Two players: the original fixed order of bouts and bonus rounds; each player takes
the bonus round in turn.

- Breaking round: wait behind the bricks; when the bubble says GO! press anything. The
  faster you react, the more bricks break (1-10): 100 points each, 2000 for all ten. As on
  the C64 a crack runs down the middle of the stack, one brick per break, from the top.
  Too late is TOO SLOW.

- Knife round: 10, 15 or 20 knives and other projectiles at the original heights and
  speeds; jump (up) or duck (down). A hit knocks you down. 100 points per projectile
  dodged (my assumption - the original's knife-round scoring isn't traced yet).

## Notes

- Sprites are redrawn only when they change, starting as soon as the last line is rendered;
  this fixed the flashing front foot (the last tile drawn used to miss the beam).
- The C64 credit row at the bottom is not shown (192 lines), for more blank time.
- Mode 4's line buffer is moved to 0x05A0 (m74cfg.h) so the main stack has 224 bytes;
  at the default 0x1020 the sound code's call depth overflowed into it and the picture
  went black. C64 globals must therefore end below 0x05A0 (the build checks).
