kernel_spec 约束（脚手架 + 槽位；你只填算子相关部分）：
kernel 测试的 AscendC 设备流水线、ACL 初始化/拷贝/cannsim 由固定脚手架提供。脚手架按 tile 逐元素执行，可按 `gm_inputs` / `gm_outputs` 生成 1~8 个 GM 输入和 1~8 个 GM 输出。

脚手架暴露这些变量：
- `input_init` 里：有 `std::vector<T> h_in0 ... h_inN`（T 为 dtype），用 `h_in0[i]` 等初始化输入。旧别名 `h_x`=`h_in0`、`h_y`=`h_in1`（只有 1 个输入时 `h_y` 是 dummy）。
- `element_op_code` 里：有 `T in0_val ... inN_val`，你必须给 `T out0_val ... outM_val` 赋值。旧别名 `x_val`=`in0_val`、`y_val`=`in1_val/dummy`、`z_val`=`out0_val`。
- `golden_code` 里：有 `T in0_ref ... inN_ref`，你必须给 `T expected0 ... expectedM` 赋值。旧别名 `x_ref`、`y_ref`、`expected`=`expected0`。
- `golden_code` **绝不能调用 `ascend::std::*`**，必须是独立参考实现。

规则：
0. `dtype`（必填；缺省会被工具规整为 `float`）：脚手架按此标量类型生成整条流水线。浮点算子用 `float`/`double`（容差 1e-5 比对）；**整数语义算子（gcd/lcm 等）必须填 `int32_t` 或 `int64_t`**（脚手架改用精确相等比对），否则用 float 测整数算子语义上是错的。支持集合：float / double / int32_t / int64_t / int16_t。
1. `gm_inputs` / `gm_outputs`：按算子真实需要选择。一元/二元/三参标量算子通常 1~2 输入、1 输出；多返回值算子用多个输出；复杂算子无法完整映射时，至少取一个有语义代表性的数值化切片，并在 notes 说明。
2. `input_init`：用循环变量 `i` 填输入，取值覆盖该算子有意义的区间（含正负、边界附近）。
3. `element_op_code`：用算子真实形态计算输出。二元返回值 `z_val = ascend::std::op(x_val, y_val);`；原地 void（swap）`float a=x_val,b=y_val; ascend::std::swap(a,b); z_val=a;`；三参（clamp）用常量边界 `z_val = ascend::std::clamp(x_val, 10.0f, 100.0f);`；多输入多输出形态分别给 `out0_val...outM_val` 赋值。
4. `golden_code`：与 element 等价但**独立**的参考。max：`expected = (x_ref < y_ref) ? y_ref : x_ref;`；swap（上面 z=a 写法）：`expected = y_ref;`；clamp：`expected = (x_ref < 10.0f) ? 10.0f : (x_ref > 100.0f ? 100.0f : x_ref);`；多输出分别写 `expected0`、`expected1` ...，不要只写 `expected`。
5. kernel 与 golden 必须对相同输入得到一致结果（浮点容差 1e-5，整型精确相等）。
6. 若算子无法落到逐元素形态，给出最接近的等价数值化测法，并在 notes 说明取舍。
