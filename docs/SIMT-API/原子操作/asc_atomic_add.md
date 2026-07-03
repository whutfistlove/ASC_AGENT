# asc\_atomic\_add

## 产品支持情况

<!-- npu="950" id1 -->
- Ascend 950PR/Ascend 950DT：支持
<!-- end id1 -->
<!-- npu="A3" id2 -->
- Atlas A3 训练系列产品/Atlas A3 推理系列产品：不支持
<!-- end id2 -->
<!-- npu="910b" id3 -->
- Atlas A2 训练系列产品/Atlas A2 推理系列产品：不支持
<!-- end id3 -->
<!-- npu="310b" id4 -->
- Atlas 200I/500 A2 推理产品：不支持
<!-- end id4 -->
<!-- npu="310p" id5 -->
- Atlas 推理系列产品AI Core：不支持
- Atlas 推理系列产品Vector Core：不支持
<!-- end id5 -->
<!-- npu="910" id6 -->
- Atlas 训练系列产品：不支持
<!-- end id6 -->

## 功能说明

对Unified Buffer或Global Memory中的数据与指定数据执行原子加操作，即将指定数据累加到这些内存区域的数据中。

## 函数原型

```
inline int32_t asc_atomic_add(int32_t *address, int32_t val)
```

```
inline uint32_t asc_atomic_add(uint32_t *address, uint32_t val)
```

```
inline float asc_atomic_add(float *address, float val)
```

```
inline int64_t asc_atomic_add(int64_t *address, int64_t val)
```

```
inline uint64_t asc_atomic_add(uint64_t *address, uint64_t val)
```

```
inline half asc_atomic_add(half *address, half val)
```

```
inline bfloat16_t asc_atomic_add(bfloat16_t *address, bfloat16_t val)
```

```
inline half2 asc_atomic_add(half2 *address, half2 val)
```

```
inline bfloat16x2_t asc_atomic_add(bfloat16x2_t *address, bfloat16x2_t val)
```

## 参数说明

**表1**  参数说明

| 参数名 | 输入/输出 | 描述 |
| --- | --- | --- |
| address | 输出 | Unified Buffer或Global Memory的地址。 |
| val | 输入 | 源操作数。 |

不同数据类型支持的内存范围说明如下：

**表2**  不同数据类型支持的内存范围

| 参数数据类型 | 支持的内存空间 |
| --- | --- |
| int32_t、uint32_t、float、half、bfloat16_t、half2、bfloat16x2_t | Unified Buffer、Global Memory |
| int64_t、uint64_t | Global Memory |

## 返回值说明

Unified Buffer或Global Memory上的初始数据。

注意，由于底层硬件约束，half和bfloat16\_t类型的返回值不准确，避免直接使用这些类型的返回值。

## 约束说明

原子操作保证对同一地址的读改写过程具有原子性，但不保证多个线程之间的执行顺序。对于浮点累加顺序敏感场景，结果可能随线程调度变化而不同。

## 需要包含的头文件

使用除half、half2、bfloat16\_t、bfloat16x2\_t类型之外的接口需要包含"simt\_api/device\_atomic\_functions.h"头文件，使用half和half2类型接口需要包含"simt\_api/asc\_fp16.h"头文件，使用bfloat16\_t和bfloat16x2\_t类型接口需要包含"simt\_api/asc\_bf16.h"头文件。

```
#include "simt_api/device_atomic_functions.h"
```

```
#include "simt_api/asc_fp16.h"
```

```
#include "simt_api/asc_bf16.h"
```

## 调用示例

可参阅[字节序频率直方图样例](https://gitcode.com/cann/asc-devkit/tree/master/examples/03_simt_api/02_features/01_api_features/02_atomic_operation/histogram)，该样例详细展示了如何利用`asc_atomic_add`接口，高效统计输入字节序列中每个字节值的出现频率。

简单示例场景：多个线程扫描状态数组，状态非0表示一条异常记录，使用`asc_atomic_add`接口统计异常状态的数量。输入参数说明如下：

| 名称 | 说明 |
| --- | --- |
| `status` | 每个元素表示一条状态记录，0为正常，非0为异常。 |
| `error_count` | Global Memory中的异常计数器，kernel启动前清零。 |
| `n` | 输入元素个数。 |

核心代码实现如下：

-   SIMT编程场景：

    ```cpp
    __global__ __launch_bounds__(256) void count_error_status(uint32_t *error_count,
                                                         uint32_t *status,
                                                         uint32_t n)
    {
        uint32_t idx = blockIdx.x * blockDim.x + threadIdx.x;
        if (idx >= n) {
            return;
        }

        if (status[idx] != 0U) {
            asc_atomic_add(error_count, 1U);
        }
    }
    ```

-   SIMD与SIMT混合编程场景：

    SIMD与SIMT混合编程场景，需要显式使用地址空间限定符表示地址空间：\_\_gm\_\_表示Global Memory内存空间，\_\_ubuf\_\_表示Unified Buffer内存空间。

    ```cpp
    __simt_vf__ __launch_bounds__(1024) inline void count_error_status(__gm__ uint32_t *error_count,
                                                         __gm__ uint32_t *status,
                                                         uint32_t n)
    {
        uint32_t idx = blockIdx.x * blockDim.x + threadIdx.x;
        if (idx >= n) {
            return;
        }

        if (status[idx] != 0U) {
            asc_atomic_add(error_count, 1U);
        }
    }
    ```

输出结果示例如下：

```cpp
status: 0, 2, 0, 1, 3
error_count: 3 // 表明status中有3个数据是非0的
```
