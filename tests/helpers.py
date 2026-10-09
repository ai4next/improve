"""测试公用夹具。零依赖：只用标准库 + 本仓库 scripts/。"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import audit  # noqa: E402
import ledger  # noqa: E402
import skillmd  # noqa: E402

# 一份「零诊断」的干净 skill：测试用它当正样本
CLEAN_SKILL_MD = """---
name: demo
description: |
  演示用 skill：把 A 变成 B。

  适用：用户说「把 A 变成 B」「转换一下」。
  不适用：C 场景（本 skill 不处理）。
license: MIT
metadata:
  version: "1.0"
  author: ai4next
---

# demo · 把 A 变成 B

## §一 铁律

1. **不编造** —— 没有数据就显式标注，宁可少写。

## §二 参考文件路由

| 时机 | 读取 |
|------|------|
| 总是 | `references/guide.md` |

## §三 执行流程

1. 读 `references/guide.md`，确认输入格式
2. 写产物到指定路径
3. 跑校验

```bash
python3 scripts/check.py <产物>
```

## §四 失败模式

| 触发条件 | 一线修复 | 仍失败兜底 |
|---------|---------|-----------|
| 输入文件不存在 | 让用户补路径 | 终止并如实报告 |
| 校验报错 | 按 code 修 | 两轮不降就停手报告 |

## §五 🔴 CHECKPOINT · 交付前确认

展示 diff 与校验摘要，等用户确认后再写盘。

## §六 反例黑名单

| # | 不要做 | 替代做法 |
|---|--------|---------|
| 1 | 用 `git reset --hard` 回滚 | 用 `git revert` 建反向提交 |
| 2 | 静默跳过异常 | 先告知用户再处理 |

## §七 输出契约

交付时报告：产物路径 · 校验摘要 · 已知限制。

## §八 质量检查

- [ ] 校验 0 error
- [ ] 反例黑名单已逐条对照
"""

CLEAN_README = "# demo\n\n把 A 变成 B 的最小 skill。\n"


def make_skill(tmp: str, skill_md: str = CLEAN_SKILL_MD, name: str = "demo",
               readme: str | None = CLEAN_README, extra: tuple[str, ...] = ("references/guide.md",)) -> str:
    """在 `tmp` 下建一个 skill 目录，返回目录路径。"""
    skill_dir = os.path.join(tmp, name)
    os.makedirs(skill_dir, exist_ok=True)
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as handle:
        handle.write(skill_md)
    if readme is not None:
        with open(os.path.join(skill_dir, "README.md"), "w", encoding="utf-8") as handle:
            handle.write(readme)
    for rel in extra:
        target = os.path.join(skill_dir, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("# placeholder\n")
    return skill_dir


def codes(report: audit.Report) -> list[str]:
    return [f.code for f in report.findings]


def severities(payload: dict) -> list[str]:
    return [f["severity"] for f in payload["findings"]]
