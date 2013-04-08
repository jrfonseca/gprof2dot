/* val3.c  2012-12-20 14:23
   Reference executable for validating application profiling tools.
   val3:  mutually recursive functions.

   With default values of FN1LOOP and FN2LOOP, the expected distribution
   of time is approximately
     main    total 100 % self  0 %
     cycfn2  total 100 % self 67 %
     cycfn1  total  67 % self 33 %
   resulting from the following call chains and proportions of samples:
     2  main->cycfn2
     1  main->cycfn2->cycfn1
     2  main->cycfn2->cycfn1->cycfn2
     1  main->cycfn2->cycfn1->cycfn2->cycfn1

   Language -std=gnu99 (with gcc-specific attributes).
   Original versions tested:  gcc 4.7.2.
*/

// Configurable FN1LOOP:  how many busy-work iterations in cycfn1.
#ifndef FN1LOOP
#define FN1LOOP 100000000
#endif

// Configurable FN2LOOP:  how many busy-work iterations in cycfn2.
#ifndef FN2LOOP
#define FN2LOOP (FN1LOOP*2)
#endif

#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdbool.h>

uint64_t accumulator=1;
double   adder=0;

__attribute__((noinline,optimize("no-optimize-sibling-calls")))
void cycfn2 (bool leaf);

__attribute__((noinline,optimize("no-optimize-sibling-calls")))
void cycfn1 (bool leaf) {
  for (uint64_t looper=0; looper<FN1LOOP; ++looper)
    adder += M_PI*3, accumulator = accumulator*3 + adder;
  if (!leaf)
    cycfn2 (true);
}

void cycfn2 (bool leaf) {
  for (uint64_t looper=0; looper<FN2LOOP; ++looper)
    adder += M_PI*3, accumulator = accumulator*3 + adder;
  cycfn1 (leaf);
}

int main() {
  cycfn2 (false);
  printf ("%" PRIu64 " %f\n", accumulator, adder);
  return 0;
}
