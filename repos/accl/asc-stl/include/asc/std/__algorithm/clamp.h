#ifndef ASC_STL_INCLUDE_ASC_STD___ALGORITHM_CLAMP_H_
#define ASC_STL_INCLUDE_ASC_STD___ALGORITHM_CLAMP_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

// [MIGRATION NOTE] The original CCCL header guarded the bounds precondition
// (!comp(hi, lo)) with _CCCL_ASSERT. ASC-STL device code has no assert facility,
// so the assert is dropped; callers must pass ordered bounds (lo <= hi).
template <typename _Tp, typename _Compare>
_ASC_AICORE_FN constexpr const _Tp&
clamp(const _Tp& __v, const _Tp& __lo, const _Tp& __hi, _Compare __comp)
{
  return __comp(__v, __lo) ? __lo : __comp(__hi, __v) ? __hi : __v;
}

template <typename _Tp>
_ASC_AICORE_FN constexpr const _Tp& clamp(const _Tp& __v, const _Tp& __lo, const _Tp& __hi)
{
  return __v < __lo ? __lo : __hi < __v ? __hi : __v;
}

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___ALGORITHM_CLAMP_H_
