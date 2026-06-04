#!/bin/bash
# *****************************************************************************
# Copyright (c) 2026 Xiong Shengwu Group at Wuhan University of Technology. All Rights Reserved.
# Author: Lu Xiongbo <luxiongbo@whut.edu.cn>
# Create: 2026-01-18
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

# 读取 .author 文件
def read_author(root_dir: Path):
    author_file = root_dir / ".author"
    print(author_file)
    if not author_file.exists():
        print(f"Warning: {author_file} not found. Using default author.")
        return "Unknown Author <unknown@example.com>"
    with open(author_file, "r", encoding="utf-8") as f:
        line = f.readline().strip()
        if line:
            return line
    return "Unknown Author <unknown@example.com>"

# 生成标准版权文本（不含注释符号）
def get_plain_copyright(author: str, year: int = None):
    if year is None:
        year = datetime.now().year
    create_date = datetime.now().strftime("%Y-%m-%d")
    return (
        f"Copyright (c) {year} Xiong Shengwu Group at Wuhan University of Technology. All Rights Reserved.\n"
        f"Author: {author}\n"
        f"Create: {create_date}\n\n"
        "Licensed under the Apache License, Version 2.0 (the \"License\");\n"
        "you may not use this file except in compliance with the License.\n"
        "You may obtain a copy of the License at\n\n"
        "http://www.apache.org/licenses/LICENSE-2.0\n\n"
        "Unless required by applicable law or agreed to in writing, software\n"
        "distributed under the License is distributed on an \"AS IS\" BASIS,\n"
        "WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.\n"
        "See the License for the specific language governing permissions and\n"
        "limitations under the License."
    )

# 根据文件后缀返回注释包装方式
def wrap_comment(content: str, suffix: str, filename: str = "") -> str:
    lines = content.splitlines()
    
    # C/C++ / Ascend C / Header
    if suffix in ['.h', '.hpp', '.c', '.cpp', '.cc', '.cxx', '.cu'] or 'kernel' in filename.lower():
        wrapped = ["/******************************************************************************"]
        for line in lines:
            wrapped.append(f" * {line}" if line else " *")
        wrapped.append(" *****************************************************************************/")
        return "\n".join(wrapped)
    
    # Python
    elif suffix == '.py':
        wrapped = ["# " + line if line else "#" for line in lines]
        return "\n".join(wrapped)
    
    # Shell / CMake
    elif suffix in ['.sh', '.bash'] or filename == 'CMakeLists.txt' or suffix == '.cmake':
        wrapped = ["# " + line if line else "#" for line in lines]
        # 添加分隔线增强可读性（可选）
        top = "# " + "*" * 77
        bottom = "# " + "*" * 77
        return f"{top}\n" + "\n".join(wrapped) + f"\n{bottom}"
    
    else:
        # 默认用 /* */ 风格（保守）
        wrapped = ["/*"]
        for line in lines:
            wrapped.append(f" * {line}" if line else " *")
        wrapped.append(" */")
        return "\n".join(wrapped)

# 检查文件是否已有版权
def has_copyright(text: str) -> bool:
    keywords = ["Copyright", "Apache License", "All Rights Reserved"]
    count = sum(1 for k in keywords if k in text)
    return count >= 2

# 主函数
def main():
    parser = argparse.ArgumentParser(description="Add license header to source files.")
    parser.add_argument("files", nargs="+", help="Files to add license header to")
    args = parser.parse_args()

    root_dir = Path(__file__).parent.parent.resolve()
    print('root_dir', root_dir)
    author = read_author(root_dir)
    plain_text = get_plain_copyright(author)

    for file_path in args.files:
        path = Path(file_path)
        if not path.exists():
            print(f"Skip: {path} does not exist.")
            continue

        suffix = path.suffix.lower()
        filename = path.name

        # 读取原内容
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            print(f"Skip binary file: {path}")
            continue

        # 跳过已有版权的文件
        if has_copyright(content):
            print(f"Skip (already has copyright): {path}")
            continue

        # 生成带注释的版权头
        header = wrap_comment(plain_text, suffix, filename)

        # 特殊处理 Shebang 或 cmake_minimum_required
        new_content = content
        if suffix == ".sh" and content.startswith("#!"):
            # 插入在 Shebang 之后
            lines = content.splitlines()
            new_content = "\n".join([lines[0], "", header] + lines[1:])
        elif filename == "CMakeLists.txt" and content.startswith("cmake_minimum_required"):
            # 插入在第一行之前（CMake 允许注释在顶部）
            new_content = header + "\n\n" + content
        else:
            new_content = header + ("\n\n" if content.strip() else "") + content

        # 写回文件
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        print(f"Added license header to: {path}")

if __name__ == "__main__":
    main()
