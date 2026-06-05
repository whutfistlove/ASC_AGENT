#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_QUAD_FANOUT_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_QUAD_FANOUT_H_

#include "ascend/std/__config"

#if defined(__CCE__)
#define ASCEND_DEVICE_CODE
#endif

_ASCEND_STD_BEGIN

// Synthetic migration test operator:
//   four scalar inputs, five output references, void return.
//
// This is intentionally wider than the common unary/binary std algorithms so the
// ACCL test migrator must generate a kernel_spec with gm_inputs=4 and
// gm_outputs=5 instead of falling back to the historical x/y -> z scaffold.
template <typename _Tp>
_ASCEND_AICORE_FN constexpr void quad_fanout(
  const _Tp& __a,
  const _Tp& __b,
  const _Tp& __c,
  const _Tp& __d,
  _Tp& __out0,
  _Tp& __out1,
  _Tp& __out2,
  _Tp& __out3,
  _Tp& __out4) {
  __out0 = __a + __b;
  __out1 = __b + __c;
  __out2 = __c + __d;
  __out3 = __a - __d;
  __out4 = __a + __b + __c + __d;
}

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_QUAD_FANOUT_H_
