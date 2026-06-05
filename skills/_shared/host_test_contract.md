host 测试约束（这是真正校验语义的地方）：
1. 第一行 `#include "<include_path>"`；再按需 `#include <iostream>` 等标准头；**不得**依赖 CANN/ACL。
2. 必须**逐条打印每个用例的实际数值**，沿用 `expect_eq("<表达式文本>", got, expected)` 风格：输出 `[host][<algo>] <expr> = <got> (expected <e>) OK/FAIL`。
3. 每个用例的 expected 必须是**独立**写死的值或独立公式，**不得**再调用 `ascend::std::<algo>` 来产生 expected（否则永远自洽假绿）。
4. 必须累计失败状态（如 `g_failures`）：`main()` 仅当全部用例通过才 `return 0`，否则返回非零（ctest 据此判定失败）。禁止只打印 `FAIL` 后仍固定 `return 0`。
5. 覆盖 CCCL 测试里体现的语义点：基本用例、边界、比较器重载、原地/数组等该算子实际具备的形态。
6. 按算子形态选择测法：二元返回值（max/min/clamp）用 `expect_eq("op(...)", ascend::std::op(...), <独立期望>)`；原地 void（swap）先准备左值再调用 `ascend::std::swap(a,b)`，然后校验 a、b 的新值。
