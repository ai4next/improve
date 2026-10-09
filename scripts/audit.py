#!/usr/bin/env python3
"""improve 确定性诊断器。

对一份 SKILL.md（及其所在目录）跑 36 条诊断码，输出**可复现、零噪音**的证据。
诊断码的 canonical 说明在 `references/skill-contract.md`；本文件的 `CATALOG`
是它的镜像，`--list-codes` 直接打印，测试会断言两者不漂移。

用法::

    python3 scripts/audit.py <skill 目录 或 SKILL.md 路径> [--json] [--out FILE]
    python3 scripts/audit.py --diff BEFORE.json AFTER.json [--json]
    python3 scripts/audit.py --list-codes

退出码：`0` 无 error ｜ `1` 有 error（或 `--diff` 判定退化）｜ `2` 用法/IO 错误。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import skillmd  # noqa: E402  (同目录模块)

TOOL = "improve/audit"
VERSION = "1.0.0"

# --------------------------------------------------------------------------
# 维度表（权重口径与 references/rubric.md 一致）
# --------------------------------------------------------------------------

DIM_NAMES = {
    1: "Frontmatter 质量",
    2: "工作流清晰度",
    3: "失败模式编码",
    4: "检查点设计",
    5: "可执行具体性",
    6: "资源整合度",
    7: "整体架构",
    8: "实测表现",
    9: "反例与黑名单",
}
DIM_WEIGHTS = {1: 7, 2: 12, 3: 12, 4: 6, 5: 18, 6: 4, 7: 12, 8: 23, 9: 6}
# machine = 完全由本脚本决定；hybrid = 脚本给上界、judge 只能下修；judge = 只能实测
DIM_MODE = {
    1: "machine",
    2: "hybrid",
    3: "machine",
    4: "machine",
    5: "machine",
    6: "machine",
    7: "hybrid",
    8: "judge",
    9: "machine",
}
PENALTY = {"error": 4.0, "warn": 1.5, "info": 0.5}
DIM_FLOOR = 1.0
DIM_CEIL = 10.0

# --------------------------------------------------------------------------
# 诊断码目录：code -> (severity, dim, 判据一句话, 修法指针)
# --------------------------------------------------------------------------

CATALOG: dict[str, tuple[str, int, str, str]] = {
    # --- FM：frontmatter ---------------------------------------------------
    "FM001": ("error", 1, "文件未以独占一行的 `---` 开头，或 frontmatter 未闭合", "补 frontmatter，见 skill-contract.md §2.1"),
    "FM002": ("error", 1, "frontmatter 缺 `name`", "补 `name: <skill 名>`"),
    "FM003": ("error", 1, "frontmatter 缺 `description`", "补 `description`，含做什么 + 何时用 + 触发词"),
    "FM004": ("error", 1, "`name` 含非法字符或超长（只允许 `[a-z0-9-]`，1–64 字符）", "改为小写短横线命名"),
    "FM005": ("warn", 1, "`name` 与 skill 目录名不一致（安装后对不上号）", "改 `name`，或去掉目录名的 `-skill` 后缀后对齐"),
    "FM006": ("error", 1, "`description` 超过 1024 字符（harness 会截断或报错）", "压缩到 1024 字符内，砍长尾关键词"),
    "FM007": ("warn", 1, "`description` 无触发词（harness 靠它选中 skill）", "补「触发词」「适用」「Use when」并列举用户真会说的话"),
    "FM008": ("warn", 1, "`description` 结尾是空话尾巴（灵活应用 / 根据情况判断 / 视情况）", "删尾巴，换成具体适用条件"),
    "FM009": ("warn", 1, "`description` 无边界声明（不适用 / 不处理 / Not for）", "补一行「不适用：…」"),
    "FM010": ("info", 1, "frontmatter 缺 `license`", "补 `license: MIT`"),
    "FM011": ("info", 1, "frontmatter 缺 `metadata.version`", "补 `metadata: {version: \"1.0\"}`"),
    # --- ST：结构 ----------------------------------------------------------
    "ST001": ("warn", 7, "正文无 H1 标题", "补一行 `# <skill 名> · <一句话>`"),
    "ST002": ("warn", 2, "找不到流程章节，也找不到编号步骤", "补「执行流程 / 工作流 / 快速路径」章节"),
    "ST003": ("warn", 2, "流程章节内无编号步骤（`1.` 或 `P0` / `Step N` 都没有）", "把流程写成有序步骤，每步写清输入与产出"),
    "ST004": ("error", 6, "正文引用的文件在 skill 目录里不存在（悬空引用）", "改路径，或补文件；删掉不存在的引用"),
    "ST005": ("info", 6, "有 `references/` 目录，但正文没有引用路由表", "补一张「时机 → 读哪个文件」的表，避免全量预读"),
    "ST006": ("warn", 9, "无「反例 / 禁令 / 反模式 / 不要做」章节", "补一节黑名单：明确写出不要做什么"),
    "ST007": ("warn", 7, "无「输出契约 / 交付」章节", "补一节：交付时报告哪几项，什么不许声称"),
    "ST008": ("info", 7, "无「质量检查 / 验收清单」章节", "补一份可勾选的验收 checklist"),
    "ST009": ("warn", 7, "SKILL.md 超过 600 行（每次触发都进上下文，成本高）", "把细节下沉到 references/，正文只留路由与判据"),
    "ST010": ("info", 7, "正文出现多个 H1（层级混乱）", "只保留一个 H1，其余降级为 H2"),
    # --- FL：失败模式 ------------------------------------------------------
    "FL001": ("warn", 3, "全文无失败分支措辞（失败 / 异常 / fallback / 兜底 / 降级）", "补失败模式章节，写出「如果 X 失败 → Y」"),
    "FL002": ("warn", 3, "有失败措辞但没有失败表（未编码为可查表的分支）", "把失败路径整理成表格"),
    "FL003": ("info", 3, "失败表缺少「仍失败兜底」一列（只有症状与解法两列）", "升级为三段式：触发条件 / 一线修复 / 仍失败兜底"),
    # --- CP：检查点 --------------------------------------------------------
    "CP001": ("warn", 4, "有「等用户确认」类措辞，但没有显性视觉标记", "在关键决策前加 `🔴 CHECKPOINT` 或 `🛑 STOP`"),
    "CP002": ("info", 4, "全文无任何显性检查点标记", "若流程含不可逆动作，在动作前插入检查点"),
    # --- SP：具体性 --------------------------------------------------------
    "SP001": ("warn", 5, "软化措辞 ≥3 处（建议 / 可以考虑 / 根据情况 / 视情况而定…）", "换成可执行的确定表述；见 playbook.md §P2"),
    "SP002": ("info", 5, "全文无代码块 / 命令行示例", "给关键步骤补一条可复制的命令或最小示例"),
    "SP003": ("info", 5, "全文无表格（信息未结构化）", "把并列的判据/分支改成表格"),
    # --- RT：runtime 中立性 ------------------------------------------------
    "RT001": ("warn", 7, "命中单 runtime 红灯措辞（须人工确认非假阳性）", "改写为 runtime-neutral 措辞；见 runtime-neutrality.md"),
    "RT002": ("warn", 7, "badge 钉死单一 runtime", "换成 Agent Skills Standard / skills.sh / Multi-Runtime 三个中立 badge"),
    "RT003": ("warn", 7, "安装路径只给单一 runtime 的目录", "补「自动检测一行命令 + 各 runtime 手动路径表 + 作为参考资料」三层结构"),
    # --- SF：安全 ----------------------------------------------------------
    "SF001": ("warn", 9, "出现破坏性命令，但未在禁令 / 反例章节登记", "在反例黑名单里明文列禁，或改用可回滚的替代命令"),
    "SF002": ("info", 9, "无凭证 / 密钥 / 隐私相关约束", "补一行：不得把凭证写入产物或日志"),
    # --- SZ：体积与一致性 --------------------------------------------------
    "SZ001": ("info", 7, "SKILL.md 超过 32KB（上下文成本）", "下沉细节到 references/"),
    "SZ002": ("info", 6, "README.md 存在但从未提到本 skill 的 `name`", "让 README 与 frontmatter 对齐，避免安装后对不上号"),
}

CODE_ORDER = sorted(CATALOG)

# 允许调用点显式下修 severity 的码：它们按「数量/规模」分两档
MULTI_SEVERITY_CODES = frozenset({"SP001"})

# --------------------------------------------------------------------------
# 词表
# --------------------------------------------------------------------------

TRIGGER_MARKERS = ("触发词", "触发", "适用", "何时用", "什么时候用", "use when", "use this", "当用户")
BOUNDARY_MARKERS = ("不适用", "不处理", "不支持", "不做", "非目标", "not for", "边界")
EMPTY_TAIL = ("灵活应用", "灵活运用", "根据情况判断", "根据具体情况", "视情况而定", "酌情处理", "随机应变")

FAILURE_MARKERS = ("失败", "异常", "fallback", "兜底", "降级", "回退", "报错", "出错", "边界条件", "error")
FALLBACK_MARKERS = ("兜底", "仍失败", "fallback", "回退", "最后手段", "退化")

CHECKPOINT_RE = re.compile(r"(🔴|🛑|\bCHECKPOINT\b|\bSTOP\b)")
CONFIRM_MARKERS = ("等用户确认", "用户确认", "经用户", "征得用户", "确认后", "暂停", "ask the user", "human in the loop")

SOFT_WORDS: dict[str, re.Pattern[str]] = {
    # 只在「下软指令」时算数：`行动建议` / `建议书` 是名词，不是软化措辞
    "建议": re.compile(r"(?<![行动价值事实评估具体])建议(?![书案])"),
    "可以考虑": re.compile(r"可以考虑"),
    "根据情况": re.compile(r"根据情况"),
    "灵活把握": re.compile(r"灵活把握"),
    "视情况而定": re.compile(r"视情况而定"),
    "酌情": re.compile(r"酌情"),
    "尽量": re.compile(r"尽量"),
    "如有必要": re.compile(r"如有必要"),
    "视需要": re.compile(r"视需要"),
    "或许": re.compile(r"或许"),
}

DESTRUCTIVE = (
    "rm -rf", "rm -fr", "git reset --hard", "push --force", "push -f",
    "git clean -fd", "git clean -fdx", "drop table", "chmod 777", "sudo rm",
    "> /dev/sda", "mkfs", "dd if=",
)

REDLIGHT = (
    (re.compile(r"在\s*Claude\s*Code\s*(里|中|内|使用)"), "「在 Claude Code 里」"),
    (re.compile(r"Claude\s*Code\s*(skill|用户|专属)", re.I), "「Claude Code skill / 用户」"),
    (re.compile(r"(Cursor|Windsurf)\s*(only|专属)", re.I), "「<runtime> only」"),
    (re.compile(r"Codex\s*中"), "「Codex 中」"),
    (re.compile(r"^\s*\[!\[Claude\s*Code", re.I), "单一 runtime badge"),
    (re.compile(r"/plugin install\b"), "只给 `/plugin install` 命令"),
)

# 元陈述标记：讲解规则、列反例、贴扫描命令的行 —— 命中不算红灯
META_MARKERS = (
    "红灯", "绿灯", "假阳性", "反例", "禁令", "禁止", "禁", "不要", "不得", "措辞",
    "黑名单", "禁用词", "软化", "grep", "正则", "扫描", "示例", "例如", "比如",
    "contract", "audit", "诊断", "判据",
    "中立", "适配", "gate", "钉死", "视为", "反模式", "替代做法",
)

# 产物路径上下文：这些行在描述「产物目录结构」，不是本 skill 自己的资源
PRODUCT_CONTEXT_MARKERS = (
    "~/.claude/skills", "~/.codex/skills", "~/.cursor/skills",
    "<slug", "<name", "<skill", "人格目录", "产物目录", "产物模型",
    "目录结构", "目录树", "输出目录", "artifact", "生成的目录",
)
# 读取动作必须**紧贴**在一个反引号路径前面才算「让 agent 去读它」。
# 否则「（人格运行体）· `references/AXIOMS.md`」里的名词「运行」会被误判成动词。
READ_IMPERATIVE_RE = re.compile(
    r"(读取|详见|参见|参阅|参考|运行|执行|调用|打开|读|见|跑|用)\s*[:：,，、]?\s*(?=`)"
)
PLACEHOLDER_RE = re.compile(r"(?i)(x{2,}|0x[^a-z0-9]|\bxx\b|foo|bar|baz|placeholder)")
IF_THEN_RE = re.compile(r"(如果|若|一旦|万一|when|if)[^\n]{0,80}?(则|就|→|，应|，改|，停|，回|，换|，删)")

BLACKLIST_TITLE_MARKERS = ("反例", "禁令", "黑名单", "不要做", "禁止", "反模式", "安全")
ROUTE_TITLE_MARKERS = ("参考文件", "路由", "references", "按需读取")
OUTPUT_TITLE_MARKERS = ("输出契约", "交付", "报告", "产物")
CHECKLIST_TITLE_MARKERS = ("质量检查", "验收", "checklist", "自检")
WORKFLOW_TITLE_MARKERS = ("流程", "工作流", "workflow", "执行", "步骤", "快速路径", "路径")

NUMBERED_STEP_RE = re.compile(
    r"^\s*(?:#{1,6}\s*|\|\s*|\*\*\s*)*(?:\d+\s*(?:[.、)]|·)|P\d+\b|Step\s*\d+|第[一二三四五六七八九十]+步)"
)
PATH_RE = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:md|py|mjs|js|json|ya?ml|html|sh|tsv|txt|csv))`")
RUNTIME_DIR_RE = re.compile(r"~/\.(claude|codex|cursor|gemini|windsurf|trae|opencode)/skills")
NET_OPS = (
    "上传", "下载", "登录", "鉴权", "授权", "数据库", "服务器", "curl", "wget",
    "requests", "api key", "api_key", "access token", "cookie", "爬取", "抓取", "接口调用",
)

RUNTIME_BOUND_NAME_RE = re.compile(r"-(codex|claude|claude-code|cursor|gemini|windsurf|trae)$", re.I)

MAX_DESCRIPTION_CHARS = 1024
MAX_LINES = 600
MAX_BYTES = 32 * 1024


# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------

@dataclass
class Finding:
    code: str
    severity: str
    dim: str
    file: str
    line: int
    message: str
    evidence: str = ""
    fix: str = ""
    suppressed: bool = False
    suppress_reason: str = ""

    def __post_init__(self) -> None:
        # severity / dim / fix 一律以 CATALOG 为准，调用点写错也漂移不了。
        # 例外：少数码按数量分两档（SP001 少量=info、≥3=warn），允许调用点显式下修。
        severity, dim, _what, fix = CATALOG[self.code]
        if self.code not in MULTI_SEVERITY_CODES:
            self.severity = severity
        self.dim = f"dim{dim}"
        if not self.fix:
            self.fix = fix

    def key(self) -> tuple[str, str, str]:
        return (self.file, self.code, self.evidence or self.message)


@dataclass
class Report:
    target: str
    skill: str
    skill_dir: str
    runtime_exempt: bool
    stats: dict[str, Any] = field(default_factory=dict)
    dims: dict[str, Any] = field(default_factory=dict)
    structural: dict[str, Any] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    suppressed: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------

def is_meta_line(line: str) -> bool:
    """这一行是在「讲规则 / 列反例」，不是在「下指令」。"""
    lowered = line.lower()
    return any(marker in lowered for marker in META_MARKERS)


def _trim(text: str, limit: int = 120) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _tables(text: str) -> list[dict[str, Any]]:
    """切出 Markdown 表格：连续 ≥2 行以 `|` 开头。"""
    lines = text.splitlines()
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            start = i
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(cells)
                i += 1
            if len(rows) >= 2:
                out.append({"line": start + 1, "rows": rows, "header": rows[0]})
            continue
        i += 1
    return out


def _resolve_target(target: str) -> tuple[str, str]:
    """返回 `(SKILL.md 绝对路径, skill 目录绝对路径)`。"""
    path = os.path.abspath(target)
    if os.path.isdir(path):
        candidate = os.path.join(path, "SKILL.md")
        if not os.path.isfile(candidate):
            raise FileNotFoundError(f"{path} 下没有 SKILL.md")
        return candidate, path
    if os.path.isfile(path):
        return path, os.path.dirname(path)
    raise FileNotFoundError(f"路径不存在：{path}")


# --------------------------------------------------------------------------
# 检查
# --------------------------------------------------------------------------

def check_frontmatter(ctx: dict[str, Any]) -> Iterable[Finding]:
    text: str = ctx["text"]
    rel = "SKILL.md"
    fm: dict[str, Any] | None
    try:
        raw_fm, _ = skillmd.split_frontmatter(text)
        fm = skillmd.parse_yaml_subset(raw_fm)
    except skillmd.FrontmatterError as exc:
        yield Finding("FM001", "error", "dim1", rel, 1, str(exc),
                      _trim(text.splitlines()[0] if text.splitlines() else ""), CATALOG["FM001"][3])
        fm = None

    if fm is None:
        return

    name = str(fm.get("name", "") or "")
    description = str(fm.get("description", "") or "")

    if not name:
        yield Finding("FM002", "error", "dim1", rel, 1, CATALOG["FM002"][2], "name 缺失", CATALOG["FM002"][3])
    else:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name):
            yield Finding("FM004", "error", "dim1", rel, 1, CATALOG["FM004"][2], f"name={name}", CATALOG["FM004"][3])
        dir_name = os.path.basename(ctx["skill_dir"])
        allowed = {dir_name}
        if dir_name.endswith("-skill"):
            allowed.add(dir_name[: -len("-skill")])
        if dir_name not in ("", ".") and name not in allowed:
            yield Finding("FM005", "error", "dim1", rel, 1, CATALOG["FM005"][2],
                          f"name={name} vs 目录={dir_name}", CATALOG["FM005"][3])

    if not description:
        yield Finding("FM003", "error", "dim1", rel, 1, CATALOG["FM003"][2], "description 缺失", CATALOG["FM003"][3])
        return

    if len(description) > MAX_DESCRIPTION_CHARS:
        yield Finding("FM006", "error", "dim1", rel, 1, CATALOG["FM006"][2],
                      f"{len(description)} 字符", CATALOG["FM006"][3])

    lowered = description.lower()
    if not any(marker in lowered for marker in TRIGGER_MARKERS):
        yield Finding("FM007", "warn", "dim1", rel, 1, CATALOG["FM007"][2],
                      _trim(description), CATALOG["FM007"][3])

    tail = description.rstrip().rstrip("。.!！").strip()
    hit = next((w for w in EMPTY_TAIL if tail.endswith(w)), None)
    if hit:
        yield Finding("FM008", "warn", "dim1", rel, 1, CATALOG["FM008"][2],
                      _trim(tail[-40:]), CATALOG["FM008"][3])

    if not any(marker in lowered for marker in BOUNDARY_MARKERS):
        yield Finding("FM009", "warn", "dim1", rel, 1, CATALOG["FM009"][2],
                      _trim(description[-60:]), CATALOG["FM009"][3])

    if not fm.get("license"):
        yield Finding("FM010", "info", "dim1", rel, 1, CATALOG["FM010"][2], "", CATALOG["FM010"][3])

    meta = fm.get("metadata")
    if not isinstance(meta, dict) or not meta.get("version"):
        yield Finding("FM011", "info", "dim1", rel, 1, CATALOG["FM011"][2], "", CATALOG["FM011"][3])


def check_structure(ctx: dict[str, Any]) -> Iterable[Finding]:
    text: str = ctx["text"]
    rel = "SKILL.md"
    lines = text.splitlines()
    masked = skillmd.mask_all(text)
    heads = skillmd.sections(text)
    titles = [h["title"] for h in heads]

    if not any(h["level"] == 1 for h in heads):
        yield Finding("ST001", "warn", "dim7", rel, 1, CATALOG["ST001"][2], "", CATALOG["ST001"][3])
    if sum(1 for h in heads if h["level"] == 1) > 1:
        dup = [h["title"] for h in heads if h["level"] == 1]
        yield Finding("ST010", "info", "dim7", rel, heads[0]["line"], CATALOG["ST010"][2],
                      _trim(" / ".join(dup)), CATALOG["ST010"][3])

    workflow = next(
        (h for h in heads if any(m in h["title"].lower() for m in WORKFLOW_TITLE_MARKERS)), None
    )
    numbered = [i + 1 for i, line in enumerate(masked.splitlines()) if NUMBERED_STEP_RE.match(line)]
    if workflow is None and not numbered:
        yield Finding("ST002", "warn", "dim2", rel, 1, CATALOG["ST002"][2], "", CATALOG["ST002"][3])
    elif workflow is not None:
        body = "\n".join(lines[workflow["line"]: workflow["end_line"]])
        if not any(NUMBERED_STEP_RE.match(l) for l in body.splitlines()):
            yield Finding("ST003", "warn", "dim2", rel, workflow["line"], CATALOG["ST003"][2],
                          _trim(workflow["title"]), CATALOG["ST003"][3])

    # 悬空引用。只在「真的会让 agent 去读一个不存在的文件」时才报，避免把
    # 「产物目录结构说明」里的路径误判成本 skill 的资源（summon 的 references/AXIOMS.md 就是这种）。
    # 判据：路径缺失 且（该行有读取动作 或 处于参考文件路由章节）且 不在产物目录语境里。
    fence_masked = skillmd.mask_code_fences(text)

    def enclosing(line_no: int) -> dict[str, Any] | None:
        """最内层包住这一行的标题。H1 是文档标题、覆盖全文，不参与语境判定。"""
        best: dict[str, Any] | None = None
        for head in heads:
            if head["level"] == 1:
                continue
            if head["line"] <= line_no <= head["end_line"]:
                if best is None or head["level"] >= best["level"]:
                    best = head
        return best

    def is_product_context(line_no: int) -> bool:
        head = enclosing(line_no)
        if head is None:
            return False
        body = "\n".join(lines[head["line"] - 1: head["end_line"]]).lower()
        return any(marker in body for marker in PRODUCT_CONTEXT_MARKERS)

    def in_route_section(line_no: int) -> bool:
        head = enclosing(line_no)
        return head is not None and any(
            marker in head["title"].lower() for marker in ROUTE_TITLE_MARKERS
        )

    for idx, line in enumerate(fence_masked.splitlines()):
        line_no = idx + 1
        if is_meta_line(line) or is_product_context(line_no):
            continue
        for raw_path in PATH_RE.findall(line):
            if raw_path.startswith(("/", "~", ".claude/", ".codex/")) or any(c in raw_path for c in "<>*"):
                continue
            if PLACEHOLDER_RE.search(raw_path):
                continue
            probe = raw_path[2:] if raw_path.startswith("./") else raw_path
            if os.path.exists(os.path.join(ctx["skill_dir"], probe)):
                continue
            if not (probe.startswith("references/") or probe.startswith("scripts/") or probe.startswith("assets/")):
                continue
            if not (READ_IMPERATIVE_RE.search(line) or in_route_section(line_no)):
                continue
            yield Finding("ST004", "error", "dim6", rel, line_no, CATALOG["ST004"][2],
                          raw_path, CATALOG["ST004"][3])

    refs_dir = os.path.join(ctx["skill_dir"], "references")
    has_route_table = any(
        "references/" in " ".join(cell for row in t["rows"] for cell in row)
        for t in _tables(fence_masked)
    )
    if os.path.isdir(refs_dir) and not has_route_table:
        yield Finding("ST005", "info", "dim6", rel, 1, CATALOG["ST005"][2], "", CATALOG["ST005"][3])

    if not any(any(m in t.lower() for m in BLACKLIST_TITLE_MARKERS) for t in titles):
        yield Finding("ST006", "warn", "dim9", rel, 1, CATALOG["ST006"][2], "", CATALOG["ST006"][3])
    if not any(any(m in t.lower() for m in OUTPUT_TITLE_MARKERS) for t in titles):
        yield Finding("ST007", "warn", "dim7", rel, 1, CATALOG["ST007"][2], "", CATALOG["ST007"][3])
    if not any(any(m in t.lower() for m in CHECKLIST_TITLE_MARKERS) for t in titles):
        yield Finding("ST008", "info", "dim7", rel, 1, CATALOG["ST008"][2], "", CATALOG["ST008"][3])

    if len(lines) > MAX_LINES:
        yield Finding("ST009", "warn", "dim7", rel, 1, CATALOG["ST009"][2],
                      f"{len(lines)} 行", CATALOG["ST009"][3])


def check_failure_modes(ctx: dict[str, Any]) -> Iterable[Finding]:
    text: str = ctx["text"]
    rel = "SKILL.md"
    masked = skillmd.mask_all(text)
    lowered = masked.lower()

    has_marker = any(m in lowered for m in FAILURE_MARKERS)
    fail_tables = [
        t for t in _tables(masked)
        if any(m in " ".join(t["header"]).lower() for m in ("失败", "异常", "故障", "fallback", "error"))
        and any(m in " ".join(t["header"]).lower() for m in ("触发", "场景", "症状", "错误", "问题", "情况", "条件"))
    ]

    if not has_marker and not fail_tables:
        yield Finding("FL001", "warn", "dim3", rel, 1, CATALOG["FL001"][2], "", CATALOG["FL001"][3])
        return

    has_branch = bool(IF_THEN_RE.search(masked))
    if has_marker and not fail_tables and not has_branch:
        first = next((i + 1 for i, l in enumerate(masked.splitlines())
                      if any(m in l.lower() for m in FAILURE_MARKERS)), 1)
        yield Finding("FL002", "warn", "dim3", rel, first, CATALOG["FL002"][2],
                      _trim(masked.splitlines()[first - 1]), CATALOG["FL002"][3])
        return

    for table in fail_tables:
        header = " ".join(table["header"]).lower()
        if len(table["header"]) < 3 or not any(m in header for m in ("兜底", "仍失败", "fallback", "回退")):
            yield Finding("FL003", "info", "dim3", rel, table["line"], CATALOG["FL003"][2],
                          _trim(" | ".join(table["header"])), CATALOG["FL003"][3])


def check_checkpoints(ctx: dict[str, Any]) -> Iterable[Finding]:
    text: str = ctx["text"]
    rel = "SKILL.md"
    masked = skillmd.mask_all(text)
    lines = masked.splitlines()

    marker_lines = [i + 1 for i, l in enumerate(lines) if CHECKPOINT_RE.search(l)]
    confirm_lines = [
        i + 1 for i, l in enumerate(lines)
        if any(m in l.lower() for m in CONFIRM_MARKERS) and not is_meta_line(l)
    ]

    if confirm_lines and not marker_lines:
        idx = confirm_lines[0]
        yield Finding("CP001", "warn", "dim4", rel, idx, CATALOG["CP001"][2],
                      _trim(lines[idx - 1]), CATALOG["CP001"][3])
    elif not marker_lines and not confirm_lines:
        yield Finding("CP002", "info", "dim4", rel, 1, CATALOG["CP002"][2], "", CATALOG["CP002"][3])


def check_specificity(ctx: dict[str, Any]) -> Iterable[Finding]:
    text: str = ctx["text"]
    rel = "SKILL.md"
    masked = skillmd.mask_all(text)
    lines = masked.splitlines()

    counts: Counter[str] = Counter()
    first_line: dict[str, int] = {}
    for idx, line in enumerate(lines):
        if is_meta_line(line):
            continue
        for word, pattern in SOFT_WORDS.items():
            n = len(pattern.findall(line))
            if n:
                counts[word] += n
                first_line.setdefault(word, idx + 1)

    total = sum(counts.values())
    if total >= 3:
        for word, n in counts.most_common():
            yield Finding("SP001", "warn", "dim5", rel, first_line[word], CATALOG["SP001"][2],
                          f"{word} × {n}", CATALOG["SP001"][3])
    elif total:
        yield Finding("SP001", "info", "dim5", rel, min(first_line.values()), CATALOG["SP001"][2],
                      " / ".join(f"{w} × {n}" for w, n in counts.most_common()), CATALOG["SP001"][3])

    if "```" not in text and "~~~" not in text:
        yield Finding("SP002", "info", "dim5", rel, 1, CATALOG["SP002"][2], "", CATALOG["SP002"][3])
    if not _tables(masked):
        yield Finding("SP003", "info", "dim5", rel, 1, CATALOG["SP003"][2], "", CATALOG["SP003"][3])


def check_runtime(ctx: dict[str, Any]) -> Iterable[Finding]:
    if ctx["runtime_exempt"]:
        return
    for rel, text in ctx["scan_files"].items():
        masked = skillmd.mask_code_fences(text)
        for idx, line in enumerate(masked.splitlines()):
            for pattern, label in REDLIGHT:
                if not pattern.search(line):
                    continue
                if is_meta_line(line):
                    ctx["suppressed_runtime"].append(
                        Finding("RT001", "warn", "dim7", rel, idx + 1, CATALOG["RT001"][2],
                                _trim(line), CATALOG["RT001"][3], True, "meta_statement")
                    )
                    continue
                yield Finding("RT001", "warn", "dim7", rel, idx + 1, CATALOG["RT001"][2],
                              f"{label}：{_trim(line)}", CATALOG["RT001"][3])
                break

        for idx, line in enumerate(masked.splitlines()):
            if re.search(r"^\s*\[!\[[^\]]*(Claude|Cursor|Codex|Windsurf)[^\]]*\]", line, re.I):
                if is_meta_line(line):
                    ctx["suppressed_runtime"].append(
                        Finding("RT002", "warn", "dim7", rel, idx + 1, CATALOG["RT002"][2],
                                _trim(line), CATALOG["RT002"][3], True, "meta_statement")
                    )
                    continue
                yield Finding("RT002", "warn", "dim7", rel, idx + 1, CATALOG["RT002"][2],
                              _trim(line), CATALOG["RT002"][3])

        install_lines = [
            (idx + 1, line) for idx, line in enumerate(masked.splitlines())
            if RUNTIME_DIR_RE.search(line)
        ]
        if install_lines:
            runtimes = {RUNTIME_DIR_RE.search(line).group(1) for _, line in install_lines}
            anchors = sum(
                1 for _, line in install_lines
                if re.search(r"(auto-detect|自动检测|npx skills add|手动路径|作为参考资料)", line, re.I)
            )
            # 给了 ≥2 个 runtime 的路径 = 已经中立，不算钉死
            if not anchors and len(runtimes) < 2:
                line_no, line = install_lines[0]
                yield Finding("RT003", "warn", "dim7", rel, line_no, CATALOG["RT003"][2],
                              _trim(line), CATALOG["RT003"][3])


def check_safety(ctx: dict[str, Any]) -> Iterable[Finding]:
    text: str = ctx["text"]
    rel = "SKILL.md"
    heads = skillmd.sections(text)
    blacklist_spans = [
        (h["line"], h["end_line"]) for h in heads
        if any(m in h["title"].lower() for m in BLACKLIST_TITLE_MARKERS)
    ]
    # 刻意用**未掩码**原文：破坏性命令通常写在行内代码里，掩码会让它消失
    lines = text.splitlines()

    def in_blacklist(line_no: int) -> bool:
        return any(start <= line_no <= end for start, end in blacklist_spans)

    for idx, line in enumerate(lines):
        lowered = line.lower()
        for cmd in DESTRUCTIVE:
            if cmd not in lowered:
                continue
            if in_blacklist(idx + 1) or is_meta_line(line):
                break
            yield Finding("SF001", "warn", "dim9", rel, idx + 1, CATALOG["SF001"][2],
                          f"{cmd}：{_trim(line)}", CATALOG["SF001"][3])
            return

    has_credential_rule = any(
        m in text.lower() for m in ("凭证", "密钥", "token", "secret", "隐私", "凭据", "api key", "api_key")
    )
    touches_network = any(m in text.lower() for m in NET_OPS)
    if touches_network and not has_credential_rule:
        yield Finding("SF002", "info", "dim9", rel, 1, CATALOG["SF002"][2], "", CATALOG["SF002"][3])


def check_size(ctx: dict[str, Any]) -> Iterable[Finding]:
    rel = "SKILL.md"
    if ctx["bytes"] > MAX_BYTES:
        yield Finding("SZ001", "info", "dim7", rel, 1, CATALOG["SZ001"][2],
                      f"{ctx['bytes'] / 1024:.1f} KB", CATALOG["SZ001"][3])

    readme = os.path.join(ctx["skill_dir"], "README.md")
    if os.path.isfile(readme):
        with open(readme, encoding="utf-8", errors="replace") as handle:
            body = handle.read()
        name = ctx.get("name") or os.path.basename(ctx["skill_dir"])
        if name and name not in body:
            yield Finding("SZ002", "info", "dim6", "README.md", 1, CATALOG["SZ002"][2],
                          f"README 未出现 `{name}`", CATALOG["SZ002"][3])


CHECKS: tuple[Callable[[dict[str, Any]], Iterable[Finding]], ...] = (
    check_frontmatter,
    check_structure,
    check_failure_modes,
    check_checkpoints,
    check_specificity,
    check_runtime,
    check_safety,
    check_size,
)


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def run_audit(target: str) -> Report:
    skill_md, skill_dir = _resolve_target(target)
    with open(skill_md, encoding="utf-8", errors="replace") as handle:
        text = handle.read()

    name = ""
    try:
        name = str(skillmd.load_frontmatter(text).get("name", "") or "")
    except skillmd.FrontmatterError:
        name = ""

    scan_files = {"SKILL.md": text}
    readme = os.path.join(skill_dir, "README.md")
    if os.path.isfile(readme):
        with open(readme, encoding="utf-8", errors="replace") as handle:
            scan_files["README.md"] = handle.read()

    ctx: dict[str, Any] = {
        "text": text,
        "skill_dir": skill_dir,
        "name": name,
        "bytes": len(text.encode("utf-8")),
        "runtime_exempt": bool(RUNTIME_BOUND_NAME_RE.search(name or os.path.basename(skill_dir))),
        "scan_files": scan_files,
        "suppressed_runtime": [],
    }

    findings: list[Finding] = []
    for check in CHECKS:
        findings.extend(check(ctx))

    findings.sort(key=lambda f: (CODE_ORDER.index(f.code), f.file, f.line))

    # 维度打分：machine / hybrid 维度由诊断惩罚直接决定
    dims: dict[str, Any] = {}
    for dim, weight in DIM_WEIGHTS.items():
        key = f"dim{dim}"
        own = [f for f in findings if f.dim == key]
        penalty = sum(PENALTY[f.severity] for f in own)
        score = max(DIM_FLOOR, DIM_CEIL - penalty) if DIM_MODE[dim] != "judge" else None
        dims[key] = {
            "name": DIM_NAMES[dim],
            "weight": weight,
            "mode": DIM_MODE[dim],
            "score": None if score is None else round(score, 2),
            "penalty": round(penalty, 2),
            "findings": len(own),
        }

    scored = [d for d in dims.values() if d["score"] is not None]
    measured_weight = sum(d["weight"] for d in scored)
    weighted = sum(d["score"] * d["weight"] for d in scored)
    structural = {
        "score": round(weighted / measured_weight * 10, 2) if measured_weight else 0.0,
        "measured_weight": measured_weight,
        "total_weight": sum(DIM_WEIGHTS.values()),
        "note": "结构分是确定性代理指标，只保证可复现与单调；它不衡量 dim8 实测表现。",
    }

    counts = Counter(f.severity for f in findings)
    stats = {
        "lines": len(text.splitlines()),
        "bytes": ctx["bytes"],
        "error": counts.get("error", 0),
        "warn": counts.get("warn", 0),
        "info": counts.get("info", 0),
    }

    report = Report(
        target=skill_md,
        skill=name or os.path.basename(skill_dir),
        skill_dir=skill_dir,
        runtime_exempt=ctx["runtime_exempt"],
        stats=stats,
        dims=dims,
        structural=structural,
        findings=findings,
        suppressed=list(ctx["suppressed_runtime"]),
    )
    report.notes.append(f"tool={TOOL} v{VERSION}")
    if report.runtime_exempt:
        report.notes.append("runtime 扫描豁免：skill name 明确绑定单一 runtime")
    return report


def to_json(report: Report) -> dict[str, Any]:
    return {
        "tool": TOOL,
        "version": VERSION,
        "target": report.target,
        "skill": report.skill,
        "skill_dir": report.skill_dir,
        "runtime_exempt": report.runtime_exempt,
        "stats": report.stats,
        "dims": report.dims,
        "structural": report.structural,
        "unverified": [f"dim{d}" for d, m in DIM_MODE.items() if m == "judge"],
        "findings": [asdict(f) for f in report.findings],
        "suppressed": [asdict(f) for f in report.suppressed],
        "notes": report.notes,
    }


def diff_reports(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """按 `(文件, 诊断码)` 做多重集比较，判定是否退化。

    刻意**不把 evidence 纳入键**：同一诊断的证据文本会随行文微调而变化，
    纳入会导致「同一条诊断被算成一消一增」的假退化。棘轮只关心
    「这个码在这一版里还在不在、多了几条」。
    """

    def group(payload: dict[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
        out: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for item in payload.get("findings", []):
            out.setdefault((item["file"], item["code"]), []).append(item)
        return out

    before_g, after_g = group(before), group(after)
    new: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []
    for key, items in after_g.items():
        extra = len(items) - len(before_g.get(key, []))
        if extra > 0:
            new.extend(items[:extra])
    for key, items in before_g.items():
        gone = len(items) - len(after_g.get(key, []))
        if gone > 0:
            resolved.extend(items[:gone])

    order = lambda f: (CODE_ORDER.index(f["code"]), f["file"], f["line"])  # noqa: E731
    new.sort(key=order)
    resolved.sort(key=order)

    blocking = [f for f in new if f["severity"] in ("error", "warn")]
    before_score = before.get("structural", {}).get("score")
    after_score = after.get("structural", {}).get("score")
    return {
        "tool": TOOL,
        "version": VERSION,
        "mode": "diff",
        "before": before.get("target"),
        "after": after.get("target"),
        "new": new,
        "resolved": resolved,
        "gate": "fail" if blocking else "pass",
        "blocking": len(blocking),
        "structural": {
            "before": before_score,
            "after": after_score,
            "delta": None if before_score is None or after_score is None
            else round(after_score - before_score, 2),
        },
        "note": "闸门 1：新增 error/warn = 退化，直接 revert，不需要 LLM 判断。",
    }


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------

SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2}
SEVERITY_TAG = {"error": "ERROR", "warn": "WARN ", "info": "INFO "}


def _group_findings(items: list[dict[str, Any]]) -> list[tuple[str, str, str, str, list[int]]]:
    """把同一 `(文件, 诊断码)` 的多条压成一行，返回 `(code, file, severity, message, lines)`。"""
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in items:
        buckets.setdefault((item["file"], item["code"]), []).append(item)
    out = []
    for (rel, code), group in sorted(buckets.items(), key=lambda kv: (CODE_ORDER.index(kv[0][1]), kv[0][0])):
        group.sort(key=lambda f: f["line"])
        out.append((code, rel, group[0]["severity"], group[0]["message"],
                    sorted({f["line"] for f in group})))
    return out


def render_human(report: Report, min_severity: str) -> str:
    keep = [f for f in report.findings if SEVERITY_ORDER[f.severity] <= SEVERITY_ORDER[min_severity]]
    out: list[str] = []
    out.append(f"# audit · {report.skill}")
    out.append(f"  {report.target}")
    out.append(
        f"  {report.stats['lines']} 行 / {report.stats['bytes'] / 1024:.1f} KB"
        f" · error {report.stats['error']} · warn {report.stats['warn']} · info {report.stats['info']}"
    )
    out.append("")
    if keep:
        out.append(f"{'SEV':6} {'CODE':6} {'DIM':5} {'LOC':>9}  MESSAGE")
        for f in keep:
            loc = f"{f.file}:{f.line}" if f.line else f.file
            out.append(f"{SEVERITY_TAG[f.severity]} {f.code:6} {f.dim:5} {loc:>9}  {f.message}")
            if f.evidence:
                out.append(f"{'':28}↳ {f.evidence}")
    else:
        out.append(f"（没有 >= {min_severity} 的诊断）")
    out.append("")
    out.append("维度：")
    for key, dim in report.dims.items():
        score = "  —  " if dim["score"] is None else f"{dim['score']:5.2f}"
        out.append(
            f"  {key} {dim['name']:<14} w={dim['weight']:<3} {dim['mode']:<7} {score}"
            f"  findings={dim['findings']}"
        )
    out.append("")
    out.append(
        f"结构分 {report.structural['score']} / 100"
        f"（覆盖权重 {report.structural['measured_weight']}/{report.structural['total_weight']}，"
        f"dim8 实测表现未测）"
    )
    if report.suppressed:
        out.append(f"（runtime 假阳性已抑制 {len(report.suppressed)} 处：元陈述行）")
    return "\n".join(out)


def render_codes() -> str:
    out = [f"{'CODE':6} {'SEV':6} {'DIM':5} 判据"]
    for code in CODE_ORDER:
        severity, dim, what, _fix = CATALOG[code]
        out.append(f"{code:6} {severity:6} dim{dim}  {what}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="audit.py",
        description="improve 确定性诊断器：对 SKILL.md 跑 36 条诊断码。",
    )
    parser.add_argument("target", nargs="?", help="skill 目录或 SKILL.md 路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--out", metavar="FILE", help="把 JSON 写入文件（用于 --diff 闸门）")
    parser.add_argument("--diff", nargs=2, metavar=("BEFORE", "AFTER"),
                        help="比较两份 audit JSON，判定是否退化")
    parser.add_argument("--min-severity", choices=("error", "warn", "info"), default="info",
                        help="人类可读输出的最低级别（默认 info）")
    parser.add_argument("--strict", action="store_true", help="warn 也算失败（退出码 1）")
    parser.add_argument("--list-codes", action="store_true", help="打印诊断码目录后退出")
    args = parser.parse_args(argv)

    if args.list_codes:
        print(render_codes())
        return 0

    if args.diff:
        try:
            with open(args.diff[0], encoding="utf-8") as handle:
                before = json.load(handle)
            with open(args.diff[1], encoding="utf-8") as handle:
                after = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"audit: 读不了 diff 输入：{exc}", file=sys.stderr)
            return 2
        result = diff_reports(before, after)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"# audit --diff · gate={result['gate']}")
            print(f"  新增 {len(result['new'])} 条，消除 {len(result['resolved'])} 条"
                  f"（其中阻断级 {result['blocking']} 条）")
            for sign, items in (("+", result["new"]), ("-", result["resolved"])):
                for code, rel, severity, message, lines in _group_findings(items):
                    where = f"{rel}:{','.join(str(n) for n in lines[:3])}"
                    if len(lines) > 3:
                        where += f" 等 {len(lines)} 处"
                    print(f"  {sign} {SEVERITY_TAG[severity]} {code} {where}  {message}")
            print(f"  结构分 {result['structural']['before']} → {result['structural']['after']}"
                  f" (Δ{result['structural']['delta']})")
        return 1 if result["gate"] == "fail" else 0

    if not args.target:
        parser.error("需要一个 target（skill 目录或 SKILL.md 路径），或 --diff / --list-codes")

    try:
        report = run_audit(args.target)
    except (FileNotFoundError, OSError) as exc:
        print(f"audit: {exc}", file=sys.stderr)
        return 2

    payload = to_json(report)
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
        except OSError as exc:
            print(f"audit: 写不了 {args.out}：{exc}", file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_human(report, args.min_severity))
        if args.out:
            print(f"\n（JSON 已写入 {args.out}）")

    if report.stats["error"]:
        return 1
    if args.strict and report.stats["warn"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
