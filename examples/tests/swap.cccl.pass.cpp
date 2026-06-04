// CCCL-side reference test for cuda::std::swap (IN-PLACE, void-returning shape).
// Used as a few-shot example: swap is NOT a binary value-returning op, so its
// migrated test must exercise the in-place exchange, not "auto out = swap(a,b)".
#include <cuda/std/__algorithm/swap.h>
#include <cassert>

int main(int, char**)
{
  int a = 1;
  int b = 2;
  cuda::std::swap(a, b);
  assert(a == 2);
  assert(b == 1);

  float x = 3.5f;
  float y = -1.0f;
  cuda::std::swap(x, y);
  assert(x == -1.0f);
  assert(y == 3.5f);
  return 0;
}
