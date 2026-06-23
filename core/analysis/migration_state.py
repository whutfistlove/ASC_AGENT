"""机器可读的迁移「验证状态」存储——闭合 能测 → 能扩 的回路。

动机（见项目评审）：此前一个 header 的 host/kernel 测试通过后，结果只落在
`outputs/dependency_convert_report.json` 与一次性日志里，**从未回写到驱动「跳过/增量」
决策的状态**。而 `migration_status._status_for` 只认 `docs/migration_ledger.md`（手写、
仓内根本不存在）里的 `host_passed/kernel_passed/full_passed`。于是：

  * 闭包永远进不了「已验证即跳过」分支 → 每次重迁全部依赖（烧模型调用）；
  * 还可能用更差的新初稿覆盖上次已通过的产物。

本模块把每个 header 的验证结论持久化到 `outputs/migration_state.json`，并记录迁移时
**源文件内容哈希**用于「新鲜度」判断：源头变了就不再视为已验证（强制重迁），实现真正的
增量。`build_migration_status_report` 把它当作与 ledger 同级的验证证据读取。

状态取值复用 `migration_status.STATUS_VALUES`：
  * host + kernel 都过      → ``full_passed``
  * 仅 kernel 过            → ``kernel_passed``
  * 仅 host 过             → ``host_passed``
  * 其它（生成但未过/失败） → ``generated``（不进跳过集合）
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.common.utils import save_text

DEFAULT_STATE_FILENAME = "migration_state.json"
SCHEMA_VERSION = 1

# 进入「已验证、可跳过」集合的状态（与 pipeline.SAFE_DEPENDENCY_SKIP_STATUSES 对齐）。
VALIDATED_STATUSES: frozenset[str] = frozenset({"host_passed", "kernel_passed", "full_passed"})


def source_sha(text: str) -> str:
    """源文件内容哈希；用于「源未变才算已验证」的新鲜度判断。"""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def classify_status(*, host_passed: bool, kernel_passed: bool) -> str:
    """由 host/kernel 通过情况推导验证状态。"""
    if host_passed and kernel_passed:
        return "full_passed"
    if kernel_passed:
        return "kernel_passed"
    if host_passed:
        return "host_passed"
    return "generated"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class HeaderState:
    source_header: str
    target_relpath: str = ""
    status: str = "generated"
    source_sha: str = ""
    host_passed: bool = False
    kernel_passed: bool = False
    updated_at: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "host_passed": self.host_passed,
            "kernel_passed": self.kernel_passed,
            "reason": self.reason,
            "source_header": self.source_header,
            "source_sha": self.source_sha,
            "status": self.status,
            "target_relpath": self.target_relpath,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HeaderState":
        return cls(
            source_header=str(data.get("source_header", "")),
            target_relpath=str(data.get("target_relpath", "")),
            status=str(data.get("status", "generated")),
            source_sha=str(data.get("source_sha", "")),
            host_passed=bool(data.get("host_passed", False)),
            kernel_passed=bool(data.get("kernel_passed", False)),
            updated_at=str(data.get("updated_at", "")),
            reason=str(data.get("reason", "")),
        )


@dataclass
class MigrationStateStore:
    headers: dict[str, HeaderState] = field(default_factory=dict)
    path: Path | None = None

    # ----- 加载 / 保存 ----- #
    @classmethod
    def load(cls, path: str | Path) -> "MigrationStateStore":
        p = Path(path)
        if not p.exists():
            return cls(headers={}, path=p)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # 状态文件损坏不应让整条流水线崩；退化为空存储（下次运行重新积累）。
            return cls(headers={}, path=p)
        headers = {
            key: HeaderState.from_dict(value)
            for key, value in (data.get("headers") or {}).items()
            if isinstance(value, dict)
        }
        return cls(headers=headers, path=p)

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "headers": {key: self.headers[key].to_dict() for key in sorted(self.headers)},
        }

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path is not None else self.path
        if target is None:
            raise ValueError("MigrationStateStore.save 需要 path（load 时已记住，或显式传入）")
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        save_text(target, payload + "\n")
        self.path = target
        return target

    # ----- 记录一次验证结论 ----- #
    def record(
        self,
        *,
        source_header: str,
        target_relpath: str,
        source_text: str | None,
        host_passed: bool,
        kernel_passed: bool,
        reason: str = "",
    ) -> HeaderState:
        entry = HeaderState(
            source_header=source_header,
            target_relpath=target_relpath,
            status=classify_status(host_passed=host_passed, kernel_passed=kernel_passed),
            source_sha=source_sha(source_text) if source_text is not None else "",
            host_passed=host_passed,
            kernel_passed=kernel_passed,
            updated_at=_now_iso(),
            reason=reason,
        )
        self.headers[source_header] = entry
        return entry

    # ----- 作为状态证据读出（带新鲜度过滤） ----- #
    def fresh_status_map(self, header_root: str | Path) -> dict[str, str]:
        """返回 {source_header: status}，仅含 status 已验证且源文件未变 的条目。

        源文件缺失或内容哈希与记录不一致 → 视为「需重迁」，不计入（从而不会被闭包跳过）。
        若记录里没存 source_sha（旧数据），保守起见仍按已验证返回（不强制重迁）。
        """
        root = Path(header_root)
        out: dict[str, str] = {}
        for source_header, entry in self.headers.items():
            if entry.status not in VALIDATED_STATUSES:
                continue
            if entry.source_sha:
                src = root / source_header
                if not src.is_file():
                    continue
                if source_sha(src.read_text(encoding="utf-8", errors="replace")) != entry.source_sha:
                    continue
            out[source_header] = entry.status
        return out
