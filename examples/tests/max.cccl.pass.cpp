// CCCL-side reference test for cuda::std::max (BINARY, value-returning shape).
// Used as a few-shot example of the test we must migrate to ACCL.
#include <cuda/std/__algorithm/max.h>
#include <cassert>

int main(int, char**)
{
  assert(cuda::std::max(1, 2) == 2);
  assert(cuda::std::max(2, 1) == 2);
  assert(cuda::std::max(5.0f, 3.0f) == 5.0f);

  auto comp = [](int x, int y) { return x < y; };
  assert(cuda::std::max(10, 20, comp) == 20);
  return 0;
}
