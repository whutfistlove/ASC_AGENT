/******************************************************************************
 * Copyright (c) 2026 Xiong Shengwu Group at Wuhan University of Technology. All Rights Reserved.
 * Author: Lu Xiongbo <luxiongbo@whut.edu.cn>
 * Create: 2026-01-19
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *****************************************************************************/

#include "acl/acl.h"
#include "ascend/std/__algorithm/max.h"
#include <iostream>
#include <cassert>

int main()
{
    // 1. 初始化 ACL（CANN Sim 会自动启用）
    aclError ret = aclInit(nullptr);
    if (ret != ACL_SUCCESS) {
        std::cerr << "aclInit failed, ret = " << ret << std::endl;
        return -1;
    }

    std::cout << "✅ ACL initialized in CANN Sim mode.\n";

    // 2. 测试 ascend::std::max（在 host 调用，但确保它能被 device 编译）
    //    实际 device kernel 中可以直接用这个函数
    int a = 10, b = 20;
    int res = ascend::std::max(a, b);
    assert(res == 20);

    std::cout << "✅ ascend::std::max(10, 20) = " << res << std::endl;

    // 3. Finalize
    aclFinalize();
    std::cout << "✅ Test passed!\n";
    return 0;
}