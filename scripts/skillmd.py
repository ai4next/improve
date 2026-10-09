#!/usr/bin/env python3
"""SKILL.md 解析原语 —— 零依赖，只做四件事。

1. `split_frontmatter`  切出 YAML frontmatter 与正文
2. `parse_yaml_subset`  解析 frontmatter 用得到的 YAML 子集
3. `mask_code_fences` / `mask_inline_code`  把示例代码挖空（诊断不该命中示例）
4. `sections` / `find_section`  切章节

**本模块不做任何判断**，只把文本变成结构。所有诊断码的判据在 `scripts/audit.py`，
诊断码的 canonical 说明在 `references/skill-contract.md`。
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "FrontmatterError",
    "split_frontmatter",
    "parse_yaml_subset",
    "load_frontmatter",
    "mask_code_fences",
    "mask_inline_code",
    "mask_all",
    "sections",
    "find_section",
    "section_titles",
]

FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_BLOCK_SCALAR = {"|", "|-", "|+", ">", ">-", ">+"}


class FrontmatterError(ValueError):
    """frontmatter 缺失或未闭合。"""


# --------------------------------------------------------------------------
# 1. frontmatter 切分
# --------------------------------------------------------------------------

def split_frontmatter(text: str) -> tuple[str, str]:
    """返回 `(frontmatter 原文, 正文)`。

    frontmatter 必须从文件第 1 行（允许 BOM / 前置空行）开始，用独占一行的
    `---` 打开、`---` 或 `...` 关闭。缺失或未闭合抛 `FrontmatterError`。
    """
    lines = text.splitlines()
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start >= len(lines) or lines[start].strip().lstrip("\ufeff") != "---":
        raise FrontmatterError("文件未以独占一行的 `---` 开头，没有 frontmatter")
    for i in range(start + 1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return "\n".join(lines[start + 1:i]), "\n".join(lines[i + 1:])
    raise FrontmatterError("frontmatter 未闭合（找不到结束的 `---`）")


def load_frontmatter(text: str) -> dict[str, Any]:
    """切分 + 解析，一步到位。"""
    raw, _ = split_frontmatter(text)
    return parse_yaml_subset(raw)


# --------------------------------------------------------------------------
# 2. YAML 子集解析
# --------------------------------------------------------------------------

def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    # 行尾注释：`#` 前必须有空白，否则 `a#b` 是普通字符
    match = re.search(r"\s#", value)
    if match:
        value = value[: match.start()].rstrip()
    return value


def _looks_like_list_item(line: str) -> bool:
    stripped = line.strip()
    return stripped == "-" or stripped.startswith("- ")


def parse_yaml_subset(text: str) -> dict[str, Any]:
    """解析 frontmatter 需要的 YAML 子集。

    支持：`key: value`、引号标量、`|` / `>` 块标量（含折叠）、嵌套映射、
    缩进列表、行内 `[a, b]` 列表、`#` 注释。不支持锚点/别名/多文档/流式映射
    —— skill frontmatter 用不到，遇到就当普通字符串。
    """
    root: dict[str, Any] = {}
    # 栈元素：(该层容器的缩进, 容器)。缩进 -1 是虚拟根。
    stack: list[tuple[int, Any]] = [(-1, root)]
    lines = text.splitlines()
    i = 0

    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if _looks_like_list_item(stripped):
            item = stripped[1:].strip()
            if isinstance(parent, list):
                parent.append(_unquote(item))
            i += 1
            continue

        if ":" not in stripped:
            i += 1
            continue

        key, _, value = stripped.partition(":")
        key = _unquote(key)
        value = value.strip()

        if not isinstance(parent, dict):
            i += 1
            continue

        if value in _BLOCK_SCALAR:
            folded = value.startswith(">")
            block_indent: int | None = None
            buf: list[str] = []
            j = i + 1
            while j < len(lines):
                line = lines[j]
                if not line.strip():
                    buf.append("")
                    j += 1
                    continue
                line_indent = len(line) - len(line.lstrip(" "))
                if block_indent is None:
                    if line_indent <= indent:
                        break
                    block_indent = line_indent
                if line_indent < block_indent:
                    break
                buf.append(line[block_indent:])
                j += 1
            if folded:
                parent[key] = " ".join(part.strip() for part in buf).strip()
            else:
                parent[key] = "\n".join(buf).rstrip()
            i = j
            continue

        if value == "":
            # 空值：看下一行决定是映射还是列表
            nxt = None
            for k in range(i + 1, len(lines)):
                if lines[k].strip() and not lines[k].strip().startswith("#"):
                    nxt = lines[k]
                    break
            if nxt is not None and _looks_like_list_item(nxt):
                container: Any = []
            else:
                container = {}
            parent[key] = container
            stack.append((indent, container))
            i += 1
            continue

        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            parent[key] = [_unquote(x) for x in inner.split(",") if x.strip()] if inner else []
            i += 1
            continue

        parent[key] = _unquote(value)
        i += 1

    return root


# --------------------------------------------------------------------------
# 3. 掩码
# --------------------------------------------------------------------------

def mask_code_fences(text: str) -> str:
    """把围栏代码块的内容替换成空行，**保留行号**。围栏标记行本身也挖空。"""
    out: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        match = FENCE_RE.match(line)
        if fence is None:
            if match:
                fence = match.group(1)[0]
                out.append("")
                continue
            out.append(line)
            continue
        out.append("")
        if match and match.group(1)[0] == fence:
            fence = None
    return "\n".join(out)


def mask_inline_code(line: str) -> str:
    """把行内反引号片段挖空，长度不变（避免行内代码里的示例词被当成指令）。"""
    return INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line)


def mask_all(text: str) -> str:
    """先挖围栏块，再挖行内代码。诊断扫描一律走这个。"""
    return "\n".join(mask_inline_code(l) for l in mask_code_fences(text).splitlines())


# --------------------------------------------------------------------------
# 4. 章节
# --------------------------------------------------------------------------

def sections(text: str) -> list[dict[str, Any]]:
    """切出所有 ATX 标题（跳过围栏代码块内的 `#`）。

    返回 `[{level, title, line, end_line}]`，`line` / `end_line` 均为 1-based
    且含端点。`end_line` 是下一个同级或更高级标题的前一行（或文件末行）。
    """
    lines = text.splitlines()
    masked = mask_code_fences(text).splitlines()
    heads: list[dict[str, Any]] = []
    for idx, line in enumerate(masked):
        match = HEADING_RE.match(line)
        if match:
            heads.append(
                {
                    "level": len(match.group(1)),
                    "title": match.group(2).strip(),
                    "line": idx + 1,
                    "end_line": len(lines),
                }
            )
    for pos, head in enumerate(heads):
        for nxt in heads[pos + 1:]:
            if nxt["level"] <= head["level"]:
                head["end_line"] = nxt["line"] - 1
                break
    return heads


def section_titles(text: str) -> list[str]:
    return [s["title"] for s in sections(text)]


def find_section(text: str, *keywords: str, level: int | None = None) -> dict[str, Any] | None:
    """按关键词找第一个标题（任一关键词出现在标题里即命中，大小写不敏感）。"""
    lowered = [k.lower() for k in keywords]
    for head in sections(text):
        if level is not None and head["level"] != level:
            continue
        title = head["title"].lower()
        if any(k in title for k in lowered):
            return head
    return None
