# WSL 运行指南

## 1. 环境准备

### 1.1 系统编译工具

```bash
sudo apt update
sudo apt install -y build-essential cmake git python3 python3-pip dos2unix
```

### 1.2 Python 依赖

```bash
cd /mnt/c/Users/86178/Desktop/cccl-to-accl-v3
pip install -r requirements.txt
```

### 1.3 API Key

```bash
cp .env.example .env
# 编辑 .env，填入 ZHIPU_API_KEY=<你的key>
```

### 1.4 CANN 工具链（kernel 仿真必需）

kernel 仿真依赖 **`cannsim`**（昇腾 camodel 模拟器）。它包含在 `cann-run-release` 仓库的 **toolkit** 包里——注意**社区 GA 版 `9.0.0` 不含 cannsim**，要用该仓库的 `master` 滚动构建（虽然文件名也叫 `9.0.0`，但比 GA 大 ~300MB，多带了模拟器）。

> 镜像已从早期的 `9.0.0-alpha.1/<build>/` 改为 `master/<build-id>/`，`<build-id>` 会轮换。下面用一个已验证可用的构建；若 404，浏览父目录 `.../software/master/` 取最新构建号替换。

```bash
cd /mnt/c/Users/86178/Downloads
BUILD=20260213000325157   # 如 404，换成 .../software/master/ 下最新的构建号
wget "https://mirror-centralrepo.devcloud.cn-north-4.huaweicloud.com/artifactory/cann-run-release/software/master/${BUILD}/x86_64/Ascend-cann-toolkit_9.0.0_linux-x86_64.run"
chmod +x Ascend-cann-toolkit_9.0.0_linux-x86_64.run
sudo ./Ascend-cann-toolkit_9.0.0_linux-x86_64.run --install --force --install-path=/usr/local/Ascend
# 安装时翻到 EULA 末尾输入 y 接受
```

**安装后必做：放开执行权限。** 安装器用 umask 0027，文件归 root 且对其他用户不可执行（否则 `cannsim: Permission denied`）。把安装目录归属给当前用户：

```bash
sudo chown -R "$(id -un):$(id -gn)" /usr/local/Ascend
```

写入环境变量：

```bash
cat >> ~/.bashrc << 'EOF'
export ASCEND_ENV_SCRIPT=/usr/local/Ascend/cann/set_env.sh
export ASCEND_HOME_PATH=/usr/local/Ascend/cann
export ASC_CONDA_ENV=asc_cccl_env
EOF
source ~/.bashrc
```

验证：

```bash
source /usr/local/Ascend/cann/set_env.sh
command -v cannsim && echo "cannsim OK"
```

> **SOC_VERSION**：本项目生成的 kernel `CMakeLists.txt` 用 `Ascend950PR_9599`（对应 `cannsim -s Ascend950`）。早期 alpha.1 里这颗芯片叫 `Ascend910_9599`，新版 CANN 已改名；若换了别的 toolkit 版本报 “SOC_VERSION ... does not support”，按报错里的支持列表改 `core/operator_test.py` 的 `KERNEL_SOC_VERSION`。

### 1.5 脚本换行（项目已自动处理）

项目在 `/mnt/c`（Windows 卷）上时，`.sh` 易被写成 CRLF，导致 `set -e` 失效、kernel 测试假阳性。本项目已自动修复：`save_text` 强制 LF 写入，`run_test.sh` 执行前还会再规整一次。手动兜底（可选）：

```bash
cd /mnt/c/Users/86178/Desktop/cccl-to-accl-v3
find repos/accl -name '*.sh' -exec dos2unix {} \;
chmod +x repos/accl/libascendcxx/*.sh \
         repos/accl/libascendcxx/test/libascendcxx/ascend/kernel/*/run_test.sh
```

### 1.6 离线自检

不需要 API Key 和网络，先确认 Python 链路正常：

```bash
python3 main.py selftest
# 预期：2 个样例成功，生成 outputs/batch_report.json
```

---

## 2. 三种运行模式

所有命令默认使用流式输出（`model.stream: true`）。`--show-model-io` 将提示词、完整请求和模型响应逐字打印到终端，同时落盘到 `outputs/model_request.md` 和 `outputs/model_raw_output.md`。

> 以下命令均在项目根目录执行。`min.h` 可替换为 `repos/cccl/` 下任意 CCCL 头文件。

---

### 模式一：不测试

只调模型生成 ACCL 文件并写入目标仓库，不运行测试，不提交 git。

```bash
python3 main.py convert \
  --input repos/cccl/libcudacxx/include/cuda/std/__algorithm/min.h \
  --show-model-io
```

产物：`repos/accl/libascendcxx/include/ascend/std/__algorithm/min.h`

---

### 模式二：不提交

生成 ACCL 文件，运行 host + kernel 仿真测试，不提交 git。

```bash
python3 main.py convert \
  --input repos/cccl/libcudacxx/include/cuda/std/__algorithm/min.h \
  --with-tests \
  --show-model-io
```

只跑 host（未安装 CANN 时）：

```bash
python3 main.py convert \
  --input repos/cccl/libcudacxx/include/cuda/std/__algorithm/min.h \
  --with-tests --host-only \
  --show-model-io
```

kernel 快速档（仿真 workload 降到 64 元素，camodel 近乎瞬时；整轮含重新编译约 2 分钟。完整档约 9 分钟）：

```bash
python3 main.py convert \
  --input repos/cccl/libcudacxx/include/cuda/std/__algorithm/min.h \
  --with-tests --kernel-fast \
  --show-model-io
```

kernel 仿真慢，超时默认 1200s，可调：`--kernel-timeout 1800`（或改 `config/settings.yaml` 的 `tests.kernel_timeout_sec`）。

结果在转换结果 JSON 的 `test_result` 字段，日志在：
- `outputs/host_test_<algo>.log`
- `outputs/kernel_test_<algo>.log`

> kernel 通过判定不只看退出码：日志须含 `KERNEL_SIM_RESULT: PASS` 且无失败特征，避免假阳性。

---

### 模式三：循环测试

生成后自动运行测试；测试失败时把日志和当前代码回传模型，写入修复版后重测，循环直到通过或达到最大轮数。

```bash
python3 main.py convert \
  --input repos/cccl/libcudacxx/include/cuda/std/__algorithm/min.h \
  --with-tests --test-feedback-to-model \
  --show-model-io
```

指定最大修复轮数（默认取 `config/settings.yaml` 的 `retry.max_fix_rounds`）：

```bash
python3 main.py convert \
  --input repos/cccl/libcudacxx/include/cuda/std/__algorithm/min.h \
  --with-tests --test-feedback-to-model --max-fix-rounds 3 \
  --show-model-io
```

每轮产物：
- `outputs/fixed_target_test_round{N}.h`：该轮修复版
- `outputs/fix_notes_test_round{N}.md`：该轮改动说明
- `outputs/fix_request_test_round{N}.md`：回传给模型的内容

---

## 3. 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| `bad interpreter: /bin/bash^M` | Windows CRLF 换行 | 项目已自动规整为 LF；手动兜底 `dos2unix repos/accl/libascendcxx/*.sh` |
| `cannsim: command not found` | toolkit 不含模拟器 | 装 `cann-run-release/master/<build>` 的 toolkit（GA `9.0.0` 不含 cannsim，见 1.4）|
| `cannsim: Permission denied` | 安装器 umask 0027，文件 root 私有 | `sudo chown -R "$(id -un):$(id -gn)" /usr/local/Ascend`（见 1.4）|
| `SOC_VERSION ... does not support` | toolkit 芯片名与项目不一致 | 按报错支持列表改 `core/operator_test.py` 的 `KERNEL_SOC_VERSION`（当前 `Ascend950PR_9599`）|
| kernel 测试超时被杀 | camodel 完整档约 9 分钟 | 加大 `--kernel-timeout`，或用 `--kernel-fast` 快速档 |
| `cmake: command not found` | 未安装编译工具 | `sudo apt install build-essential cmake` |
| `未读取到 ZHIPU_API_KEY` | 未配置 | 编辑 `.env` 填入 Key |
| `No module named yaml` | Python 依赖未装 | `pip install -r requirements.txt` |
| 编译报错（宏/命名空间找不到）| 生成代码与 ACCL 约定不符 | 用模式三循环测试自动修复，或手工调整 `repos/accl/.../min.h` |
