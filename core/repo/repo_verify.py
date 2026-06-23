"""与目标仓库交互、执行真实提交检查。

相对 v2 的改进：
1. 不再有用户主目录这种写死路径；conda.sh、conda 环境、
   clang-format 可执行名、远端、基线分支等全部来自配置。
2. hook 检查不再把英文文案写死在函数里，而是遍历 config.repo_verify.checks。
3. 所有 shell 命令统一经 Config.build_shell_script 构造，路径用 shlex.quote 转义，
   修掉了 v2 里把 commit message 直接拼进双引号字符串的注入/转义隐患。
4. 提供 dry_run：只记录将要执行的命令、不真正跑 git/clang，便于本地验证命令构造。
"""

from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.common.config import Config
from core.common.utils import save_text


@dataclass
class _CompletedStub:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def build_branch_name(prefix: str, filename: str) -> str:
    stem = Path(filename).stem
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stem}-{timestamp}"


def build_commit_message(template: str, filename: str) -> str:
    return template.format(filename=filename)


def check_commit_passed(commit_output: str, checks: list[dict]) -> dict[str, bool]:
    """按配置的 checks 逐条匹配，返回 {check_name: passed}。"""
    result: dict[str, bool] = {}
    for c in checks:
        result[c["name"]] = bool(re.search(c["pattern"], commit_output))
    return result


def required_checks_passed(check_results: dict[str, bool], checks: list[dict]) -> bool:
    for c in checks:
        if c.get("required", True) and not check_results.get(c["name"], False):
            return False
    return True


class RepoVerifier:
    def __init__(self, config: Config, dry_run: bool = False, verbose: bool = True):
        self.config = config
        self.dry_run = dry_run
        self.verbose = verbose
        self.commands: list[str] = []  # dry_run 下记录将要执行的命令

    # ----- 基础执行 ----- #
    def _log(self, *args) -> None:
        if self.verbose:
            print(*args)

    def _run(self, body: str, cd_repo: bool = True):
        script = self.config.build_shell_script(body, cd_repo=cd_repo)
        if self.dry_run:
            self.commands.append(script)
            return _CompletedStub(returncode=0, stdout="", stderr="[dry-run] not executed")
        return subprocess.run(["bash", "-lc", script], capture_output=True, text=True)

    @property
    def _checks(self) -> list[dict]:
        return self.config.repo_verify["checks"]

    @property
    def _outputs(self) -> Path:
        return self.config.output_dir

    # ----- 单步操作 ----- #
    def check_clean_worktree(self):
        return self._run("git status --porcelain")

    def checkout_new_branch(self, branch_name: str):
        rv = self.config.repo_verify
        remote = shlex.quote(rv["push_remote"])
        base = shlex.quote(rv["base_branch"])
        body = (
            f"git fetch {remote} {base}\n"
            f"git checkout -b {shlex.quote(branch_name)} {remote}/{rv['base_branch']}"
        )
        return self._run(body)

    def write_target_file(self, generated_file_path: Path, target_relpath: str) -> Path:
        repo = Path(self.config.target_repo)
        target_file_path = repo / target_relpath
        if not Path(generated_file_path).exists():
            raise FileNotFoundError(f"找不到生成文件: {generated_file_path}")
        content = Path(generated_file_path).read_text(encoding="utf-8")
        if self.dry_run:
            self.commands.append(f"[write] {target_file_path}")
            return target_file_path
        target_file_path.parent.mkdir(parents=True, exist_ok=True)
        target_file_path.write_text(content, encoding="utf-8")
        return target_file_path

    def run_clang_format(self, target_file: Path):
        clang = self.config.repo_verify["clang_format_bin"]
        return self._run(f"{shlex.quote(clang)} -i {shlex.quote(str(target_file))}", cd_repo=False)

    def git_add_and_commit(self, commit_message: str, target_relpath: str):
        rv = self.config.repo_verify
        add_target = target_relpath if rv.get("only_add_target_file", True) else "."
        sign = "-s " if rv.get("sign_off", True) else ""
        body = (
            f"git add -- {shlex.quote(add_target)}\n"
            f"git commit {sign}-m {shlex.quote(commit_message)}"
        )
        return self._run(body)

    def git_push(self, branch_name: str):
        remote = shlex.quote(self.config.repo_verify["push_remote"])
        return self._run(f"git push {remote} {shlex.quote(branch_name)}")

    # ----- 基线保存 ----- #
    def save_post_hook_baseline(self, target_file: Path, extra_name: Optional[str] = None) -> Optional[Path]:
        target_file = Path(target_file)
        # dry_run 下目标文件并不真实存在；用生成内容降级处理由调用方负责
        if not target_file.exists():
            return None
        suffix = target_file.suffix or ".txt"
        baseline_path = self._outputs / f"post_hook_baseline{suffix}"
        content = target_file.read_text(encoding="utf-8")
        save_text(baseline_path, content)
        if extra_name:
            save_text(self._outputs / extra_name, content)
        return baseline_path

    # ----- 组合流程 ----- #
    def first_commit_verify(self, generated_file_path: Path, target_relpath: str) -> dict:
        rv = self.config.repo_verify
        target_filename = Path(target_relpath).name
        branch_name = build_branch_name(rv["branch_prefix"], target_filename)
        commit_message = build_commit_message(rv["commit_message_template"], target_filename)

        info = {
            "branch_name": branch_name,
            "target_filename": target_filename,
            "target_relpath": target_relpath,
            "checkout_ok": False,
            "format_ok": False,
            "commit_ok": False,
            "checks": {},
            "style_passed": False,
            "post_hook_baseline_saved": False,
            "post_hook_baseline_path": "",
        }

        if rv.get("require_clean_worktree", True):
            self._log("检查目标仓库（ACCL）工作区是否干净...")
            status = self.check_clean_worktree()
            save_text(self._outputs / "git_status_before_verify.log",
                      (status.stdout or "") + "\n" + (status.stderr or ""))
            if status.returncode != 0:
                self._log("git status 检查失败")
                return info
            if status.stdout.strip():
                self._log("目标仓库工作区不干净，停止本次 repo verify。")
                return info

        branch = self.checkout_new_branch(branch_name)
        save_text(self._outputs / "git_checkout.log",
                  (branch.stdout or "") + "\n" + (branch.stderr or ""))
        if branch.returncode != 0:
            self._log("创建分支失败")
            return info
        info["checkout_ok"] = True

        target_file_path = self.write_target_file(generated_file_path, target_relpath)
        self._log(f"已写入目标文件: {target_file_path}")

        fmt = self.run_clang_format(target_file_path)
        save_text(self._outputs / "clang_format.log",
                  (fmt.stdout or "") + "\n" + (fmt.stderr or ""))
        if fmt.returncode != 0:
            self._log("clang-format 执行失败")
            self._save_baseline_into(info, target_file_path, "post_hook_baseline_round0.h")
            return info
        info["format_ok"] = True

        commit = self.git_add_and_commit(commit_message, target_relpath)
        commit_log = (commit.stdout or "") + "\n" + (commit.stderr or "")
        save_text(self._outputs / "git_commit.log", commit_log)

        checks = check_commit_passed(commit_log, self._checks)
        info["checks"] = checks
        info["style_passed"] = required_checks_passed(checks, self._checks)
        self._log(f"checks: {checks}")

        self._save_baseline_into(info, target_file_path, "post_hook_baseline_round0.h")

        if commit.returncode == 0 and info["style_passed"]:
            info["commit_ok"] = True
        return info

    def repair_commit_verify(self, generated_file_path: Path, target_relpath: str, round_index: int) -> dict:
        target_filename = Path(target_relpath).name
        commit_message = f"fix round{round_index} {target_filename}"

        info = {
            "round_index": round_index,
            "target_filename": target_filename,
            "target_relpath": target_relpath,
            "format_ok": False,
            "commit_ok": False,
            "checks": {},
            "style_passed": False,
            "post_hook_baseline_saved": False,
            "post_hook_baseline_path": "",
        }

        target_file_path = self.write_target_file(generated_file_path, target_relpath)
        fmt = self.run_clang_format(target_file_path)
        save_text(self._outputs / f"clang_format_round{round_index}.log",
                  (fmt.stdout or "") + "\n" + (fmt.stderr or ""))
        if fmt.returncode != 0:
            self._save_baseline_into(info, target_file_path, f"post_hook_baseline_round{round_index}.h")
            return info
        info["format_ok"] = True

        commit = self.git_add_and_commit(commit_message, target_relpath)
        commit_log = (commit.stdout or "") + "\n" + (commit.stderr or "")
        save_text(self._outputs / f"git_commit_round{round_index}.log", commit_log)

        checks = check_commit_passed(commit_log, self._checks)
        info["checks"] = checks
        info["style_passed"] = required_checks_passed(checks, self._checks)

        self._save_baseline_into(info, target_file_path, f"post_hook_baseline_round{round_index}.h")

        if commit.returncode == 0 and info["style_passed"]:
            info["commit_ok"] = True
        return info

    def push(self, branch_name: str) -> dict:
        info = {"branch_name": branch_name, "push_ok": False, "git_push_log_path": ""}
        push = self.git_push(branch_name)
        log = (push.stdout or "") + "\n" + (push.stderr or "")
        log_path = self._outputs / "git_push.log"
        save_text(log_path, log)
        save_text(
            self._outputs / "git_push_status.log",
            f"push {'success' if push.returncode == 0 else 'failed'}: {branch_name}\n",
        )
        info["git_push_log_path"] = str(log_path)
        info["push_ok"] = push.returncode == 0
        return info

    # ----- 内部 ----- #
    def _save_baseline_into(self, info: dict, target_file_path: Path, extra_name: str) -> None:
        baseline_path = self.save_post_hook_baseline(target_file_path, extra_name=extra_name)
        if baseline_path is not None:
            info["post_hook_baseline_saved"] = True
            info["post_hook_baseline_path"] = str(baseline_path)
